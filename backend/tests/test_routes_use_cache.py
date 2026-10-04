"""源码级守卫：API 层只许经 `api.deps.get_dataset()`，不许自己碰数据集加载。

**为什么需要它**（复查给的第三条绕过路径）：`test_end_to_end.py` 那条计数守卫
把 `tfield.data.loader.load_dataset` 与 `api.deps._CACHE` 都换成了计数版，
但**改不到路由模块里已经拷死的那个引用**：

- 若某模块在**顶层**写 `from tfield.data.loader import load_dataset`，
  绑定在 monkeypatch 之前就固定了 —— 计数装不上，那条测试**静默绿**；
- 同类残余还有 `deps.load_dataset(...)` 直调、以及自建 `DatasetCache().get(...)`
  （新实例不经 `_CACHE`）。

这些都是「未来化回归会静默放行」的东西 —— 本项目已经吃过两次假绿的亏。
运行期数不清，那就从**源码**上禁掉。

**扫描根是 `backend/api/` 且递归**（不是只扫 `routes/`）。为什么收口到整个
`api/`：只扫 `routes/` 的失败模式是**静默的** —— 新模块一旦落在 `routes/`
之外，守卫全绿而实际什么都没扫到。收口后唯一合法持有者 `deps.py` 走一条
**显式白名单**（见 `WHITELIST`），代价只有那一行，却把「新模块落在哪」这件事
从「守卫看不见」变成「守卫盖得住」。

`__init__.py` **不跳过**：`api/routes/__init__.py` 里完全可以写
`from tfield.data.loader import load_dataset` 再 `__all__` 转出 —— 按名跳过
就漏了这条路。所有 `*.py` 一视同仁走同一个 AST 检查。

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
#: 它就是数据集缓存的正主、`get_dataset()` 的定义处，引用这两个名字天经地义。
#: 其余任何模块一律不许直接碰它们，只能走 `deps.get_dataset()`。
#:
#: 这是一条**写死在这儿的声明**，不是「按后缀/按目录自动放行」那种隐式过滤：
#: 增删一行都必须改这个集合，diff 里一眼可见、review 时挡得住。
#: 键是相对 `API` 的 posix 路径。
WHITELIST = frozenset({"deps.py"})

#: 不许直接取用的名字。取用它们的唯一合法路径是 `deps.get_dataset()`。
FORBIDDEN = frozenset({"load_dataset", "DatasetCache"})


def _api_files() -> list[pathlib.Path]:
    """`backend/api/` 下**所有** `*.py`，递归，含各层 `__init__.py`。"""
    return sorted(p for p in API.rglob("*.py"))


def _rel(f: pathlib.Path) -> str:
    return f.relative_to(API).as_posix()


def _offences_in(tree: ast.AST) -> list[str]:
    """返回这个模块里所有对禁用名的取用（行号 + 形态）。"""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # from tfield.data.loader import load_dataset
            # from api.deps import DatasetCache
            for alias in node.names:
                if alias.name in FORBIDDEN:
                    out.append(f"{node.lineno}: from … import {alias.name}")
        elif isinstance(node, ast.Import):
            # import tfield.data.loader.load_dataset（模块名末段命中）
            for alias in node.names:
                if alias.name.rsplit(".", 1)[-1] in FORBIDDEN:
                    out.append(f"{node.lineno}: import {alias.name}")
        elif isinstance(node, (ast.Name, ast.Attribute)):
            # 任何对 load_dataset / DatasetCache 的引用（含 deps.DatasetCache）
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in FORBIDDEN:
                out.append(f"{node.lineno}: 引用 {name}")
    return out


def test_api_层不许绕过_deps_直接取用_load_dataset_或_DatasetCache():
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
        + "\n请改成 `deps.get_dataset()` —— 否则缓存计数守卫会因为顶层绑定拷死而静默放行。"
    )
