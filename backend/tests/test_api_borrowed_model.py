"""**借来的**那一份模型：库里的当前模型不是为当前训练段标的时，载荷怎么报。

⭐ 2026-10-10 用户裁定：「只要是模型库中有模型，就能选择模型库中的任意一个
模型来构建，而不是绑定数据集。」裁定之后，构场那条路不再因为数据集签名对不上
就把库里那一份丢掉、退回兜底参数 —— 于是「已标定」这一个状态里分出了两档：
**本地的**与**借来的**。这一个文件钉的是第二档。

⚠️ 三个状态都要有落点，缺一个就是屏上把借来的数说成本地成绩：
    · 没模型      → `calibrated=False`（`test_api_field` / `test_api_volume` 的
                    那个模块里验，库是空的时那两条路走的就是它）
    · 本地的      → `calibrated=True` 且 `mismatch_note` 是**空串**
    · 借来的      → `calibrated=True` 且 `mismatch_note` **有话**（就在这里）

⚠️ 全程只 `fit()` **一次**：四个用例共用同一份数据集、同一组特征、同一个包，
`PipelineCache` 的键因此相同（键里不含请求参数）。

⚠️ **不标 `slow`**：与 `test_api_live.py` 同理，那一次真 `fit()` 是可接受的
（几十秒那几条在 `test_api_field` / `test_api_volume`，它们标了）。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import conftest                                         # noqa: E402
from api import deps, models_store, paths               # noqa: E402
from api.main import create_app                         # noqa: E402

#: 与页③ 的默认一致（`test_api_volume.py` 的 QUERY 同一个值）。
QUERY = {"t_index": 12}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _borrowed(models_db):
    """每个用例都从「库里的当前模型是为**别的**数据集标的」这一处境开始。

    ⚠️ `models_db` 每一格清一次库，所以下面这条 `save_model` 每格都得重来
    （794 KB 一次）。换来的是**不必收尾**：下一条用例的库由它自己造，
    某一条挂了也不会把后面几条一起带偏。

    ⚠️ 这里**不** `deps.reset_cache()`：借来的那一份的键在四个用例之间是同一个，
    清一次就等于每个用例都重 `fit()` 一次。缓存里那一份是全局的，但它不是
    过期的 —— 它的键里就有这个包的身份。
    """
    deps.set_current_dataset(paths.dataset_path())
    ds = deps.get_train_dataset()
    other = _for_another_dataset()
    models_store.save_model("别人家标的", other, ds, "别人家的棚.xlsx")
    yield other


def _for_another_dataset():
    """一份**为别的数据集标的**包 —— 拿交付那份换个签名合成出来的。

    ⚠️ 合成而不是「从盘上找一份别人的」：盘上有没有别的包取决于谁在这台机器上
    跑过标定（本机那两份就没进仓库），**别人的克隆里根本没有**。见
    `conftest.bundle_for_another_dataset`。

    ⚠️ 要断言它真的对不上：取到对得上的那一份，下面每条用例里的那句话本来就
    该是空串 —— 红绿都不动，而它们测的东西已经换了。
    """
    return conftest.bundle_for_another_dataset()


def test_前提成立_库里那一份真的不是为这份数据标的(_borrowed):
    """先钉住前提。前提不成立时，下面每一条都会「通过」得毫无意义。"""
    assert _borrowed.dataset_sig != deps.get_train_dataset().signature


def test_页三切面照用那一份_并把借来说出来(client, _borrowed):
    b = client.get("/api/field/sections", params=QUERY).json()
    assert b["calibrated"] is True, "借来的也是标定过的一份，不是兜底参数"
    assert b["mismatch_note"] == deps._BORROWED_NOTE


def test_页四那一卷也把借来说出来(client, _borrowed):
    """同一份管线、同一个属性 —— 但这是**另一个**载荷构造器（`volume_payload`），
    两处各写一遍 `getattr(pipe, ...)`，只验一处验不到另一处。"""
    b = client.get("/api/field/volume", params=QUERY).json()
    assert b["calibrated"] is True
    assert b["mismatch_note"] == deps._BORROWED_NOTE


def test_实时那一帧也把借来说出来(client, _borrowed):
    """页⑤ 单独说得着：它的管线是 `LiveSource` 自己那一份（键里不含帧数），
    与页③ 的不是同一个对象 —— 第三档落地时最容易漏的就是这条另开的分支。"""
    client.post("/api/live/prepare")
    # ⚠️ `start` 这一下不是客套：`frame/{n}` 要求 cursor 已经走到 n
    # （`_require_walked`），而真时钟在测试里推不动它。与 `test_api_live.py`
    # 同一个手法。
    client.post("/api/live/start", params={"from_n": 3})
    b = client.get("/api/live/frame/3").json()
    assert b["calibrated"] is True
    assert b["mismatch_note"] == deps._BORROWED_NOTE
