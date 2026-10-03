"""FastAPI 层 —— 本仓库里**唯一**允许 import fastapi 的地方。

`backend/src/tfield/**` 必须保持框架无关（spec §三）：
它要能被脚本、被测试、被将来可能的第三个前端复用。
"""
from __future__ import annotations

import pathlib as _pathlib
import sys as _sys

# 把 `backend/src` 放上 sys.path，好让 `python -m uvicorn api.main:app --port 8503`
# （README 的首选启动命令）直接可用。
#
# 为什么非做不可：`tfield` 在 `backend/src/` 下，而 `pyproject.toml` 里的
# `pythonpath = ["src"]` **只对 pytest 生效**。裸跑 uvicorn 时没人替我们加这一条，
# 于是 `routes/dataset.py` 的 `from tfield import config` 会以
# `ModuleNotFoundError: No module named 'tfield'` 收场 ——
# 而**全部测试照样全绿**，因为 pytest 恰好把 src 放上了路径。
# 测试全绿却跑不起来，是这里最该防的那种差距。
#
# 放在 `api/__init__.py`：它在 `api.main` / `api.routes` 之前执行，
# 而 tfield 的 import 正好发生在那些模块里，次序刚好。
# 用 insert(0) 之外的写法都不必要 —— src 里只有 tfield 一个包，没有遮蔽风险。
_SRC = _pathlib.Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))
