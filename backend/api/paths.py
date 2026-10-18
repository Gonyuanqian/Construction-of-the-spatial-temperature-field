"""API 层的路径与端口。

**为什么不直接用 tfield 里的默认值**：`calibration.DEFAULT_ROOT` 是相对路径
`Path("configs")`，它的含义取决于进程的 CWD。Web 服务不能依赖「启动时人在哪个目录」——
从别处启动就会读到一个空的 configs，而且**不会报错**，只是所有查询都返回「没有标定包」。
所以 API 层算绝对路径，显式传进 `root=`。`tfield` 本身一个字节不改。
"""
from __future__ import annotations

import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]     # <新项目>/backend
PROJECT = BACKEND.parent
CONFIGS = BACKEND / "configs"
DIST = PROJECT / "frontend" / "dist"      # Vite 的构建产物，生产形态由 FastAPI 托管
API_PORT = 8503

#: 上传的数据集落这儿。**不是新发明的目录** —— `.gitignore` 里早就写着
#: `backend/configs/uploads/`，注释是「上传的数据集（用户自带，不进仓库）」。
#: 与 `CONFIGS` 一样做成模块级常量：测试要能把它换到 `tmp_path` 上，
#: 否则每条上传用例都会往真的 `configs/` 里写东西。
UPLOADS = CONFIGS / "uploads"

#: 实时模式**自己的**数据源（规格书 2026-10-16 §5.1）。由
#: `scripts/make_live_source.py` 一次性切出来，**不进仓库**（与 `UPLOADS` 同待遇）。
#: 与 `UPLOADS` 同一个理由做成模块级常量：测试要能把它换到 `tmp_path` 上。
LIVE_DIR = CONFIGS / "live"
#: 拟合轴：切点之前那 1164 行。管线要一条 1164 个时刻的轴才接得上实时帧。
LIVE_TRAIN = LIVE_DIR / "train.xlsx"
#: 帧源：切点及以后那 144 行。
LIVE_FRAMES = LIVE_DIR / "live.xlsx"


def dataset_path() -> pathlib.Path:
    """本项目的数据集。

    直接用 `tfield.data.loader.test_data_path()` —— 它算的是
    `Path(__file__).resolve().parents[3] / C.DATA_FILENAME`，
    在 `backend/src/tfield/data/loader.py` 里正好解析到 `backend/`。
    包一层函数是为了让测试能 monkeypatch 掉它。
    """
    from tfield.data.loader import test_data_path
    return test_data_path()
