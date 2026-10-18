"""空态：系统启动时**还没有在用数据集**。

这是本规格书里两种错的第一种，另一种是「数据集文件不见了」（`404`）。
把两者合成一种，界面就会把「你还没开始」说成「出错了」——
而验收的人第一次打开系统看到的正是这一屏。

⚠️ 这个文件是**唯一**一处故意把系统打回空态的地方：本仓其余每个测试模块
都有一条 autouse 夹具 `set_current_dataset(...)`，从此每份夹具都显式声明它测的是
哪一份数据集。所以这里**不**跟着那一行写。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, errors, paths     # noqa: E402
from api.main import create_app         # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _empty():
    """每一条都从空态开始，跑完把交付数据集装回去。

    装回去不是礼貌：`_CURRENT` 是**进程级**的模块变量，不恢复就是给后面
    跑的模块留一颗雷（它们大多在自己的夹具里装，但谁少装一次就会莫名其妙地
    拿到 409 —— 而报错位置离现场很远）。
    """
    deps.clear_current_dataset()
    yield
    deps.clear_current_dataset()
    deps.reset_cache()
    deps.set_current_dataset(paths.dataset_path())


#: 参数最少、覆盖三个不同 router 的五条接口。
#:
#: `/api/dataset/preview` 与 `/api/dataset` 同一个 router，列在这里不为覆盖面 ——
#: 是 T1 那句「防新加的路由漏了这条判断」：它读的也是当前那份宽表，漏了就是
#: 空态下回一个 500。
#:
#: ⚠️ **`/api/field/arch` 不在名单里，这是有意的**：它由 `_arch_polyline()`
#: 与 `_sensors()` 从 `tfield.config` 现算，**不碰数据集**，所以空态下它
#: 照样 200。把它写进这一条只会让人以为「空态下所有接口都 409」，
#: 而前端的外壳闸门是由 `GET /api/dataset` 单独驱动的（Task 4）——
#: arch 答得出来不影响任何一处判断。
#:
#: ⚠️ **`/api/live/status` 2026-10-16 起也搬出名单了**（规格书 §9.2 第 1 条）：
#: 页⑤ 改读 `configs/live/` 自己的两份文件，与「当前数据集」无关。空态下它不是
#: 409，是 200 —— 那一页的验收第一条断的就是这件事，在
#: `test_api_live_source.py::test_没有当前数据集时_status_是_200`。
_空态下应当_409 = [
    "/api/dataset",
    "/api/dataset/timeseries",
    "/api/dataset/preview",
    "/api/calibration",
]


def test_空态下这些接口都是_409_且是同一句话(client):
    """T1：防「新加的路由漏了这条判断」。

    写法是**逐条断言同一句 detail**，不是各断言各的：这句话由
    `api/errors.py` 一处定义，各接口各写一句就会漂成三种说法，
    而界面会把它们当成三件不同的事。
    """
    for path in _空态下应当_409:
        r = client.get(path)
        assert r.status_code == 409, f"{path} 在空态下返回了 {r.status_code}"
        assert r.json()["detail"] == errors.NO_DATASET_DETAIL, path


def test_空态与文件丢失是两种错(client):
    """T2：`set_current_dataset(不存在的路径)` → 404，**不是** 409。

    这一条同时钉住「404 要在**每一条**接口上成立」：跳过了
    `/api/dataset` 那一处显式的 `except FileNotFoundError`
    （它是仓里早就有的），所以只有全局 handler 兜得住。
    """
    deps.set_current_dataset(pathlib.Path("C:/并不存在的目录/没有这份数据集.xlsx"))
    # `/api/live/status` 不在这一串里：它早就不看当前数据集了（见上面那段），
    # 所以「当前数据集的文件不见了」对它而言是一句无关的话。
    for path in ("/api/dataset", "/api/calibration"):
        r = client.get(path)
        assert r.status_code == 404, f"{path} 把「文件不见了」报成了 {r.status_code}"


def test_装回去之后就不是空态了(client):
    """上一条的反面：**空态是一个可进可出的状态**，不是一次性的。

    没有这一条，上面两条在「永远 409」的实现下也能全绿。
    """
    deps.set_current_dataset(paths.dataset_path())
    r = client.get("/api/dataset")
    assert r.status_code == 200, r.text
    assert r.json()["signature"] == deps.get_dataset().signature
