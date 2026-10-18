"""实时模式的数据源：`configs/live/live.xlsx` 那 144 帧 + 它自己的那份管线。

**为什么是模块级单例**：与 `deps` 的两个缓存同形（`_CACHE` / `_PIPELINES` 加
`reset_cache()`）。测试要能像 `monkeypatch deps.get_pipeline` 那样把整条路径
换成会炸的替身 —— 挂在 `app.state` 上的话，每个测试都得先拿到一个 app 实例。

**为什么它自己的管线实例不进 `PipelineCache`**：`PipelineCache.key_of` 是

    (ds.signature, groups_signature(groups), bundle.created_at)

**里面没有「帧数」**。往缓存里那个共享实例上 append，键一个字节都不变 ——
训练模式的路由会照样命中这个被改过的对象，而且不报任何错。这正是本项目
从第一天就在防的那类错。

**为什么不启后台线程**：cursor 是 `(started_at, now)` 的纯函数，
所以它是确定的、可注入时钟的、可重放的。唯一的副作用是 append，
而那是单调且幂等的。
"""
from __future__ import annotations

import time
from typing import Callable

import pandas as pd

from tfield import config as C
from tfield.calibration import groups_signature

from . import deps

#: 一帧 300 秒 —— 就是数据集的采样间隔。**不加速**：加速等于把「5 分钟一帧」
#: 这件事演成假的，而这一屏要演的正是「数据一帧一帧来」。
LIVE_INTERVAL_S: float = 300.0

#: cursor 的浮点容差。重基写的是 `started_at = now − 300 × n`，
#: 过一轮加减之后可能落成 `n × 300 − 5.7e-14`，`//` 就给出 n − 1 ——
#: 界面上表现为「点了下一帧，没动」。
_CURSOR_EPS = 1e-6


class LiveSource:
    def __init__(self, *, clock: Callable[[], float] = time.time,
                 builder=None) -> None:
        self._clock = clock
        self._builder = builder or deps._build_pipeline
        self._frames: pd.DataFrame | None = None
        #: 训练段长度。`prepare` 里量一次 —— 实时帧接在时间轴尾部，
        #: 第 n 帧的 t_index 是 `_t0 + n`（见 `t_index_of`）。
        self._t0: int | None = None
        self.pipeline = None
        self.started_at: float | None = None
        self.running = False
        self.cursor_frozen = 0

    # ── 留出段 ──
    def frames(self) -> pd.DataFrame:
        if self._frames is None:
            #: 2026-10-16 起读页⑤ **自己的**那份（`configs/live/live.xlsx`），
            #: 不再是「当前数据集切出来的留出段」。
            self._frames = deps.live_playback_dataset().wide
        return self._frames

    @property
    def total(self) -> int:
        return int(len(self.frames()))

    def frame(self, n: int) -> pd.Series:
        return self.frames().iloc[n]

    def sensor_temps(self, n: int) -> list[float]:
        """第 n 帧的 24 路棚温，**次序与 `Dataset.sensor_ids()` 一致**
        （p1 的 8 个位置，然后 p2、p3）—— 与 `_resid_matrix` 的行、`fs.coords`
        的行是同一套序。三处不同序就会静默地把 A 测点的读数贴到 B 测点上。
        """
        row = self.frame(n)
        return [float(row[C.sensor_columns(shed, pos)[0]])
                for shed in C.SHED_ORDER for pos in C.SENSOR_LAYOUT]

    # ── 状态 ──
    @property
    def state(self) -> str:
        return "ready" if self.pipeline is not None else "idle"

    def cursor(self) -> int:
        """现在走到第几帧。**纯读**：不 append、不建管线。"""
        if not self.running or self.started_at is None:
            return int(self.cursor_frozen)
        elapsed = self._clock() - self.started_at
        return max(0, min(self.total - 1,
                          int((elapsed + _CURSOR_EPS) // LIVE_INTERVAL_S)))

    def _rebase(self, n: int) -> None:
        """让纯函数立刻算出 n：`elapsed = n × 300`。"""
        self.cursor_frozen = int(n)
        self.started_at = self._clock() - int(n) * LIVE_INTERVAL_S

    # ── 动作 ──
    def prepare(self) -> float:
        """建实时源自己的管线。幂等；再来一次直接返回 0.0。

        **同步的**，几十秒。慢是刻意的：它换来的是这条路径可测
        （没有线程、没有「等它好」的轮询）。

        ⚠️ 取哪一份模型走 `deps.current_bundle()` —— 与页③ 同一条判定。
        拟合轴是 `configs/live/train.xlsx`（切点之前那 1164 行），与页③ 的
        训练段**行数相同、测点字典逐字相同**，所以 `groups_signature` 相同 →
        `compatible` 相同；对不上的只剩数据集那一轴（`borrowed`），而那一个
        只是标签、不是闸门。**那句标签在页⑤ 上要抹掉**（理由见下面那几行）。
        """
        if self.pipeline is not None:
            return 0.0
        t0 = self._clock()
        # 拟合轴是**切点之前那 1164 行**那份文件，整份读，不再切。
        ds = deps.live_train_dataset()
        groups = tuple(C.DEFAULT_FEATURE_GROUPS)
        # ⚠️ 把 `ds` 传进去：页⑤ 用的不是「当前数据集」切出来的训练段，而
        # `current_bundle()` 的默认轴是后者。
        bundle = deps.current_bundle(groups, ds=ds).bundle
        self.pipeline = self._builder(ds, groups, bundle)
        # ⚠️ 「借来的」那句话在页⑤ 上**永远是亮的**，所以它在页⑤ 上是零信息：
        # `deps._borrowed()` 比的是包的 `dataset_sig` 与**当前数据集**的指纹，而
        # 页⑤ 没有「当前数据集」—— 它的轴是 `configs/live/train.xlsx`，一个和
        # 交付包不在同一台机器、同一次导出里产生的文件，指纹逐机、逐次都不同。
        # 那两句话说的其实是同一批 1164 行，标成「不是用这份数据标的」是错的。
        # 规格书 §五 也写着「`borrowed` 只是标签（且页⑤ 不显示它）」。
        # `calibrated` / `artifact_note` **不动**：它们是页⑤ 真要看的。
        self.pipeline.mismatch_note = ""
        # 训练段长度：此刻还没有任何实时帧（`n_live == 0`），所以 `n_times` 就是它。
        self._t0 = self.pipeline.n_times
        return max(0.0, self._clock() - t0)

    def t_index_of(self, n: int) -> int:
        """留出段第 n 帧在**管线时间轴**上的下标。

        ⚠️ **不是 n。** 实时帧接在训练段**尾部**，所以第 0 帧是 1164
        （规格书 §三：实时帧的 `t_index` 落在 1164..1307）。拿 n 直接当
        `t_index` 不会报错 —— 时间轴长度对得上、载荷形状也对 —— 只是屏幕上的
        场取到了**训练段的第 n 帧**，而 `frame.time` 写的是留出段那一帧的时间。
        两半各自看着都对，合起来差着一段时间。
        """
        self._require_ready()
        return int(self._t0) + int(n)

    def advance_to(self, n: int) -> int:
        """把缺的帧按序补到第 n 帧，**返回它在时间轴上的 `t_index`**。
        单调、幂等：往回退是空操作，同一帧不会接两次。

        返回 `t_index` 而不是 None：调用方要拿它去 `sections_payload`，
        而这一步只有实时源自己知道（`t_index_of`）。
        """
        pipe = self._require_ready()
        if n >= self.total:
            raise ValueError(f"第 {n} 帧不在留出段里（共 {self.total} 帧）")
        while pipe.n_live <= n:
            k = pipe.n_live
            row = self.frame(k)
            pipe.append_live_frame(
                bg_temp=float(row[C.BG_TEMP]),
                bg_rh=float(row[C.BG_RH]),
                bg_light=float(row[C.BG_LIGHT]),
                ts=pd.Timestamp(row[C.COL_TIMESTAMP]),
                sensor_temps=self.sensor_temps(k),
            )
        return self.t_index_of(n)

    def start(self, from_n: int | None = None) -> None:
        self._require_ready()
        if from_n is not None:
            if not 0 <= int(from_n) < self.total:
                raise ValueError(f"from_n 越界：{from_n}（留出段共 {self.total} 帧）")
            self.advance_to(int(from_n))
            self._rebase(int(from_n))
        self._rebase(self.cursor())
        self.running = True

    def pause(self) -> None:
        self.cursor_frozen = self.cursor()
        self.running = False

    def next_frame(self) -> int:
        """手动前进一格。**暂停时也精确前进一格**（重基之后纯函数给出 n+1）。"""
        self._require_ready()
        cur = self.cursor()
        if cur >= self.total - 1:
            raise ValueError(f"已经是最末帧（第 {cur} 帧）")
        nxt = cur + 1
        self._rebase(nxt)
        return nxt

    def _require_ready(self):
        if self.pipeline is None:
            raise RuntimeError("实时源还没准备好，先 POST /api/live/prepare")
        return self.pipeline


_SOURCE: LiveSource | None = None


def get_live_source() -> LiveSource:
    global _SOURCE
    if _SOURCE is None:
        _SOURCE = LiveSource()
    return _SOURCE


def reset_live_source() -> None:
    """丢掉实时源（连同它那份管线）。**只给测试用。**

    ⚠️ 2026-10-16 起它**不再**登记进 `deps._INVALIDATORS`：实时源的输入是
    `configs/live/` 两个固定文件 + 当前模型包，与「当前数据集」无关。留着登记
    会带来一个**假的**副作用 —— 演示到一半有人在页① 导一份数据集，页⑤ 当场
    被打回 idle，而那次导入对页⑤ 什么都没改变。
    """
    global _SOURCE
    _SOURCE = None
