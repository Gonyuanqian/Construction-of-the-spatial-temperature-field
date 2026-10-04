"""进程内的依赖：数据集缓存（管线缓存在页③ 那份计划里加进同一个文件）。

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

from tfield.data.loader import load_dataset
from tfield.data.types import Dataset

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


_CACHE = DatasetCache()


def get_dataset(path: pathlib.Path | str | None = None) -> Dataset:
    """本项目数据集的唯一入口。**路由层不许直接 import load_dataset。**"""
    if path is None:
        from . import paths
        path = paths.dataset_path()
    return _CACHE.get(path)


def reset_cache() -> None:
    """换数据集之后（上传、重新导出）显式清一次。

    大多数情况下不需要 —— 键里有 mtime 与大小，文件一变自然失效。
    这个函数是给「文件被原地改回原样」那种边角留的。
    """
    global _CACHE
    _CACHE = DatasetCache()
