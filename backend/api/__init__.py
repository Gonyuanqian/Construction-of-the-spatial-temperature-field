"""FastAPI 层 —— 本仓库里**唯一**允许 import fastapi 的地方。

`backend/src/tfield/**` 必须保持框架无关（spec §三）：
它要能被脚本、被测试、被将来可能的第三个前端复用。
"""
from __future__ import annotations
