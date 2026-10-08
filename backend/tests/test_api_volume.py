"""`/api/field/volume` 的验收。**后端库就是那个 oracle。**

规格书 §4.5 立下的规矩与 P3 同一条：同一数据集、同一标定包、同一 `t_index`、
同一 `preset`、同一 `monotonic` 下，接口返回的**每一片** `values` 必须与直接调用
`tfield.field.build.field_at(...).values` **逐位相等**（NaN 位置也相同）。
冻结的 Streamlit 渲染器不构成独立证据。

整个文件是 slow：真 `fit()` 要几十秒。模块级 fixture 只 fit 一次，全文件复用。
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import create_app

pytestmark = pytest.mark.slow

#: 与页③ 的默认一致：monotonic 开着。这一卷 37 片，实测约 1.25 s。
QUERY = {"t_index": 12}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def _library(library_module):
    """这一整个模块都要求模型库里存着交付那一份模型（见 `tests/conftest.py`）。

    ⚠️ **必须是 module 级。** 下面那个 `volume` 夹具是一次真实请求的响应体
    （37 片，约 1.25 s），整个模块拿它当基准比；pytest 先建大作用域的夹具，
    函数级的 `current_model` 跑得太晚 —— 它会拿到**空库**建出的那一卷
    （兜底参数，与标定那份**同折族、不同参数**），而后面每一条都在拿它比。
    """
    return library_module


@pytest.fixture(scope="module")
def volume(client):
    r = client.get("/api/field/volume", params=QUERY)
    assert r.status_code == 200, r.text
    return r.json()


def test_形状与状态码(volume):
    for k in ("t_index", "time", "n_times", "preset", "monotonic", "calibrated",
              "y_step", "y_min", "y_max", "x_min", "x_max", "z_max", "max_measured_z",
              "vmin", "vmax", "x", "z", "arch", "sheds", "sensors",
              "available_sheds", "stripes", "planes", "elapsed_ms", "note"):
        assert k in volume, f"载荷少了 {k}"
    assert volume["t_index"] == 12
    assert volume["preset"] == "standard"
    assert volume["monotonic"] is True
    assert len(volume["planes"]) == 37, "默认 y_step=0.5、0 至 18 m 该是 37 片"
    assert [p["y"] for p in volume["planes"]] == sorted(p["y"] for p in volume["planes"])
    assert [s["id"] for s in volume["sheds"]] == ["p1", "p2", "p3"]
    assert [s["y"] for s in volume["sheds"]] == [3.0, 9.0, 15.0]


def test_每一片都与后端库逐位相等(volume):
    """**本计划的验收判据。**

    「逐位相等」不是 `almost` —— 是 `==`。接口返回的是同一批 float64 经 `repr`
    往返的数字，JSON 的往返是无损的，所以 `==` 成立；一旦有人在接口层顺手
    `round(v, 2)`、重算一遍、或者把行列接反，这条立刻红。

    对照的是 `field_at` 而不是 `section_field`：`field_at` 才是端点实际走的路，
    而它自己会在 y 撞上某个棚的 y 时短路到该断面（build.py:139-142）。
    这条测试因此同时覆盖了**实测片**（y = 3 / 9 / 15）与**混合片**（其余全部）。
    """
    from api.deps import get_pipeline
    from tfield.field.build import field_at
    from tfield.field.constraints import MonotonicConfig
    from tfield.field.grid import GridSpec

    pipe = get_pipeline()
    grid = GridSpec.from_preset(volume["preset"])
    cfg = MonotonicConfig(enabled=True) if volume["monotonic"] else None

    for p in volume["planes"]:
        f = field_at(pipe, p["y"], volume["t_index"], grid, monotonic=cfg)
        assert len(p["values"]) == f.nz, f"y={p['y']} 的行数不对"
        assert len(p["values"][0]) == f.nx, f"y={p['y']} 的列数不对"
        for iz in range(f.nz):
            for ix in range(f.nx):
                got = p["values"][iz][ix]
                want = f.values[iz, ix]
                if not np.isfinite(want):
                    assert got is None, f"y={p['y']} ({ix},{iz}) 该是 null，得到 {got!r}"
                else:
                    assert got == float(want), (
                        f"y={p['y']} ({ix},{iz}): 接口 {got!r} != 库 {float(want)!r}"
                    )
    f0 = field_at(pipe, volume["planes"][0]["y"], volume["t_index"], grid, monotonic=cfg)
    assert np.array_equal(np.asarray(volume["x"]), f0.x)
    assert np.array_equal(np.asarray(volume["z"]), f0.z)


def test_measured_与可用断面对账(volume):
    """`measured` / `shed` 的判据是 `available_sheds`，不是 `C.SHED_Y` 这个常数。

    对账而不是照抄 `_measured_at` 的实现：这里用**接口自己送出来的**
    `available_sheds` 反推，任何一边改了另一边没跟就红。
    """
    from tfield import config as C

    avail = volume["available_sheds"]
    assert avail, "一卷里没有任何可用断面"
    for p in volume["planes"]:
        hit = [s for s in avail if abs(p["y"] - C.SHED_Y[s]) < 1e-9]
        assert p["measured"] == bool(hit), f"y={p['y']} 的 measured 与可用断面对不上"
        assert p["shed"] == (hit[0] if hit else None), f"y={p['y']} 的 shed 不对"
    # 主折（留一测点）下三座棚都在，所以整卷里恰好有三片实测。
    assert sum(1 for p in volume["planes"] if p["measured"]) == len(avail)


def test_无测量带的下标与场自己的掩膜对账(volume):
    """`stripes` 与 `f.outside_measured` 同一份事实。

    行是 z、列是 x（`np.nonzero` 的次序）—— 接反了图上会出现一圈莫名其妙的斜纹，
    而接口仍然 200。所以这里两头都查：带里的 z 必须**高于**实测上限，
    带外的 z 必须**不高于**它。
    """
    from api.deps import get_pipeline
    from tfield.field.build import field_at
    from tfield.field.constraints import MonotonicConfig
    from tfield.field.grid import GridSpec

    pipe = get_pipeline()
    grid = GridSpec.from_preset(volume["preset"])
    cfg = MonotonicConfig(enabled=True)
    f = field_at(pipe, volume["planes"][0]["y"], volume["t_index"], grid, monotonic=cfg)

    want = {(int(ix), int(iz)) for iz, ix in zip(*np.nonzero(f.outside_measured))}
    got = {(ix, iz) for ix, iz in volume["stripes"]}
    assert got == want, "stripes 与库的 outside_measured 对不上"
    z = volume["z"]
    assert got, "一条无测量带都没有 —— 网格里应该有一段 z 高于实测上限"
    for ix, iz in got:
        assert z[iz] > volume["max_measured_z"], f"({ix},{iz}) 的 z 不超过上限"


def test_无测量带在整卷上完全一致(volume):
    """**这是 `stripes` 只发一份的依据**（规格书 §四.4）。

    发一份省下的是 36 份重复的下标表；而一旦哪天真不一致了，只发一份就会
    静默地在别的片上画错带子。所以这个假设要被**测**，不能被假设。
    逐片用库再算一遍 `outside_measured` 来对。
    """
    from api.deps import get_pipeline
    from tfield.field.build import field_at
    from tfield.field.constraints import MonotonicConfig
    from tfield.field.grid import GridSpec

    pipe = get_pipeline()
    grid = GridSpec.from_preset(volume["preset"])
    cfg = MonotonicConfig(enabled=True)
    ref = field_at(pipe, volume["planes"][0]["y"], volume["t_index"], grid, monotonic=cfg)
    for p in volume["planes"][1:]:
        f = field_at(pipe, p["y"], volume["t_index"], grid, monotonic=cfg)
        assert np.array_equal(f.outside_measured, ref.outside_measured), (
            f"y={p['y']} 的无测量带与第一片不一致 —— 只发一份就不成立了"
        )


def test_null_的位置与拱形掩膜对账(volume):
    """拱外必须是 `null` 而且接口仍然是 **200**。

    `JSONResponse(allow_nan=False)` 会把 NaN 变成 500 —— 「不画」是一个正常的
    答案，不是一次故障。
    """
    from api.deps import get_pipeline
    from tfield.field.build import field_at
    from tfield.field.constraints import MonotonicConfig
    from tfield.field.grid import GridSpec

    pipe = get_pipeline()
    grid = GridSpec.from_preset(volume["preset"])
    cfg = MonotonicConfig(enabled=True)
    n_null = 0
    for p in volume["planes"]:
        f = field_at(pipe, p["y"], volume["t_index"], grid, monotonic=cfg)
        for iz in range(f.nz):
            for ix in range(f.nx):
                got = p["values"][iz][ix]
                if not np.isfinite(f.values[iz, ix]):
                    assert got is None, f"y={p['y']} ({ix},{iz}) 拱外却不是 null"
                    n_null += 1
                else:
                    assert isinstance(got, float), f"y={p['y']} ({ix},{iz}) 不是浮点"
    assert n_null > 0, "整卷一个 null 都没有 —— 拱外那些格子去哪了"


def test_三档网格的_vmin_vmax_是整卷共用的(volume):
    """色标范围**全卷一份**，前端没有各算各的余地（与页③ 切面图同一口径）。"""
    assert isinstance(volume["vmin"], float)
    assert isinstance(volume["vmax"], float)
    assert volume["vmax"] > volume["vmin"]
    for p in volume["planes"]:
        vals = [v for row in p["values"] for v in row if v is not None]
        assert min(vals) >= volume["vmin"] - 1e-9
        assert max(vals) <= volume["vmax"] + 1e-9


def test_换时刻真的换帧(client, volume):
    """管线缓存**与时刻无关**，但**场**与时刻强相关。

    这条钉的是「场没有被误当作管线一起缓存」：换 `t_index` 必须真的换一批数，
    否则画面上一切正常、数字是上一时刻的，而且不报错。
    """
    other = client.get("/api/field/volume", params={"t_index": 13, "y_step": 3.0}).json()
    base = client.get("/api/field/volume", params={"t_index": 12, "y_step": 3.0}).json()
    assert other["planes"][0]["values"] != base["planes"][0]["values"], (
        "t_index 从 12 换到 13，第一片一模一样 —— 时刻被缓存掉了"
    )
    assert other["time"] != base["time"]


def test_实测片恰好落在三座棚的_y_上(client):
    """步长整除 6 的时候，y = 3 / 9 / 15 必须正好是被标为实测的那三片。"""
    body = client.get("/api/field/volume", params={"t_index": 12, "y_step": 3.0}).json()
    assert [p["y"] for p in body["planes"]] == [0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0]
    got = {p["y"]: p["shed"] for p in body["planes"] if p["measured"]}
    assert got == {3.0: "p1", 9.0: "p2", 15.0: "p3"}


def test_越界的_t_index_是_400_不是_500(client, volume):
    r = client.get("/api/field/volume", params={"t_index": volume["n_times"]})
    assert r.status_code == 400
    assert "t_index" in r.json()["detail"]



@pytest.fixture(autouse=True)
def _current_dataset():
    """空态成为默认之后，这个文件也必须**显式声明**它测的是哪一份数据集。

    2026-10-06 起，「当前在用哪一份数据集」是一个进程级的模块变量，启动时为空
    （规格书 §1.1 的空态）。不声明的话，这个模块里凡是碰数据集的用例都会拿到 409，
    而报错位置离现场很远。

    写成 autouse 而不是改各文件形状各异的 `client` 夹具，是因为本仓还有 **6 处**
    在测试里**内联**建 `TestClient(create_app())`（test_api.py ×2、
    test_api_train.py ×3、test_deps.py ×1）—— 它们同样要碰数据集，
    而只改 `client` 夹具会漏掉它们。一段代码、12 个文件、一模一样。
    """
    from api import deps, paths
    deps.set_current_dataset(paths.dataset_path())
