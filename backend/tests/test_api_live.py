"""实时模式：实时源、走帧的纯函数、七条接口。

⚠️ **时钟是注入的**。cursor 是 `(started_at, now)` 的纯函数，注入之后
「走 5 分钟前进一帧」这种断言是确定的 —— 不用 sleep、不用等线程。
这个文件里没有一个 `time.sleep`。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from api import deps, live
from tfield import config as C
from tfield.data.loader import HOLDOUT_CUTOFF, load_dataset, test_data_path

pytestmark = pytest.mark.skipif(not test_data_path().exists(),
                                reason="数据集不在（与 test_acceptance.py 同一口径）")


class FakeClock:
    """可以手推的时钟。`advance(seconds)` 就是「过了这么久」。"""

    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def src(clock) -> live.LiveSource:
    return live.LiveSource(clock=clock)


@pytest.fixture(autouse=True)
def _library(current_model, monkeypatch):
    """这一整个文件都要求模型库里存着交付那一份模型（见 `tests/conftest.py`）。

    2026-10-08 起 `LiveSource.prepare()` 与页③ 走**同一条判定**
    （`deps.current_bundle()`），而本文件里凡是要 `prepare()` 的用例都因此
    要读一次库。库空着也不报错 —— `prepare()` 会拿兜底参数把管线建起来、
    场照样画得出来，只是参数不是标定出来的那一套；`test_验收折_接口的数与
    直接调库逐位相等` 那条正好会因为这个差距而红，其余的会静默地测错东西。

    ⚠️ 它同时把「当前数据集」指过去：`src` 夹具是**函数级、不走 autouse**，
    而 `LiveSource.prepare()` 要经 `deps.get_train_dataset()`，那条路在指针
    为空时抛 `NoDatasetError`。本文件没有别的夹具设它。
    """
    from api import paths
    deps.set_current_dataset(paths.dataset_path())
    return current_model


def test_没准备之前_status_字段是_idle_且不动管线(src, monkeypatch):
    """**status 是纯读。** 把「建管线」那条路径换成会炸的替身，它也必须照样答得出来。

    这条守的是一件真事：页面上每 5 秒问一次 status，而建管线要几十秒 ——
    status 一旦顺手把管线建起来，「切到实时页看一眼就走」的人会等几十秒。

    ⚠️ **替身必须打在 `deps` 上，不能打在 `live.LiveSource._builder` 上。**
    `_builder` 在 `__init__` 里就已经绑进了实例（`self._builder = builder
    or deps._build_pipeline`），而 `src` 夹具先于这条 monkeypatch 跑完 ——
    打在类上对已经构造好的实例一点作用都没有，那条守卫会变成「看着像在守，
    其实什么也没守」。（`state` / `cursor` / `total` 本来也不碰 `_builder`，
    所以打错了照样绿，错得无声无息。）
    """
    def boom(*a, **k):
        raise AssertionError("status 不该去建管线")

    monkeypatch.setattr(deps, "get_train_dataset", boom)
    monkeypatch.setattr(deps, "_build_pipeline", boom)
    monkeypatch.setattr(deps, "get_pipeline", boom)
    assert src.state == "idle"
    assert src.cursor() == 0
    assert src.total == 144
    assert src.pipeline is None


def test_走帧是纯函数_五分钟一帧(src, clock):
    src.prepare()
    src.start()
    assert src.cursor() == 0
    clock.advance(299.0)
    assert src.cursor() == 0
    clock.advance(1.0)          # 满 300 s
    assert src.cursor() == 1
    clock.advance(300.0 * 5)
    assert src.cursor() == 6
    clock.advance(300.0 * 1_000)      # 走过头
    assert src.cursor() == src.total - 1 == 143


def test_暂停冻结_开始重基(src, clock):
    src.prepare()
    src.start()
    clock.advance(300.0 * 4 + 10.0)
    n = src.cursor()
    src.pause()
    clock.advance(300.0 * 10)
    assert src.cursor() == n, "暂停之后时钟还在推着 cursor 走"
    src.start()
    clock.advance(300.0)
    assert src.cursor() == n + 1, "开始应当从冻结的那一帧接着走"


def test_下一帧在暂停时也精确前进一格(src, clock):
    """暂停之后 `next_frame()` 必须**精确**前进一格：一次一格，不是零格。

    差一格在界面上表现为「点了下一帧，没动」—— 而这一屏的全部动作就是「点下一帧」。

    ⚠️ 暂停时读数走的是 `cursor_frozen`，**不经过浮点**（`running=False` 直接返回
    冻结值），所以这条**钉不住** `_CURSOR_EPS`。钉它的是下一条
    `test_时钟往回跳一丝_帧号不许倒退`。
    """
    src.prepare()
    src.start()
    clock.advance(300.0 * 3 + 7.0)
    n = src.cursor()
    src.pause()
    assert src.next_frame() == n + 1
    assert src.next_frame() == n + 2
    assert src.cursor() == n + 2


def test_时钟往回跳一丝_帧号不许倒退(src, clock):
    """`time.time()` **不是单调钟** —— NTP 会把墙钟往回拨，而它正是生产用的那个钟。

    回拨一丝（小于 `_CURSOR_EPS`）就会让 `//` 把第 n 帧算成第 n−1 帧，
    界面上表现为帧号自己退了一格。

    ⚠️ **这条钉的就是 `_CURSOR_EPS`**：把 `cursor()` 里的 `+ _CURSOR_EPS` 去掉，
    这里会红（实测 `1199.9999999 // 300 = 3.999999999`，取整就是 3）。
    """
    src.prepare()
    src.start()
    clock.advance(300.0 * 4)          # 正好踩在第 4 帧的边界上
    assert src.cursor() == 4
    clock.t -= 1e-7                   # 时钟往回拨了一丝
    assert src.cursor() == 4, "时钟往回一丝就让帧号倒退了一格"


def test_重复推进到同一帧是幂等的(src):
    """`frame/{n}` 与 `volume/{n}` 各走一遍 —— 同一帧不许接两次。

    接两次不会报错，只会让时间轴悄悄变长、帧号全体错位。
    """
    src.prepare()
    src.advance_to(5)
    n_live = src.pipeline.n_live
    src.advance_to(5)
    src.advance_to(5)
    assert src.pipeline.n_live == n_live == 6


def test_没走到的那一帧接不进来(src):
    """`advance_to` 只往前进：往回退是空操作。"""
    src.prepare()
    src.advance_to(5)
    src.advance_to(2)
    assert src.pipeline.n_live == 6


def test_准备是幂等的_而且只经手自己的那份管线(src, monkeypatch):
    """`n_builds` 不该被实时模式推高 —— 它数的是**缓存自己**建的那几次。"""
    before = deps._PIPELINES.n_builds
    src.prepare()
    first = src.pipeline
    assert src.prepare() == 0.0, "第二次 prepare 应当直接返回"
    assert src.pipeline is first
    assert deps._PIPELINES.n_builds == before


def test_prepare_之后管线是训练段那份(src):
    src.prepare()
    assert src.pipeline.n_times == 1164
    assert src.pipeline.n_live == 0
    assert "-h20260727T1200" in src.pipeline.ds.signature


# ── 七条接口 ──


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import create_app
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _fresh_source():
    """每条用例一个全新的实时源。**必须** —— 实时源是进程内单例，
    上一条用例接进去的帧会留给下一条。"""
    live.reset_live_source()
    yield
    live.reset_live_source()


def test_没准备时_start_next_frame_都报_400_叫你先准备(client):
    """要先准备的是 **start / next / frame** —— 规格书 §五 的失败表逐字列的是这三条。

    ⚠️ **`pause` 不在其中**，这是有意的：它是个幂等的空操作（本来就没在走，
    冻结的就是第 0 帧）。前端在 `idle` 下也渲染暂停按钮、也轮询 status，
    让它报 400 只会逼前端多一层没有信息量的「现在能不能按」。
    """
    for path in ("/api/live/start", "/api/live/next"):
        r = client.post(path)
        assert r.status_code == 400, path
        assert "prepare" in r.json()["detail"]
    r = client.get("/api/live/frame/0")
    assert r.status_code == 400
    assert "prepare" in r.json()["detail"]

    # 反例：没准备时 pause 是空操作，不是错误。
    r = client.post("/api/live/pause")
    assert r.status_code == 200
    assert r.json()["state"] == "idle"
    assert r.json()["running"] is False


def test_status_始终答得出来(client):
    b = client.get("/api/live/status").json()
    assert b == {"state": "idle", "running": False, "cursor": 0,
                 "total": 144, "interval_s": 300.0}


def test_prepare_之后_status_变_ready(client):
    r = client.post("/api/live/prepare")
    assert r.status_code == 200
    b = r.json()
    assert b["state"] == "ready"
    assert b["seconds"] >= 0.0
    assert client.get("/api/live/status").json()["state"] == "ready"


def test_frame_的载荷形状与页3_一样_外加两块(client):
    client.post("/api/live/prepare")
    client.post("/api/live/start")
    b = client.get("/api/live/frame/0").json()
    # 页③ 断面那一屏的字段一个不少
    for key in ("t_index", "time", "n_times", "preset", "vmin", "vmax",
                "x", "z", "arch", "sensors", "sheds", "note"):
        assert key in b, key
    # 帧号 n 与 t_index 是**两套坐标**：n 是留出段下标（0），t_index 是管线
    # 时间轴下标（1164 = 训练段长度 + 0，规格书 §三）。这一条钉住转发，
    # 也钉住「载荷里的场就是这一帧的场」——见下面的时间一致性。
    assert b["t_index"] == 1164, "实时帧接在训练段尾部，第 0 帧的 t_index 是 1164"
    assert b["n_times"] == 1165, "1164 训练段 + 1 接进来的（frame/0 已经走过一步）"
    # 时间是**空格分隔**的那种：`sections_payload` 里就是 `str(pipe.time_at(...))`
    # （`routes/dataset.py` 用 `.isoformat()` 给的是带 T 的，两处格式不同、各有各的
    # 消费方）。这里跟断面载荷保持一致 —— 下面那条相等断言就靠它。
    assert b["time"] == "2026-07-27 12:00:00"
    # ⚠️ 这两半必须指同一帧：`time` 由 t_index 算、`frame.time` 由留出段那一行算。
    # 转发错一格，这里就是「场画的是 A 帧、标题写的是 A ± 1 帧」。
    assert b["time"] == b["frame"]["time"]
    assert b["frame"]["n"] == 0
    assert set(b["frame"]) == {"n", "time", "bg_temp", "bg_rh", "bg_light", "sensor_temps"}
    assert len(b["frame"]["sensor_temps"]) == 24
    assert set(b["live"]) == {"cursor", "running", "interval_s", "total"}
    assert b["live"]["total"] == 144


def test_没走到的帧报_400_而且不悄悄拿当前帧顶替(client):
    client.post("/api/live/prepare")
    client.post("/api/live/start")
    client.get("/api/live/frame/0")          # 走到第 0 帧
    r = client.get("/api/live/frame/5")
    assert r.status_code == 400
    assert "5" in r.json()["detail"]
    assert client.get("/api/live/status").json()["cursor"] == 0, "被拒的请求把 cursor 推走了"


def test_同一帧走两条路由不重复接帧(client):
    """`frame/{n}` 与 `volume/{n}` 各自都会 `advance_to(n)` —— 幂等性破了
    就是同一帧接两次，时间轴悄悄变长、帧号全体错位，而且都看起来正常。

    ⚠️ **不比两边的数值**：断面给的是三个棚在 y = 3 / 9 / 15 的网格，
    体网格给的是 y = 0 / 6 / 12 / 18 那些片（`y_step=6` 时不落在棚位上）。
    两个数本来就不该相等 —— 拿它们相等当断言是错的。
    """
    client.post("/api/live/prepare")
    # ⚠️ **不能只 start()**：cursor 是 floor((now − started_at) / 300)，而测试里
    # 两个时刻是同一瞬间 —— start 之后 cursor 恒为 0，frame/2 会直接被顶回 400。
    # 用 from_n 直接落到第 2 帧（规格书 §五：`from_n` 可选）。
    client.post("/api/live/start", params={"from_n": 2})
    f = client.get("/api/live/frame/2").json()
    v = client.get("/api/live/volume/2?y_step=6.0").json()
    assert f["t_index"] == v["t_index"] == 1166, "第 2 帧 → 时间轴上的 1164 + 2"
    assert f["time"] == v["time"]
    assert f["frame"]["time"] == v["frame"]["time"]
    assert client.get("/api/live/status").json()["cursor"] == 2
    assert live.get_live_source().pipeline.n_live == 3, "同一帧被接了不止一次"


def test_验收折_接口的数与直接调库逐位相等(client):
    """照上篇 §八 的口径：**后端库是唯一的 oracle**。

    实时路由只是「校验 + 走帧 + 调 `sections_payload`」—— 它一个数都不许自己算。
    """
    from tfield import config as C
    from tfield.calibration import load_for
    from tfield.features import build_features
    from tfield.pipeline import FieldPipeline
    from api import deps, paths
    from api.live import LiveSource
    from api.routes.field import sections_payload

    client.post("/api/live/prepare")
    client.post("/api/live/start", params={"from_n": 3})   # 同上：真时钟推不动 cursor
    body = client.get("/api/live/frame/3").json()

    ds = deps.get_train_dataset()
    train_n = len(ds.wide)                     # 训练段长度：实时帧接在它后面
    cfg = load_for(ds, tuple(C.DEFAULT_FEATURE_GROUPS), paths.CONFIGS).config()
    pipe = FieldPipeline(cfg, ds).fit(build_features(ds, C.DEFAULT_FEATURE_GROUPS), ds)
    src = LiveSource()
    for k in range(4):
        pipe.append_live_frame(
            bg_temp=float(src.frame(k)[C.BG_TEMP]), bg_rh=float(src.frame(k)[C.BG_RH]),
            bg_light=float(src.frame(k)[C.BG_LIGHT]),
            ts=pd.Timestamp(src.frame(k)[C.COL_TIMESTAMP]),
            sensor_temps=src.sensor_temps(k))
    # `calibrated` 是 **API 层**的注记（`deps._build_pipeline` 打的），不是库的性质 ——
    # 这个 oracle 走的是库本身，得自己打上同一个记号，否则比的是注记不是数。
    pipe.calibrated = True
    mine = sections_payload(pipe, t_index=train_n + 3, preset="standard", monotonic=True)

    # 接口在断面载荷之外**只**多这两块（规格书 §五）。先钉住「只多这两块」，
    # 再用逐位相等钉住共有那部分 —— 直接 `mine == body` 会因为多出来的块而红，
    # 那条断言的实际内容是「接口没多塞东西」，不是「数一样」。
    assert set(body) - set(mine) == {"frame", "live"}
    for k in ("frame", "live"):
        body.pop(k)
    assert mine == body


def test_实时源不污染共享管线(client):
    """共享管线（训练模式的路由用的那一份）一个字节都不许变。"""
    deps.reset_cache()
    before = deps.get_pipeline().n_live
    client.post("/api/live/prepare")
    client.post("/api/live/start", params={"from_n": 4})   # 同上：真时钟推不动 cursor
    client.get("/api/live/frame/4")
    assert deps.get_pipeline().n_live == before == 0
    assert deps._PIPELINES.n_builds == 1, "实时源进了缓存"


def test_next_在末帧报_400(client, monkeypatch):
    client.post("/api/live/prepare")
    src = live.get_live_source()
    src.pause()
    src._rebase(src.total - 1)
    r = client.post("/api/live/next")
    assert r.status_code == 400
    assert "最末帧" in r.json()["detail"]


def test_start_的_from_n_越界报_400(client):
    client.post("/api/live/prepare")
    assert client.post("/api/live/start", params={"from_n": 144}).status_code == 400
    assert client.post("/api/live/start", params={"from_n": -1}).status_code == 400


def test_pause_是幂等的(client):
    client.post("/api/live/prepare")
    client.post("/api/live/start")
    assert client.post("/api/live/pause").json()["running"] is False
    assert client.post("/api/live/pause").json()["running"] is False


@pytest.fixture
def raw_client():
    """**不把服务端异常抛给调用方**的客户端。

    默认的 `TestClient` 是 `raise_server_exceptions=True`：未翻译的异常会从
    `client.get(...)` 那一行**直接抛出来**，于是「用户实际收到什么」根本看不见 ——
    用户收到的是 500。要断言 400 / 500 这种状态码，必须关掉它。
    """
    from fastapi.testclient import TestClient
    from api.main import create_app
    return TestClient(create_app(), raise_server_exceptions=False)


def test_读数坏时是显式报错不是_500(raw_client, monkeypatch):
    """规格书 §七 最后两行：实时段读数坏（缺列 / 非数）**照 `check_sensor_columns`
    的规矩显式报错**。

    `append_live_frame` 对非有限读数、乱序 / 重复时间戳、路数不对一律抛
    `ValueError`（那是库的规矩，对）。但它在路由层没有被翻译过，于是冒到 FastAPI
    就是 **500** —— 界面上是一句「服务器内部错误」，而不是
    「第 3 帧的时间戳比时间轴尾巴早」。数据集实测零缺失，所以这是纯守卫路径；
    守卫路径的报错方式也只有在这里才钉得住（把 `advance_to` 换成会抛的替身，
    真数据到不了的那条分支才走得进来）。
    """
    raw_client.post("/api/live/prepare")
    raw_client.post("/api/live/start")

    def boom(n: int) -> int:
        raise ValueError("第 3 帧的时间戳比时间轴尾巴早")

    monkeypatch.setattr(live.get_live_source(), "advance_to", boom)

    for path in ("/api/live/frame/0", "/api/live/volume/0"):
        r = raw_client.get(path)
        assert r.status_code == 400, path
        assert "时间戳" in r.json()["detail"], path



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
