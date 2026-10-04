"""源码级守卫：路由层只许经 `api.deps.get_dataset()`，不许自己碰数据集加载。

**为什么需要它**（复查给的第三条绕过路径）：`test_end_to_end.py` 那条计数守卫
把 `tfield.data.loader.load_dataset` 与 `api.deps._CACHE` 都换成了计数版，
但**改不到路由模块里已经拷死的那个引用**：

- 若某路由在**模块顶层**写 `from tfield.data.loader import load_dataset`，
  绑定在 monkeypatch 之前就固定了 —— 计数装不上，那条测试**静默绿**；
- 同类残余还有 `deps.load_dataset(...)` 直调、以及路由里 `deps.DatasetCache().get(...)`
  （新实例不经 `_CACHE`）。

这些都是「未来化回归会静默放行」的东西 —— 本项目已经吃过两次假绿的亏。
运行期数不清，那就从**源码**上禁掉：路由模块不许出现 `load_dataset` / `DatasetCache`。

**为什么用 AST 不用裸文本**：裸文本会把注释与文档字符串误伤 ——
`dataset.py` 的 `_load()` docstring 里正写着 `DatasetCache.key_of` 这个词。
AST 只看 `ImportFrom` / `Import` / `Name` / `Attribute` / `Call`，字面量里的词不碰。
"""
from __future__ import annotations

import ast
import pathlib

ROUTES = pathlib.Path(__file__).resolve().parents[1] / "api" / "routes"

#: 路由层不许直接取用的名字。取用它们的唯一合法路径是 `deps.get_dataset()`。
FORBIDDEN = frozenset({"load_dataset", "DatasetCache"})


def _route_files() -> list[pathlib.Path]:
    return sorted(p for p in ROUTES.glob("*.py") if p.name != "__init__.py")


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


def test_路由层不许直接取用_load_dataset_或_DatasetCache():
    files = _route_files()
    # 非空断言：目录改名/搬走后这条守卫不许变成空过。
    assert len(files) >= 4, (
        f"只扫到 {len(files)} 个路由文件（本仓当前 4 个）—— "
        "目录结构变了，这条守卫已经扫不到东西，成了空过"
    )

    offenders: list[str] = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        offenders += [f"{f.name}:{o}" for o in _offences_in(tree)]

    assert not offenders, (
        "路由层绕过了 api.deps.get_dataset()，直接取用了数据集加载设施：\n  "
        + "\n  ".join(offenders)
        + "\n请改成 `deps.get_dataset()` —— 否则缓存计数守卫会因为顶层绑定拷死而静默放行。"
    )
