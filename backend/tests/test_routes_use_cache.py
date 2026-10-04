"""源码级守卫：API 层只许经 `api.deps.get_dataset()`，不许自己碰数据集加载。

**为什么需要它**（复查给的绕过路径）：`test_end_to_end.py` 那条计数守卫
把 `tfield.data.loader.load_dataset` 与 `api.deps._CACHE` 都换成了计数版，
但**改不到别处已经拷死的那个引用**：

- 某个模块在**顶层**写 `from tfield.data.loader import load_dataset` ——
  绑定在 monkeypatch 之前就固定了，计数装不上，那条测试**静默绿**；
- 同样地 `from api.deps import _CACHE` 抓走的是**旧对象**：计数守卫替换的是
  `deps._CACHE` 这个**模块属性**，改不到副本，而旧对象的 `_loader` 是没被
  patch 的真 `load_dataset` —— 结果是「计数守卫看到 1 次、数据集实际加载 2 次」，
  三绿齐现（源码守卫绿、运行期计数绿、数据集真的重复加载）。

**规则（不是名单）**：`backend/api/**` 下任何模块，从 `api.deps` 取名字时，
**只能取 `get_dataset` 这一个**。取任何别的名字（`_CACHE`、`load_dataset`、
`DatasetCache`、以及将来新增的任何私有名）一律红。

为什么写成**规则**而不是往禁用名单里堆字符串：名单会烂 —— `deps.py` 每多一个
私有名，就得再往名单里补一次，漏一次就是一个静默口子。规则只认「是不是从
`api.deps` 取的名字」，与具体叫什么无关。

两种合法写法都放行：
- `from .. import deps` 然后 `deps.get_dataset(...)`（模块导入 + 属性取用）；
- `from ..deps import get_dataset`（只取那一个名字）。

**已知且有意接受的残余（边界，不是漏）** —— 三条**都会**逃过本守卫，
都是**裁定接受的残余**：

1. **字符串字面量 getattr**：`getattr(deps, "load_dataset")(p)` 或
   `getattr(deps, "DatasetCache")().get(p)` —— 字符串落在 `Constant` 节点上，
   AST 看不见它的语义。
2. **完整点号路径**：`import api.deps` 后写 `api.deps._CACHE`（或 `import api`
   后 `api.deps._CACHE`）—— 属性链的 `.value` 是**嵌套 Attribute** 而非 Name，
   属性取用检查（要求 `node.value` 是 `ast.Name`）匹配不到。
3. **把 `deps` 当参数传进别的函数**，在函数里访问 `x._CACHE` —— 静态追不到。

**这道守卫的性质**：它是一道**黑名单式的语法守卫**，**原理上不可能穷尽** ——
补了点号路径还有 `globals()["_CACHE"]`，补了它还有
`getattr(importlib.import_module("api.deps"), "_CACHE")`。它抓的是**人真会犯的错**
（写 `load_dataset`、自建 `DatasetCache`、顶层取 `_CACHE`），**不是刻意构造的绕过**。
**别把这条守卫当成滴水不漏。** 谁要挡刻意绕过，得**换抓手**：去**读盘那一层**计数
（`pd.read_excel` 之类 choke point）—— 任何绕过最终都得读那个 xlsx —— 那是另一件事。

**为什么用 AST 不用裸文本**：裸文本会把注释与文档字符串误伤 ——
`dataset.py` 的 `_load()` docstring 里正写着 `DatasetCache.key_of` 这个词。
AST 只看 `ImportFrom` / `Import` / `Name` / `Attribute`，字面量里的词不碰。
"""
from __future__ import annotations

import ast
import pathlib

API = pathlib.Path(__file__).resolve().parents[1] / "api"

#: 路由模块都住在这个子目录里。非空断言拿它算「路由模块有没有扫到」。
ROUTES_DIRNAME = "routes"

#: **显式白名单。** `api/deps.py` 是 `load_dataset` 与 `DatasetCache` 的**持有者** ——
#: 它就是数据集缓存的正主、`get_dataset()` 的定义处，引用这些名字天经地义。
#: 其余任何模块一律不许直接碰它们，只能走 `deps.get_dataset()`。
#:
#: 这是一条**写死在这儿的声明**，不是「按后缀/按目录自动放行」那种隐式过滤：
#: 增删一行都必须改这个集合，diff 里一眼可见、review 时挡得住。键是相对 `API`
#: 的 posix 路径（不是文件名 —— 复制成 `api/core/deps.py` 仍会当场变红）。
WHITELIST = frozenset({"deps.py"})

#: 从 `api.deps` 取名字时**唯一**允许的名字。别往这儿加 —— 加之前先回答
#: 「为什么这个模块能直接拿缓存/加载器，而不是走 get_dataset()」。
#:
#: `get_pipeline` 是第二个，理由同形：`get_pipeline()` 内部先调 `get_dataset()`，
#: 它**不绕过**数据集缓存，而是把「管线只构建一次」这条性质收到一个可计数的
#: 落点上（`PipelineCache.n_builds`）。路由不许自己 new FieldPipeline。
ALLOWED_FROM_DEPS = frozenset({"get_dataset", "get_pipeline"})

#: 与 `api.deps` 无关的、任何位置都不许直接取用的通用黑名单（直取后端库/缓存类）。
FORBIDDEN_ANYWHERE = frozenset({"load_dataset", "DatasetCache"})

#: 哪些 import 的 module 算「api.deps」：相对导入 `from ..deps import X` 的 module
#: 就是 "deps"，绝对导入是 "api.deps"。
_DEPS_MODULES = frozenset({"deps", "api.deps"})


def _api_files() -> list[pathlib.Path]:
    """`backend/api/` 下**所有** `*.py`，递归，含各层 `__init__.py`。

    收口到整个 `api/` 而不是只扫 `routes/`：只扫 `routes/` 的失败模式是**静默的**
    —— 新模块一旦落在 `routes/` 之外，守卫全绿而实际什么都没扫到。
    `__init__.py` **不跳过**：里面完全可以写 `from ... import load_dataset`
    再 `__all__` 转出，按名跳过就漏了这条路。
    """
    return sorted(p for p in API.rglob("*.py"))


def _rel(f: pathlib.Path) -> str:
    return f.relative_to(API).as_posix()


def _offences_in(tree: ast.AST) -> list[str]:
    """返回这个模块里所有违规取用（行号 + 形态）。"""
    out: list[str] = []
    #: 绑定到 `api.deps` **模块对象**的本地名（`from .. import deps` / `import api.deps`）。
    deps_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module in _DEPS_MODULES:
                # 从 api.deps 取名字：只许 get_dataset 这一个。
                for alias in node.names:
                    if alias.name not in ALLOWED_FROM_DEPS:
                        out.append(
                            f"{node.lineno}: 从 api.deps 取了 {alias.name}"
                            "（只许 get_dataset）"
                        )
            else:
                # `from .. import deps` / `from api import deps` —— 模块导入，合法。
                # 记下别名，供下面「deps.<attr>」的属性取用检查。
                for alias in node.names:
                    if alias.name == "deps":
                        deps_aliases.add(alias.asname or "deps")
            for alias in node.names:
                if alias.name in FORBIDDEN_ANYWHERE:
                    out.append(f"{node.lineno}: from … import {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                last = alias.name.rsplit(".", 1)[-1]
                if alias.name in _DEPS_MODULES or last == "deps":
                    deps_aliases.add(alias.asname or last)
                if last in FORBIDDEN_ANYWHERE:
                    out.append(f"{node.lineno}: import {alias.name}")
        elif isinstance(node, (ast.Name, ast.Attribute)):
            # 任何对 load_dataset / DatasetCache 的引用（含 lz.load_dataset）
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in FORBIDDEN_ANYWHERE:
                out.append(f"{node.lineno}: 引用 {name}")

    # 属性取用：deps.<attr> 里，attr 也只许 get_dataset。
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in deps_aliases
            and node.attr not in ALLOWED_FROM_DEPS
        ):
            # 消息用**源码里实际写的那个别名**（可能是 `d` 而不是 `deps`），
            # 否则 `import api.deps as d` + `d._CACHE` 会报成 `deps._CACHE`，
            # 跟源码对不上，把诊断带偏。
            alias = node.value.id
            out.append(f"{node.lineno}: {alias}.{node.attr}（只许 {alias}.get_dataset）")
    return out


def test_api_层从_deps_只许取_get_dataset():
    files = _api_files()

    # 非空断言：目录改名/搬走后这条守卫不许变成空过。
    # 底是怎么来的：本仓 `backend/api/` 下现共 **10** 个 `*.py`
    # （5 个顶层模块 + routes/ 下 5 个），其中 **4** 个是非 `__init__` 的路由模块。
    # 取 6 与 4 是留了余量、又足够说明「确实扫到了东西」的下界。
    assert len(files) >= 6, (
        f"`backend/api/` 下只扫到 {len(files)} 个 .py（本仓当前 10 个）—— "
        "目录结构变了，这条守卫已经扫不到东西，成了空过"
    )
    route_mods = [
        f for f in files
        if f.parent.name == ROUTES_DIRNAME and f.name != "__init__.py"
    ]
    assert len(route_mods) >= 4, (
        f"只扫到 {len(route_mods)} 个路由模块（本仓当前 4 个）—— "
        "路由目录改名/搬走后这条守卫的覆盖面已经悄悄缩水"
    )

    offenders: list[str] = []
    for f in files:
        if _rel(f) in WHITELIST:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        offenders += [f"{_rel(f)}:{o}" for o in _offences_in(tree)]

    assert not offenders, (
        "API 层绕过了 api.deps.get_dataset()，直接取用了数据集加载设施：\n  "
        + "\n  ".join(offenders)
        + "\n请改成 `deps.get_dataset()` —— 否则缓存计数守卫会因为绑定拷死而静默放行。"
    )


def test_白名单只有两个出口():
    """白名单是一份**写死的声明**。它悄悄变长，是这道守卫失效的第一种方式。"""
    assert ALLOWED_FROM_DEPS == frozenset({"get_dataset", "get_pipeline"})
