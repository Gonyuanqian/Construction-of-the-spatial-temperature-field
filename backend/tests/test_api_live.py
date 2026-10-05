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
