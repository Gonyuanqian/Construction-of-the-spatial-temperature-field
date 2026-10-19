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

**注解不算取用**（2026-10-10 加的规则）：模块开了
`from __future__ import annotations` 时，它的注解**从不求值**，
`def f(row) -> deps.ModelFit:` 里那次属性取用在运行时根本不发生 ——
而 `ModelFit` 是个 dataclass 类型、不带任何缓存或加载器，拿它当「绕过
`get_dataset()`」来拦是**假红**（真正触发它的是 `routes/models.py:30`）。
规则只挪开**注解位置**那一个节点：值里的同一件事照抓，`FORBIDDEN_ANYWHERE`
那两个名字**连注解里也照抓**，没开 future 的模块没有这个豁免 —— 三条都由
本文件末尾那组「守卫自己的边界」钉着。
⚠️ 加的是**规则**不是名单：往 `ALLOWED_FROM_DEPS` 里补一个 `ModelFit`
也能让它变绿，但那是一条永久放宽的运行时口子，而这里放行的东西
**运行时不存在**。

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
#:
#: `get_train_dataset` 是第三个，理由仍是同形：它内部先调 `get_dataset()`，
#: 不绕过缓存，只是把「留出切分」收到一个可计数的落点上（`deps._HOLDOUTS`）。
#: 页② 必须问它 —— 标定包是按**训练段**标出来的，拿整份文件去 `load_for`
#: 会命中另一个包，于是报出来的数是**另一份标定**的数，而页面上没有任何
#: 一个字会提示这件事。
#:
#: `get_live_frames` 是第四个，理由同形（内部先调 `get_dataset()`，读的是同一个
#: 切分缓存 `deps._HOLDOUTS` 的另一半）。
#:
#: `_build_pipeline` 是第五个，**理由与前四个不同形** —— 前四个都不绕过缓存，
#: 这一个**故意**绕过 `PipelineCache`，所以这里必须把话说明白。
#: `api/live.py` 的实时源要持有**自己那份**管线实例：`PipelineCache.key_of` 是
#: `(ds.signature, groups_signature(groups), bundle.created_at)`，**里面没有帧数**。
#: 往缓存里那个共享实例上 append 一帧，键一个字节都不变，训练模式的路由会照样
#: 命中这个被改过的对象，而且不报任何错 —— 这正是这条守卫本来要拦的第一类错
#: （共享实例被就地改）。放行的是**同一个 builder 函数**，不是「随便建」：
#: 建出来的实例由 `api/live.py` 的模块级单例独自持有，不进任何路由的取用路径。
#:
#: `current_dataset_path` 是第六个，理由**是前四个那一族**（纯读入口，不绕过缓存）：
#: `GET /api/dataset` 要报出「现在在用哪一份」的**文件名**，而 `Dataset` 身上
#: 没有路径字段（`tfield` 一个字节不许改），唯一的来源就是这个槽位。
#: 以前它写 `paths.dataset_path()` —— 那在「用户导过一份」之后报的是**交付数据集**
#: 的名字，一条不报错但指错地方的岔路。
#:
#: `probe_dataset` 是第七个，**理由与 `_build_pipeline` 同族**（有意绕开缓存）：
#: 它加载的是用户刚交上来的那一份，文件下一步就改名 —— 按临时名算出的缓存键
#: 从诞生起就是废的。让 `api/uploads.py` 自己 import `load_dataset` 也能达到
#: 同样效果，但那要给**整个模块**开白名单（`WHITELIST`），而这里只需点名一个出口。
#:
#: `install_dataset` 是第八个，也是本白名单里**第一个写入口**。门槛比读入口高，
#: 所以理由要写足：它是「先清缓存、再改指针」这两步的**唯一**组合入口，
#: 写反了不会有任何报错，只会留下一个「新指针配旧缓存」的瞬间 ——
#: 而那正是导入成功后的第一个请求。合成一个具名出口，顺序就不可能写反。
#: `on_dataset_change` 是第九个，理由**与 `install_dataset` 同族**：它是**登记口**，
#: 不是读入口。它的消费者只有 `api/live.py`（在模块末尾登记自己）——
#: 路由不许用它。在路由里登记一个「换数据集时顺便干点什么」的回调，
#: 正是这条守卫要防的那类隐式耦合。
#:
#: `current_bundle` 是第十个，理由**与 `get_train_dataset` 那一族同形**
#: （纯读入口，不绕过缓存）：它是「这次用哪一份模型」的唯一出口，
#: 路由自己 `load_for` 一遍就是第二套口径 —— 而两套口径不一致的表现，
#: 是页② 说「未入库」而那几条 field 路由拿库里的模型构场，屏上没有一处提示。
#:
#: `model_fit` 是第十一个，**理由与前十个都不同，是本名单里唯一的「纯函数」**：
#: 它收的不是 `deps` 的任何状态，`ds` 是**调用方传进来**的，而调用方那一侧本来
#: 就写着 `deps.get_train_dataset()`（`routes/models.py::list_models`）。所以这条
#: 守卫要防的三类错（顶层绑定拷死、绕过缓存、共享实例被就地改）在它身上**一类都
#: 不存在** —— 函数体里没有缓存、没有加载器、没有管线。
#: 放行它恰恰是为了**减少**第二套口径：2026-10-10 之前 `/api/models` 的
#: `compatible` 与 `deps._usable` 是两套「对得上」的定义，一行按别的特征组标出来
#: 的模型列表说「能用」、构场却拒绝，屏上一个字不提。判据收到 `model_fit` 一处
#: 之后，路由**必须**能从这儿拿到它。
#: `live_train_dataset` / `live_playback_dataset` 是第十二、十三个
#: （2026-10-16 页⑤ 独立数据源那批加的），理由**与 `get_train_dataset` /
#: `get_live_frames` 那一族逐字同形**：两个函数体各只有一句
#: `get_dataset(paths.LIVE_TRAIN / LIVE_FRAMES)`，不绕过缓存、不另开判定。
#: 它们进名单**不是为了给 `api/` 开方便门**，而是相反的：页⑤ 的两份文件必须
#: 有**具名出口**，否则 `api/live.py` 与 `routes/models.py` 只能各自写一遍
#: `deps.get_dataset(paths.LIVE_*)` —— 路径从哪个属性取、要不要整份读，就会在
#: 两处各有一份口径。⚠️ `on_dataset_change` 那一条里「消费者只有 `api/live.py`」
#: 那句在 2026-10-16 之后也不再成立：`api/live.py` 已经**不再**登记自己了。
#:
#: ⚠️ 放行一条**规则**上的例外要看得更紧：往后再有人想往这份名单里加一个「纯函数」
#: 之外的出口，先回答「它有没有可能自己建缓存/加载器」。
# current_dataset_name 仅从请求上下文读取原上传文件名；不加载数据或访问缓存。
# 允许该元数据出口，避免把 UUID 存储文件名 source.xlsx 错当成用户原文件名。
ALLOWED_FROM_DEPS = frozenset({
    "get_dataset", "get_pipeline", "get_train_dataset", "get_live_frames",
    "_build_pipeline", "current_dataset_path", "probe_dataset", "install_dataset",
    "on_dataset_change", "current_bundle", "model_fit",
    "live_train_dataset", "live_playback_dataset", "current_dataset_name",
})

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


def _annotations_are_dead(tree: ast.AST) -> bool:
    """本模块开了 `from __future__ import annotations` 吗。

    开了，模块里**所有**注解都退化成字符串，运行时一个字节都不求值 ——
    `-> deps.ModelFit` 里面那次属性取用**从不发生**。没开，注解是**求值的
    表达式**，`deps.X` 那次取用是真跑的。
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(a.name == "annotations" for a in node.names):
                return True
    return False


def _dead_annotation_nodes(tree: ast.AST) -> set[int]:
    """**从不求值**的那些注解子树里，所有节点的 `id()`。

    只在 `_annotations_are_dead(tree)` 为真时返回东西。位置**只有三处**：
    函数返回值、函数参数、变量注解（`x: T = ...` 里冒号右边那半段；
    等号右边是值，**照抓**）。
    """
    if not _annotations_are_dead(tree):
        return set()

    found: set[int] = set()

    def _take(ann: ast.expr | None) -> None:
        if ann is not None:
            found.update(id(n) for n in ast.walk(ann))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _take(node.returns)
            a = node.args
            for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs,
                        a.vararg, a.kwarg]:
                if arg is not None:
                    _take(arg.annotation)
        elif isinstance(node, ast.AnnAssign):
            _take(node.annotation)
    return found


def _offences_in(tree: ast.AST) -> list[str]:
    """返回这个模块里所有违规取用（行号 + 形态）。

    ⚠️ **注解不算取用**（2026-10-10 加的规则，理由见 `_dead_annotation_nodes`）。
    豁免只挪开「注解里那个名字」这一个节点，**别的一律照抓**：

    - 值里的同一件事照抓（`x: deps.X = deps._CACHE` → 抓 `_CACHE`）；
    - `FORBIDDEN_ANYWHERE`（`load_dataset` / `DatasetCache`）**连注解里也抓**
      —— 豁免是给「类型引用」的，不是给「直取后端库」的；
    - 没开 `from __future__ import annotations` 的模块**没有**这个豁免。
    """
    out: list[str] = []
    #: 绑定到 `api.deps` **模块对象**的本地名（`from .. import deps` / `import api.deps`）。
    deps_aliases: set[str] = set()
    dead = _dead_annotation_nodes(tree)

    def _skip(node: ast.AST, name: str) -> bool:
        """这个节点在免死注解里、而且名字不是全局禁用的 —— 放过。"""
        return id(node) in dead and name not in FORBIDDEN_ANYWHERE

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
            # ⚠️ 这一支**不查** `_skip`：`FORBIDDEN_ANYWHERE` 两个名字在
            # **任何**位置都算违规，注解里也一样。`_skip` 自己也这么写的。
            if name in FORBIDDEN_ANYWHERE:
                out.append(f"{node.lineno}: 引用 {name}")

    # 属性取用：deps.<attr> 里，attr 也只许 get_dataset。
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in deps_aliases
            and node.attr not in ALLOWED_FROM_DEPS
            and not _skip(node, node.attr)
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
    # 底是怎么来的：本仓 `backend/api/` 下现共 **12** 个 `*.py`
    # （7 个顶层模块 + routes/ 下 5 个），其中 **4** 个是非 `__init__` 的路由模块。
    # 取 6 与 4 是留了余量、又足够说明「确实扫到了东西」的下界。
    assert len(files) >= 6, (
        f"`backend/api/` 下只扫到 {len(files)} 个 .py（本仓当前 12 个）—— "
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


# --------------------------------------------------------------- 守卫自己的边界
#
# ⚠️ 这一节测的是**守卫自己**的判定，不是 `api/` 的现状。它钉的是 2026-10-10
# 加进 `_offences_in` 的那条**规则**：模块开了 `from __future__ import
# annotations` 之后，注解**从不求值** —— 于是 `-> deps.ModelFit` 这种**类型
# 引用**不构成「取用」，不该红。
#
# 为什么必须把它框住：豁免一旦写成「凡是 deps.X 就放行」，这道守卫就废了。
# 所以下面三组反面用例与正面用例是**一样重要**的 —— 值里的取用照抓、
# `FORBIDDEN_ANYWHERE` 两个名字连注解里也照抓、没开 future 的模块照抓。

#: 一个「开了 future + 导入了 deps」的最小模块头，供下面几条拼装。
_MINI_HEAD = "from __future__ import annotations\nfrom .. import deps\n"


def _offences_of(src: str) -> list[str]:
    """拿一段**合成源码**问守卫要违规清单。"""
    return _offences_in(ast.parse(src))


def test_注解里的类型引用不算取用():
    """正面：`-> deps.ModelFit` 是类型引用，`ModelFit` 也不在名单上，但不该红。"""
    assert _offences_of(
        _MINI_HEAD + "def f(row, ds) -> deps.ModelFit:\n"
        "    return deps.model_fit(ds=ds)\n"
    ) == []


def test_参数与变量注解同样豁免():
    """豁免认的是**位置**（注解），不是某一种写法。"""
    assert _offences_of(
        _MINI_HEAD + "def f(other: deps.ModelFit):\n"
        "    fit: deps.ModelFit = other\n"
        "    return fit\n"
    ) == []


def test_值里的取用照抓_注解不挡_同一行也不挡():
    """反面一：同一个函数，注解豁免、**函数体**照抓 —— 豁免不许漫出来。"""
    got = _offences_of(
        _MINI_HEAD + "def f(ds) -> deps.ModelFit:\n"
        "    return deps._CACHE\n"
    )
    assert len(got) == 1 and "_CACHE" in got[0], got


def test_变量注解右边的值照抓():
    """反面二：`x: deps.X = <值>` 里，右边那半段是**求值**的。"""
    got = _offences_of(
        _MINI_HEAD + "def f():\n"
        "    fit: deps.ModelFit = deps._CACHE\n"
        "    return fit\n"
    )
    assert len(got) == 1 and "_CACHE" in got[0], got


def test_禁用名连注解里也照抓():
    """反面三：`load_dataset` / `DatasetCache` 不许出现在**任何**位置。

    这一条是这道守卫的**牙**：豁免是给「类型引用」的，不是给「直取后端库」的。
    没有它，上面那条豁免就能一路漫到 `-> deps.DatasetCache`。
    """
    got = _offences_of(
        _MINI_HEAD + "def f(x) -> deps.DatasetCache:\n"
        "    return x\n"
    )
    # ⚠️ 只断「抓到了」，不断条数：`deps.DatasetCache` 这种写法在**改这条豁免
    # 之前**就已经被两个循环各报一次（`引用 DatasetCache` + `deps.DatasetCache`），
    # 那是既有的重复报，不是这次豁免引入的，也不该顺手改掉 —— 改它就动了这条
    # 守卫对**别的**写法的输出。
    assert got and all("DatasetCache" in o for o in got), got


def test_没开_future_的模块_注解是求值的_照抓():
    """反面四：豁免的**前提**是「注解不求值」。没有 future 就没有这个前提。

    实测过：本仓 `api/` 下的模块**个个都开了**，所以这条今天不影响任何文件 ——
    它是给将来那个忘了写 future 的模块准备的。
    """
    got = _offences_of(
        "from .. import deps\n\ndef f(row) -> deps.ModelFit:\n    return row\n"
    )
    assert len(got) == 1 and "ModelFit" in got[0], got


def test_白名单只有那十三个出口():
    """白名单是一份**写死的声明**。它悄悄变长，是这道守卫失效的第一种方式。

    第三、第四、第五个（`get_train_dataset` / `get_live_frames` / `_build_pipeline`）
    都是**有意加的**：页② 必须与标定包问同一份数据集（包是按训练段标的），
    实时源必须拿得到留出段与一份**自己独有**的管线。加它们要改这一行 ——
    这正是这条测试存在的意义：让白名单的每一次生长都落在 diff 里，
    而不是悄悄发生。

    第六个（`current_dataset_path`，2026-10-06 加）也是有意加的，理由见上面
    常量旁边。**它属于「纯读入口」那一族** —— 加读入口的门槛比加写入口低，
    因为读入口掩盖不了「两次读之间状态被改」那类错。

    第七到第九个（`probe_dataset` / `install_dataset` / `on_dataset_change`，
    2026-10-06 数据导入那批一起加）同样是有意加的，理由见常量旁边。
    ⚠️ **后两个是写入口，不是读入口** —— 加它们的门槛比前六个高，因为放行一个
    写入口能掩盖的错比读入口多。看到它们在名单上就该多问一句：「为什么这条
    路由能改当前数据集 / 为什么要登记回调」。两个答案都是「那次改动只有这一个
    入口」。

    第十个（`current_bundle`，2026-10-08 模型库那批加）**回到「纯读入口」那一族**：
    它取代的是四个地方各自一遍的 `load_for(ds, groups, paths.CONFIGS)`，
    而那四处正是「这次用哪一份模型」有五套口径的来源。

    第十一个（`model_fit`，2026-10-10 「模型不绑数据集」那批加）是名单里
    **唯一的纯函数**：它不拿 `deps` 的任何状态，`ds` 由调用方传进来。
    ⚠️ 它进名单不是为了「方便」，是为了**把判据收到一处** —— 2026-10-10 之前
    `/api/models` 与 `deps._usable` 是两套「对得上」的定义，列表说能用、
    构场的路却拒绝。理由见常量旁边。

    第十二、十三个（`live_train_dataset` / `live_playback_dataset`，2026-10-16
    页⑤ 独立数据源那批加）回到**「纯读入口」那一族**：各一句
    `get_dataset(paths.LIVE_*)`，不绕过缓存。⚠️ 加它们是要**收口径**而不是开门：
    页⑤ 的两份文件必须只有一个具名出口，否则 `api/live.py` 与 `routes/models.py`
    会各自写一遍「路径从哪个属性取、整份读还是切」。
    """
    assert ALLOWED_FROM_DEPS == frozenset({
        "get_dataset", "get_pipeline", "get_train_dataset", "get_live_frames",
        "_build_pipeline", "current_dataset_path", "probe_dataset", "install_dataset",
        "on_dataset_change", "current_bundle", "model_fit",
        "live_train_dataset", "live_playback_dataset", "current_dataset_name",
    })
