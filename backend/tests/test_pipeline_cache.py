"""管线缓存：键是身份、容量是 LRU、并发下同一个键只构建一次。

这里的 builder 一律是**假的**（一个记账的 lambda）—— 真 `fit()` 要几十秒，
缓存的正确性与「训得多准」无关。真管线的等价性由 `test_api_field.py` 的
P3 验收测试负责。
"""
from __future__ import annotations

import threading

import pytest

from api.deps import PipelineCache


class FakeDs:
    """只要有 `signature` 就够了 —— 键只认它。"""

    def __init__(self, sig: str) -> None:
        self.signature = sig


class FakeBundle:
    def __init__(self, created_at: str) -> None:
        self.created_at = created_at


GROUPS = ("coord", "zbasis", "meteo", "interaction")


def make_cache(built: list) -> PipelineCache:
    def builder(ds, groups, bundle):
        built.append((ds.signature, tuple(groups), getattr(bundle, "created_at", None)))
        return f"pipe@{len(built)}"

    return PipelineCache(builder=builder, capacity=4)


def test_同键不重建():
    built: list = []
    c = make_cache(built)
    ds, b = FakeDs("sig-1"), FakeBundle("2026-10-03T13:22:00+00:00")
    first = c.get(ds, GROUPS, b)
    second = c.get(ds, GROUPS, b)
    assert first is second
    assert len(built) == 1
    assert c.n_builds == 1


def test_换数据集要重建():
    built: list = []
    c = make_cache(built)
    b = FakeBundle("t1")
    c.get(FakeDs("sig-1"), GROUPS, b)
    c.get(FakeDs("sig-2"), GROUPS, b)
    assert len(built) == 2


def test_换特征组要重建():
    built: list = []
    c = make_cache(built)
    ds, b = FakeDs("sig-1"), FakeBundle("t1")
    c.get(ds, GROUPS, b)
    c.get(ds, ("coord",), b)
    assert len(built) == 2


def test_换标定包要重建():
    built: list = []
    c = make_cache(built)
    ds = FakeDs("sig-1")
    c.get(ds, GROUPS, FakeBundle("t1"))
    c.get(ds, GROUPS, FakeBundle("t2"))
    assert len(built) == 2


def test_没有标定包时键里是空串而不是_None():
    """未标定时也能跑（走 FALLBACK_*），但键必须与「有包」区分得开。"""
    built: list = []
    c = make_cache(built)
    ds = FakeDs("sig-1")
    c.get(ds, GROUPS, None)
    c.get(ds, GROUPS, FakeBundle(""))
    assert len(built) == 1, "None 与空 created_at 应当是同一个键"


def test_超容量按_LRU_淘汰():
    # 这个 cache 用内联 lambda 当 builder，所以不记账 —— 它只验淘汰次序本身。
    c = PipelineCache(builder=lambda ds, g, b: f"pipe@{ds.signature}", capacity=2)
    b = FakeBundle("t1")
    c.get(FakeDs("a"), GROUPS, b)
    c.get(FakeDs("b"), GROUPS, b)
    c.get(FakeDs("a"), GROUPS, b)      # a 命中，提到队尾
    c.get(FakeDs("c"), GROUPS, b)      # 淘汰最久未用的 b
    assert c.get(FakeDs("a"), GROUPS, b) == "pipe@a"   # a 还在
    assert c.get(FakeDs("c"), GROUPS, b) == "pipe@c"   # c 还在
    assert c.get(FakeDs("b"), GROUPS, b) == "pipe@b"   # b 被淘汰过，重新构建


def test_并发下同一个键只构建一次():
    """FastAPI 的同步端点跑在线程池里，两个请求可以同时到。"""
    built: list = []
    started = threading.Barrier(2)
    c = make_cache(built)
    ds, b = FakeDs("sig-1"), FakeBundle("t1")
    out: list = []

    def worker():
        started.wait()
        out.append(c.get(ds, GROUPS, b))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1
    assert out[0] is out[1]
