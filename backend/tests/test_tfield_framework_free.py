"""`tfield` 必须框架无关（spec §三）。

这一条一直住在这个文件名下 —— 「副本保真」那半（拿 `sync_backend.py --check`
跟另一棵树逐字节对）已经不在本仓里了：那半要靠一棵本仓之外的 tfield 树，
公开仓库里没有它。
"""
from __future__ import annotations

import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def test_tfield_里不许出现框架导入():
    """后端库必须框架无关（spec §三）。

    FastAPI 与 uvicorn 只允许活在 api/，`tfield` 里一个都不许有。
    本仓里 tfield 与 api 是邻居，顺手 import 的诱惑很大 —— 这条钉住它。

    ⚠️ 列的是**本仓真的依赖**的那几个：钉住一个谁也不会 import 的框架，
    这个守卫看起来还在，其实什么都没拦。
    """
    banned = ("import fastapi", "from fastapi", "import uvicorn", "from uvicorn")
    hits = []
    for p in (BACKEND / "src" / "tfield").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for b in banned:
            if b in text:
                hits.append(f"{p.relative_to(BACKEND)}: {b}")
    assert hits == [], "tfield 必须框架无关，但发现：" + "; ".join(hits)
