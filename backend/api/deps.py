"""进程内的依赖：数据集缓存与管线缓存。

**为什么必须有**
    `load_dataset()` 读那个 1308 × 52 的 xlsx，实测 **0.96–1.00 秒**
    （三个全新进程各冷加载一次），没有任何缓存。
    页① 要打四个接口，一个都不缓存就是「打开一页等三四秒」。
    这是服务端问题 —— HTTP 无状态，每个请求重建一次数据集不可行。

**缓存键是什么**
    数据集的**文件身份** = (绝对路径, mtime_ns, 大小)，与 `dataset_signature`
    用的是同一组要素，但用途不同：签名回答「这个标定包属于谁」，
    这里回答「这份内存对象还对得上盘上的文件吗」。
    用户重新导出一次数据集 → mtime 与大小变 → 键变 → 自动重新加载，**不需要手动失效**。

    ⚠️ 不能拿 `Dataset` 自己当键：它是 frozen dataclass，但字段里有 DataFrame，不可哈希。

**为什么加锁**
    FastAPI 的同步端点跑在线程池里，两个请求可以同时到。
    锁保证「同一个文件只加载一次」这句话在并发下也成立 ——
    而且后到的那个线程**等前面那个装完就直接命中**，不是白等。
"""
from __future__ import annotations

import pathlib
import threading
from typing import Callable

import pandas as pd

from tfield.calibration import groups_signature, load_for
from tfield.data.loader import HOLDOUT_CUTOFF, Holdout, load_dataset, split_holdout
from tfield.data.types import Dataset
from tfield.features import build_features
from tfield.pipeline import FieldPipeline, PipelineConfig

from .errors import NoDatasetError

Capacity = int
FileKey = tuple[str, int, int]


class DatasetCache:
    """按文件身份缓存 Dataset。容量默认 4（一个演示里最多来回切几个数据集）。"""

    def __init__(self, *, loader: Callable[[pathlib.Path], Dataset] | None = None,
                 capacity: Capacity = 4) -> None:
        self._loader = loader or load_dataset
        self._capacity = int(capacity)
        # dict 保插入序 —— LRU 就靠这个：命中时 pop 再塞回去（提到队尾）
        self._items: dict[FileKey, Dataset] = {}
        self._lock = threading.Lock()
        self.n_loads = 0                 # 测试用它证明「真的只加载了一次」

    @staticmethod
    def key_of(path: pathlib.Path | str) -> FileKey:
        """文件的身份。文件不存在时**让它抛 FileNotFoundError** —— 路由层负责翻成 404。"""
        p = pathlib.Path(path)
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size)

    def get(self, path: pathlib.Path | str) -> Dataset:
        key = self.key_of(path)          # 先 stat（在锁外）：不存在就直接抛，不占锁
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items[key] = self._items.pop(key)      # 命中即提到队尾
                return hit

            # 加载放在锁里：并发时第二个线程等在这里，醒来就命中，
            # 不会出现「两个线程各 load 一遍」。
            ds = self._loader(pathlib.Path(path))
            self._items[key] = ds
            while len(self._items) > self._capacity:
                self._items.pop(next(iter(self._items)))     # 淘汰最久未用的
            self.n_loads += 1
            return ds


# ══════════════════════════ 管线缓存 ══════════════════════════
#: 管线身份 = (数据集签名, 特征组签名, 标定包 created_at)。
#: 三者任一变了就是**另一份**管线 —— 少一个维度，换了那份东西还会命中旧管线。
PipelineKey = tuple[str, str, str]

#: 未标定时的哨兵。**不用 None**：None 进不了 JSON 之外的语境也会让 `dict` 的键
#: 类型变成 `str | None`，而「没有包」与「包的空 created_at」本该是同一个键。
NO_BUNDLE = ""


def _mark_calibrated(pipe: FieldPipeline, bundle) -> FieldPipeline:
    """把「配置从哪来」写进管线**自己**身上。

    路由层据此照实标注（spec §七 V3：兜底参数「不是最优，只是不在坏角上」，
    与标定后的数**同折族、不同参数，不可直接比大小**）。写成管线的属性而不是
    一个查询函数，是为了让 `_build_pipeline` 的每条返回路径**不可能忘记**设它 ——
    忘记的后果是界面把兜底的数标成「已标定」，而这正是最不能错的一处标注。
    """
    pipe.calibrated = bundle is not None        # type: ignore[attr-defined]
    return pipe


def _build_pipeline(ds: Dataset, groups: tuple[str, ...], bundle) -> FieldPipeline:
    """未标定走 `PipelineConfig.fallback()`（**不是最优，只是不在坏角上**）。

    这条路在界面上必须标成「未标定」—— 兜底参数与标定后的数**同折族、不同参数**，
    大小不可直接比。
    """
    cfg = bundle.config() if bundle is not None else PipelineConfig.fallback()
    pipe = FieldPipeline(cfg, ds).fit(build_features(ds, groups), ds)
    return _mark_calibrated(pipe, bundle)       # ← 唯一的返回路径


class PipelineCache:
    """按管线身份缓存 `FieldPipeline`。容量默认 4 —— 一个演示里最多来回切几个数据集。

    与 `DatasetCache` 同形是**故意的**：两个缓存的失效规则必须读起来一样，
    否则「为什么这次没生效」会在两个不同的心智模型之间来回甩。
    """

    def __init__(self, *, builder=None, capacity: Capacity = 4) -> None:
        self._builder = builder or _build_pipeline
        self._capacity = int(capacity)
        self._items: dict[PipelineKey, FieldPipeline] = {}
        self._lock = threading.Lock()
        self.n_builds = 0

    @staticmethod
    def key_of(ds: Dataset, groups: tuple[str, ...], bundle) -> PipelineKey:
        return (
            ds.signature,
            groups_signature(groups),
            getattr(bundle, "created_at", None) or NO_BUNDLE,
        )

    def get(self, ds: Dataset, groups: tuple[str, ...], bundle) -> FieldPipeline:
        key = self.key_of(ds, groups, bundle)
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items[key] = self._items.pop(key)      # 命中即提到队尾
                return hit
            # 构建放在锁里：并发时第二个线程等在这里，醒来就命中，
            # 不会出现「两个线程各 fit 一遍」——那不只是浪费，是两次
            # 各要几十秒，前端等到超时。
            pipe = self._builder(ds, groups, bundle)
            self._items[key] = pipe
            while len(self._items) > self._capacity:
                self._items.pop(next(iter(self._items)))
            self.n_builds += 1
            return pipe


_PIPELINES = PipelineCache()


# ══════════════════════════ 当前数据集 ══════════════════════════
#: 「现在在用哪一份」。**只活在内存里**（规格书 §1.3 裁定 A）：不写状态文件，
#: 重启回空态 —— 与「启动时是空态」同一条规则。
#:
#: 为什么不做成 `paths.current_json()`：那会让「重启后屏幕上是什么」不再只由
#: 这次操作决定，而消灭那件事正是这个功能的目的。
_CURRENT: pathlib.Path | None = None


def set_current_dataset(path: pathlib.Path | str) -> None:
    """把「现在在用哪一份」指过去。**不校验文件在不在** —— 那是使用它的人的事。"""
    global _CURRENT
    _CURRENT = pathlib.Path(path)


def current_dataset_path() -> pathlib.Path:
    """现在在用的那一份。空态时抛 `NoDatasetError`（由 `main.py` 翻成 409）。"""
    if _CURRENT is None:
        raise NoDatasetError()
    return _CURRENT


def clear_current_dataset() -> None:
    """打回空态。测试与「重启」用。"""
    global _CURRENT
    _CURRENT = None


def install_dataset(path: pathlib.Path | str) -> None:
    """换数据集：**先清缓存，再改指针**（规格书 §4.2 第 5 步）。

    这两步合成一个函数而不是让调用点各写两行，只有一个理由：
    **顺序写反了不会有任何报错，只会有一个「新指针配旧缓存」的瞬间** ——
    而那一刻恰好是导入成功后的第一个请求。合成一个入口，顺序就不可能写反。

    它也顺手把白名单只撑大一个名字（`api/**` 从 `deps` 取名字受
    `tests/test_routes_use_cache.py` 守着）。
    """
    reset_cache()
    set_current_dataset(path)


#: 换数据集时要作废的**其余东西**的登记处。
#:
#: 四样要一起清（规格书 §三.1）：前三个是 `reset_cache()` 自己管的三个缓存，
#: 第四个是 `api/live.py` 的实时源 —— 它不在这里，而且 `live` 依赖 `deps`，
#: 反过来 import 成环。所以由 `live` 在 import 时**把自己登记进来**。
#:
#: 显式调用（上传路由里写两行）要求**每个未来的调用点**都记得调两次，
#: 而那正是今天这个漏的成因。「换数据集忘了清实时源」在结构上不可能发生，
#: 比「记得调」可靠。
_INVALIDATORS: list[Callable[[], None]] = []


def on_dataset_change(fn: Callable[[], None]) -> None:
    """登记一个「数据集换掉时请作废你自己」的回调。重复登记同一个函数无害。"""
    _INVALIDATORS.append(fn)


def get_pipeline(groups: tuple[str, ...] | None = None) -> FieldPipeline:
    """本项目管线的唯一入口。**路由层不许自己 new FieldPipeline、也不许自己 fit。**

    为什么它能与 `get_dataset` 并列成为 `api.deps` 的第二个出口：
    它**内部先调 `get_train_dataset()`**（而那个又调 `get_dataset()`），
    是数据集缓存的消费者而不是绕过者；
    让它当出口，是为了让「管线只构建一次」这条性质有一个**可计数**的落点
    （`PipelineCache.n_builds`），否则每个路由各 fit 一次，谁也数不出来。

    ⚠️ **它 fit 的是训练段，不是用户交进来的那份文件**（见 `get_train_dataset`）。
    页① 报的那份凭证与这里的世界**故意**不是同一个：模型不许看过留出段。
    """
    from . import paths
    from tfield import config as C
    groups = tuple(C.DEFAULT_FEATURE_GROUPS if groups is None else groups)
    ds = get_train_dataset()          # ← 模型认训练段，页① 认文件
    # 每次请求读一次标定包（794 KB 的 JSON，约 10 ms 量级）——
    # 它的 `created_at` 是键的一部分，不读就不知道键。相对 fit 的几十秒可以忽略。
    bundle = load_for(ds, groups, paths.CONFIGS)
    return _PIPELINES.get(ds, groups, bundle)


_CACHE = DatasetCache()


def get_dataset(path: pathlib.Path | str | None = None) -> Dataset:
    """本项目数据集的唯一入口。**路由层不许直接 import load_dataset。**

    `path=None` 时问「现在在用哪一份」：空态抛 `NoDatasetError`（由 `main.py`
    翻成 409），指针指着盘上没有的文件时抛 `FileNotFoundError`（翻成 404）。

    ⚠️ **这里不再回退到 `paths.dataset_path()`**（曾经是）。那条回退让
    「交付数据集」在启动时自动生效 —— 与规格书 §1.1「不预置、不代劳」
    正相反，而且它**不报错**：界面看起来一切正常，只是用的不是用户导的那一份。
    """
    if path is None:
        path = current_dataset_path()
    return _CACHE.get(path)


def probe_dataset(path: pathlib.Path | str) -> Dataset:
    """**试加载**：只回答「这份文件读不读得成数据集」，**不进任何缓存**。

    上传通道专用。它必须绕开 `_CACHE`，理由是**缓存键在这里从诞生起就是废的**：
    上传时文件还叫 `.<名字>.<pid>.part`，加载完紧接着就改名 ——
    按临时名算出来的 key 指向一个下一毫秒就不存在的路径。
    真放进缓存，它占掉 LRU 的一格，而且永远不可能再被命中。

    ⚠️ 它**不是** `get_dataset()` 的替代品：那个问的是「现在在用的是哪一份」，
    这个问的是「用户刚交上来的这一份能不能用」。两条问题不一样，
    合起来会让「当前数据集」这个指针被一次试加载悄悄改掉。

    为什么写在这里而不是 `api/uploads.py`：本仓有一条源码守卫
    （`tests/test_routes_use_cache.py`）规定 **`load_dataset` 只许出现在
    `api/deps.py`**。把试加载放进 `uploads.py` 就得给那个模块开一张
    整模块的白名单，而这里只需要多一个**点名**的出口。
    """
    return load_dataset(path)


#: 留出切分的缓存。键 = (数据集签名, 切点)。
#:
#: 切一次就是两次 iloc，不贵；记住它是为了让 `get_train_dataset()` 每次返回
#: **同一个** Dataset 对象 —— `PipelineCache` 的键虽然只看签名，
#: 但「同一次会话里训练段是同一份」这件事本身值得成立。
_HOLDOUTS: dict[tuple[str, str], Holdout] = {}


def _holdout(path: pathlib.Path | str | None = None,
             cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> Holdout:
    ds = get_dataset(path)
    key = (ds.signature, str(pd.Timestamp(cutoff)))
    hit = _HOLDOUTS.get(key)
    if hit is None:
        hit = split_holdout(ds, pd.Timestamp(cutoff))
        _HOLDOUTS[key] = hit
    return hit


def get_train_dataset(path: pathlib.Path | str | None = None,
                      cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> Dataset:
    """**模型与构场看得到的世界**：时间轴到 2026-07-27 11:55 为止的 1164 行。

    与 `get_dataset()` **分成两个出口**是这张规格书里唯一一处设计性的决定：

    - `get_dataset()` = 用户交进来的那份文件（页① 认证它）；
    - `get_train_dataset()` = 留出之后剩下的训练段（模型与场只用它）。

    合成一个出口的话，页① 会报「宽表 1164 × 52」却带着 `n_rows = 1308`
    的修复报告 —— 一份自相矛盾的凭证，而页① 的全部职责就是出自洽的凭证。
    """
    return _holdout(path, cutoff).train


def get_live_frames(path: pathlib.Path | str | None = None,
                    cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> pd.DataFrame:
    """**留出段**：实时模式一帧一帧接进时间轴的那 144 行（时间升序）。"""
    return _holdout(path, cutoff).live


def reset_cache() -> None:
    """换数据集之后（上传、重新导出）显式清一次。**三个缓存一起清，再叫所有登记者作废自己。**

    只清数据集不清管线是最坏的组合：数据集重读了，管线还是按旧数据 fit 出来的，
    于是「数据被替换就重标」整条防线失效，而 `n_loads` 会显示「确实重读了」——
    一条看起来正常的错。

    ⚠️ 重建 `_CACHE` / `_PIPELINES` 是**换对象**不是 `clear()`：计数守卫
    （`test_end_to_end.py`）替换的是 `deps._CACHE` 这个模块属性，`clear()`
    会让它替换过的那个对象被清空、而模块属性还指着旧对象。
    """
    global _CACHE, _PIPELINES
    _CACHE = DatasetCache()
    _PIPELINES = PipelineCache()
    _HOLDOUTS.clear()      # 切分结果挂着旧的 Dataset 对象，留着就是「换了数据集还用旧训练段」
    for fn in _INVALIDATORS:      # ← 第四个：实时源（由 api/live.py 登记）
        fn()
