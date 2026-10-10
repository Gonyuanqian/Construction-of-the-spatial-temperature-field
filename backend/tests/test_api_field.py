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


@pytest.fixture(scope="module", autouse=True)
def _library(library_module):
    """这一整个模块都要求模型库里存着交付那一份模型（见 `tests/conftest.py`）。

    ⚠️ **必须是 module 级。** 下面那个 `sections` 夹具也是一次真实请求的
    响应体，整个模块拿它当基准比；pytest 先建大作用域的夹具，函数级的
    `current_model` 跑得太晚 —— 它会拿到**空库**建出的载荷（兜底参数那一份，
    与标定那份**同折族、不同参数**），而模块里每一条都在拿这个载荷比。
    """
    return library_module


@pytest.fixture(scope="module")
def sections(client):
    r = client.get("/api/field/sections", params={"t_index": 12})
    assert r.status_code == 200, r.text
    return r.json()


def test_形状与状态码(sections):
    for k in ("t_index", "time", "n_times", "preset", "monotonic", "calibrated",
              "mismatch_note",
              "vmin", "vmax", "max_measured_z", "x_min", "x_max", "z_max",
              "x", "z", "arch", "sensors", "sheds", "note"):
        assert k in sections, f"载荷少了 {k}"
    assert sections["t_index"] == 12
    # 这个模块的库是交付那一份（`library_module`），也就是**为这份数据标的** ——
    # 那句「借来的」的话必须是空串（三个状态：没模型 / 本地的 / 借来的）。
    assert sections["mismatch_note"] == "", sections["mismatch_note"]
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


def test_对比的形状与状态码(client):
    r = client.get("/api/field/compare", params={"shed": "p1", "t_index": 12})
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("shed", "y", "t_index", "time", "n_times", "preset", "x", "z",
              "arch", "sensors", "max_measured_z", "before", "after", "delta",
              "stripes", "vmin", "vmax", "delta_vmax", "light", "gate_open",
              "gate_label", "identical", "note"):
        assert k in body, f"载荷少了 {k}"
    assert body["y"] == 3.0
    assert len(body["before"]) == len(body["after"]) == len(body["delta"])


def test_白天两张图确实不同(client):
    """反过来的一天：门禁开着时，软投影必须真的动了这个场。

    要是「开」与「关」算出来一模一样，那这个门禁就没在做事，
    而第四格会是一整片零 —— 看起来像是「约束很温和」。
    """
    body = client.get("/api/field/compare", params={"shed": "p1", "t_index": 12}).json()
    assert body["light"] > 0
    assert body["gate_open"] is True
    assert body["identical"] is False
    assert body["delta_vmax"] > 0


def test_夜里两张图逐位相同(client):
    """spec §七 V5：门禁关闭时两张图**逐位相同** —— 图上照实说。

    没有这一步，「夜里不变」就只是 docstring 里的一句话。
    """
    from api.deps import get_pipeline
    from tfield.field.constraints import light_at

    pipe = get_pipeline()
    n_times = int(pipe.ds.wide.shape[0])
    night = next((t for t in range(n_times) if light_at(pipe, t) == 0.0), None)
    assert night is not None, (
        "这 5 天里一个无光照的时刻都没有 —— 门禁「关」的那一态就没被测到"
    )

    body = client.get("/api/field/compare",
                      params={"shed": "p1", "t_index": int(night)}).json()
    assert body["light"] == 0.0
    assert body["gate_open"] is False
    assert body["identical"] is True
    assert body["delta_vmax"] == 0.0
    assert body["gate_label"] == "关（无光照，严格不变）"
    assert body["before"] == body["after"], "夜里两张图不一样 —— 门禁没关上"


def test_delta_是约束前减约束后(client):
    """签号方向要在后端定死、在界面上写清。定在界面上的话，两处迟早不一致。"""
    body = client.get("/api/field/compare", params={"shed": "p1", "t_index": 12}).json()
    changed = 0
    for iz, row in enumerate(body["delta"]):
        for ix, d in enumerate(row):
            b, a = body["before"][iz][ix], body["after"][iz][ix]
            if b is None or a is None:
                assert d is None, f"({ix},{iz}) 场是 null，delta 却不是"
                continue
            assert d == b - a, f"({ix},{iz}): delta {d!r} != before-after {b - a!r}"
            if d != 0:
                changed += 1
    assert changed > 0, "白天居然一格都没变"


def test_before_after_与切面图逐位相同(client, sections):
    """**第四格画的必须就是第一格那片场。**

    `field_at` 在 y 恰好等于某个棚的 y 时会短路到该断面（build.py:139-142），
    所以 `compare` 的 before/after 与 `sections` 的对应格**逐位相等**。
    两个面板画同一片场却各不相同，是最难查的一类错 —— 这条把它焊死。
    """
    t = sections["t_index"]
    off = client.get("/api/field/sections",
                     params={"t_index": t, "monotonic": False}).json()
    on = client.get("/api/field/sections",
                    params={"t_index": t, "monotonic": True}).json()
    cmp = client.get("/api/field/compare", params={"shed": "p1", "t_index": t}).json()

    cell_off = next(s for s in off["sheds"] if s["shed"] == "p1")["values"]
    cell_on = next(s for s in on["sheds"] if s["shed"] == "p1")["values"]
    assert cmp["before"] == cell_off, "第四格的「约束前」与切面图对不上"
    assert cmp["after"] == cell_on, "第四格的「约束后」与切面图对不上"


def test_delta_的范围是对称的(client):
    """发散色标的中点必须在 0。不对称的话「没变」会被画成一个有颜色的格子。"""
    body = client.get("/api/field/compare", params={"shed": "p1", "t_index": 12}).json()
    m = body["delta_vmax"]
    assert m >= 0
    for row in body["delta"]:
        for d in row:
            if d is not None:
                assert -m - 1e-12 <= d <= m + 1e-12


def test_拱外是_null_且接口是_200(client):
    """与 Task 2 同一条：`allow_nan=False` 会把 NaN 变成 500。"""
    body = client.get("/api/field/compare", params={"shed": "p1", "t_index": 12}).json()
    assert any(v is None for row in body["before"] for v in row)


def test_对比的越界参数也是_400(client, sections):
    assert client.get("/api/field/compare",
                      params={"shed": "p1", "t_index": sections["n_times"]}).status_code == 400
    assert client.get("/api/field/compare",
                      params={"shed": "p1", "preset": "ultra"}).status_code == 400



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
