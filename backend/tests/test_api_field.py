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
