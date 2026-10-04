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

from tfield.calibration import groups_signature, load_for
from tfield.data.loader import load_dataset
from tfield.data.types import Dataset
from tfield.features import build_features
from tfield.pipeline import FieldPipeline, PipelineConfig

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


def _build_pipeline(ds: Dataset, groups: tuple[str, ...], bundle) -> FieldPipeline:
    """未标定走 `PipelineConfig.fallback()`（**不是最优，只是不在坏角上**）。

    这条路在界面上必须标成「未标定」—— 兜底参数与标定后的数**同折族、不同参数**，
    大小不可直接比。
    """
    from . import paths
    assert paths is not None  # 保持 import 形态一致；paths 在下面 get_pipeline 里真用
    cfg = bundle.config() if bundle is not None else PipelineConfig.fallback()
    return FieldPipeline(cfg, ds).fit(build_features(ds, groups), ds)


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


def get_pipeline(groups: tuple[str, ...] | None = None) -> FieldPipeline:
    """本项目管线的唯一入口。**路由层不许自己 new FieldPipeline、也不许自己 fit。**

    为什么它能与 `get_dataset` 并列成为 `api.deps` 的第二个出口：
    它**内部先调 `get_dataset()`**，是数据集缓存的消费者而不是绕过者；
    让它当出口，是为了让「管线只构建一次」这条性质有一个**可计数**的落点
    （`PipelineCache.n_builds`），否则每个路由各 fit 一次，谁也数不出来。
    """
    from . import paths
    from tfield import config as C
    groups = tuple(C.DEFAULT_FEATURE_GROUPS if groups is None else groups)
    ds = get_dataset()
    # 每次请求读一次标定包（794 KB 的 JSON，约 10 ms 量级）——
    # 它的 `created_at` 是键的一部分，不读就不知道键。相对 fit 的几十秒可以忽略。
    bundle = load_for(ds, groups, paths.CONFIGS)
    return _PIPELINES.get(ds, groups, bundle)


_CACHE = DatasetCache()


def get_dataset(path: pathlib.Path | str | None = None) -> Dataset:
    """本项目数据集的唯一入口。**路由层不许直接 import load_dataset。**"""
    if path is None:
        from . import paths
        path = paths.dataset_path()
    return _CACHE.get(path)


def reset_cache() -> None:
    """换数据集之后（上传、重新导出）显式清一次。**两个缓存一起清。**

    只清数据集不清管线是最坏的组合：数据集重读了，管线还是按旧数据 fit 出来的，
    于是「数据被替换就重标」整条防线失效，而 `n_loads` 会显示「确实重读了」——
    一条看起来正常的错。
    """
    global _CACHE, _PIPELINES
    _CACHE = DatasetCache()
    _PIPELINES = PipelineCache()
