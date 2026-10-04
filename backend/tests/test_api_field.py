"""页③ 的三个接口。**这个文件是本计划的验收对象。**

最重的一条是 `test_与后端库逐位相等` —— spec §十：同一数据集、同一标定包、
同一时刻下，接口返回的每个数值必须与直接调用 `tfield` 的**逐位相等**。
它是 P3 唯一必要的证明，与 Streamlit 版无关：**后端库本身就是那个 oracle**，
冻结的渲染器不构成独立证据。

整个文件是 slow：真 `fit()` 要几十秒。模块级 fixture 只 fit 一次，全文件复用 ——
否则三条测试就是三次 fit。
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import create_app

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="module")
def sections(client):
    r = client.get("/api/field/sections", params={"t_index": 12})
    assert r.status_code == 200, r.text
    return r.json()


def test_形状与状态码(sections):
    for k in ("t_index", "time", "n_times", "preset", "monotonic", "calibrated",
              "vmin", "vmax", "max_measured_z", "x_min", "x_max", "z_max",
              "x", "z", "arch", "sensors", "sheds", "note"):
        assert k in sections, f"载荷少了 {k}"
    assert sections["t_index"] == 12
    assert [s["shed"] for s in sections["sheds"]] == ["p1", "p2", "p3"]
    assert [s["y"] for s in sections["sheds"]] == [3.0, 9.0, 15.0]


def test_拱外一律是_null_不是_NaN_且接口仍然是_200(sections):
    """Review Focus 2：`JSONResponse(allow_nan=False)` 会把 NaN 变成 500。

    拱外那一半网格**必须是 `null`**，而且接口必须仍然是 **200** ——
    「不画」是一个正常的答案，不是一次故障。
    """
    n = 0
    for s in sections["sheds"]:
        for row in s["values"]:
            for v in row:
                if v is None:
                    n += 1
                else:
                    assert isinstance(v, float)
    assert n > 0, "三个断面里一个 null 都没有 —— 拱外的格子去哪了？"


def test_无测量带用斜纹下标报出来而不是报数(sections):
    """z > 1.10 m 的带里**存着外推值**，但界面上不许报。

    后端只负责指出**哪些格子属于那条带**（`stripes`），
    「不报数」这句话在 Task 8 的 `interpretPick` 里落实。
    """
    z = sections["z"]
    for s in sections["sheds"]:
        assert s["stripes"], f"{s['shed']} 一条斜纹格子都没有 —— 无测量带不见了"
        for ix, iz in s["stripes"]:
            assert z[iz] > sections["max_measured_z"], (
                f"({ix},{iz}) 的 z={z[iz]} 不大于 max_measured_z —— 斜纹盖到实测区了"
            )


def test_三格共享同一个_vmin_vmax(sections):
    """Review Focus 4：后端**只给一对** vmin/vmax，前端没有各算各的余地。"""
    assert isinstance(sections["vmin"], float)
    assert isinstance(sections["vmax"], float)
    assert sections["vmax"] > sections["vmin"]
    for s in sections["sheds"]:
        vals = [v for row in s["values"] for v in row if v is not None]
        assert min(vals) >= sections["vmin"] - 1e-9
        assert max(vals) <= sections["vmax"] + 1e-9


def test_与后端库逐位相等(client, sections):
    """**P3 的验收判据（spec §十）。**

    「逐位相等」不是 `almost` —— 是 `==`。接口返回的是同一批 float64 经
    `repr` 往返的数字，JSON 的往返是无损的，所以 `==` 成立；
    一旦有人在接口层顺手 `round(v, 2)` 或者重算一遍，这条立刻红。
    """
    from tfield.field.build import section_field
    from tfield.field.constraints import MonotonicConfig
    from tfield.field.grid import GridSpec

    from api.deps import get_pipeline

    pipe = get_pipeline()
    grid = GridSpec.from_preset(sections["preset"])
    cfg = MonotonicConfig(enabled=True) if sections["monotonic"] else None

    for s in sections["sheds"]:
        f = section_field(pipe, s["shed"], sections["t_index"], grid, monotonic=cfg)
        assert len(s["values"]) == f.nz
        assert len(s["values"][0]) == f.nx
        for iz in range(f.nz):
            for ix in range(f.nx):
                got = s["values"][iz][ix]
                want = f.values[iz, ix]
                if not np.isfinite(want):
                    assert got is None, f"({ix},{iz}) 该是 null"
                else:
                    assert got == float(want), (
                        f"{s['shed']} ({ix},{iz}): 接口 {got!r} != 库 {float(want)!r}"
                    )
        assert np.array_equal(np.asarray(sections["x"]), f.x)
        assert np.array_equal(np.asarray(sections["z"]), f.z)


def test_换时刻真的换帧(client, sections):
    """Review Focus 1：管线缓存**与时刻无关**，但**场**与时刻强相关。

    这条测试钉的是「场没有被误当作管线一起缓存」：换 `t_index` 必须真的换一批数，
    否则画面上一切正常、数字是上一时刻的，而且不报错。
    """
    other = client.get("/api/field/sections", params={"t_index": 13}).json()
    a = sections["sheds"][0]["values"]
    b = other["sheds"][0]["values"]
    assert a != b, "t_index 从 12 换到 13，第一个棚的场一模一样 —— 时刻被缓存掉了"


def test_越界的_t_index_是_400_不是_500(client, sections):
    r = client.get("/api/field/sections", params={"t_index": sections["n_times"]})
    assert r.status_code == 400
    assert "t_index" in r.json()["detail"]


def test_认不出的_preset_是_400(client):
    r = client.get("/api/field/sections", params={"preset": "ultra"})
    assert r.status_code == 400
    assert "preset" in r.json()["detail"]


CURVE_POINT = {"shed": "p1", "x": 0.80, "z": 1.10}    # 正好是一个实测点位


def test_曲线的形状与状态码(client):
    r = client.get("/api/field/curve", params=CURVE_POINT)
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("shed", "x", "y", "z", "label", "n_times", "time", "values",
              "defined", "note"):
        assert k in body, f"载荷少了 {k}"
    assert body["shed"] == "p1"
    assert body["y"] == 3.0
    assert len(body["time"]) == body["n_times"]
    assert len(body["values"]) == body["n_times"]
    assert body["defined"] is True


def test_曲线的口径写明了没有竖直软单调投影(client):
    """Review Focus 3：单点没有竖直邻点，所以这条曲线天生不含软投影。

    实现里偷偷投影一下（只能靠编一个邻点）就是造数；图上不写清楚就是撒谎。
    这条测试钉的是**载荷里自带那句口径** —— 界面上要显示的就是它。
    """
    note = client.get("/api/field/curve", params=CURVE_POINT).json()["note"]
    assert "没有" in note and "竖直" in note and "投影" in note, (
        f"曲线的口径没写清楚：{note!r}"
    )


def test_拱外的点返回全_null_且_defined_是假(client):
    """拱外的点「无定义」—— 不是一个特别低或特别高的数，是**没有数**。"""
    body = client.get("/api/field/curve",
                      params={"shed": "p1", "x": 2.05, "z": 1.30}).json()
    assert body["defined"] is False
    assert all(v is None for v in body["values"])
    assert len(body["values"]) == body["n_times"]


def test_无测量带里的点也返回全_null(client):
    """z > 1.10 m 的带里**有**外推值，但那个数没有实测支撑，单点查询不报。

    这一段与切面图上的斜纹是同一条口径的两种呈现。
    """
    body = client.get("/api/field/curve",
                      params={"shed": "p1", "x": 1.00, "z": 1.25}).json()
    assert body["defined"] is False
    assert all(v is None for v in body["values"])


def test_曲线与后端库逐位相等(client):
    """与 Task 2 同一条判据：后端库是唯一的 oracle。

    ⚠️ 这里**必须**用 `predict_points` 一次算完，不能写成
    「for t in range(n_times): field_at(...)」—— 那是 1308 次完整的二维场构建。
    """
    from api.deps import get_pipeline

    body = client.get("/api/field/curve", params=CURVE_POINT).json()
    pipe = get_pipeline()
    coords = np.array([[body["x"], body["y"], body["z"]]], dtype=float)
    want = pipe.predict_points(coords, np.arange(body["n_times"])).reshape(-1)
    for i, got in enumerate(body["values"]):
        assert got == float(want[i]), f"t={i}: 接口 {got!r} != 库 {float(want[i])!r}"


def test_认不出的棚是_400(client):
    r = client.get("/api/field/curve", params={"shed": "p9", "x": 1.0, "z": 0.5})
    assert r.status_code == 400
    assert "shed" in r.json()["detail"]
