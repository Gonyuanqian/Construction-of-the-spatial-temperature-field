"""副本保真：新项目的 tfield/ 与旧项目逐字节相同。

为什么不能只靠「16 个测试全绿」：测试覆盖的是**行为**，不是**同一份代码**。
副本里少了一个分支、改了一个常数，测试可能照样全绿 ——
而那时两份后端已经悄悄分了家。这条断言的是**字节**。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
SOURCE = PROJECT.parent / "空间温度场的构建"


@pytest.mark.skipif(not SOURCE.is_dir(), reason="旧项目不在旁边，跳过保真校验")
def test_新项目的_tfield_与旧项目逐字节相同():
    # PYTHONIOENCODING：Windows 控制台是 cp936，子进程的中文输出是 GBK，
    # 用 utf-8 解码会崩在 helper 里。（同 test_sync_backend.py）
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "sync_backend.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert r.returncode == 0, r.stdout + r.stderr


def test_tfield_里不许出现框架导入():
    """后端库必须框架无关（spec §三）。

    FastAPI 只允许活在 api/，Streamlit 只允许活在旧项目的 app/。
    新项目里 tfield 与 api 是邻居，顺手 import 的诱惑很大 —— 这条钉住它。
    """
    banned = ("import fastapi", "from fastapi", "import streamlit", "from streamlit")
    hits = []
    for p in (BACKEND / "src" / "tfield").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for b in banned:
            if b in text:
                hits.append(f"{p.relative_to(BACKEND)}: {b}")
    assert hits == [], "tfield 必须框架无关，但发现：" + "; ".join(hits)
