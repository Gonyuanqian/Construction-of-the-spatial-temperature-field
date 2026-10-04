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
    """容量 2，而且**必须记账** —— 只断言返回值的话，这条测试验不了 LRU。

    `pipe@{signature}` 是确定的：不管命中的是缓存里的旧对象还是刚重建的新对象，
    返回值都一样。若只断言返回值，「命中不提升（FIFO）」与「淘汰错了对象」两种
    实现都能通过 —— 而这条测试的名字许诺的正是它们不能通过。
    所以断言的是**构建次序**：a 只被构建过一次（说明第 3 步的命中确实把它提到了
    队尾，否则第 4 步被淘汰的就是它），b 被构建过两次（说明第 4 步淘汰的确实是它）。
    """
    built: list = []

    def builder(ds, groups, bundle):
        built.append(ds.signature)
        return f"pipe@{ds.signature}"

    c = PipelineCache(builder=builder, capacity=2)
    b = FakeBundle("t1")
    c.get(FakeDs("a"), GROUPS, b)      # 建 a      → [a]
    c.get(FakeDs("b"), GROUPS, b)      # 建 b      → [a, b]
    c.get(FakeDs("a"), GROUPS, b)      # a 命中，提到队尾 → [b, a]
    c.get(FakeDs("c"), GROUPS, b)      # 建 c，淘汰最久未用的 b → [a, c]
    c.get(FakeDs("a"), GROUPS, b)      # 命中，不重建
    c.get(FakeDs("c"), GROUPS, b)      # 命中，不重建
    c.get(FakeDs("b"), GROUPS, b)      # 上一步被淘汰的是它，重建 → [c, b]
    assert built == ["a", "b", "c", "b"]


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


def test_管线自己带着_是否标定的_事实():
    """路由不该回头去读缓存的键 —— 让管线自己带这个事实。

    直接调 `_mark_calibrated`，绕开 `fit()`：要验证的是**赋值这一步**，
    与「训得多准」无关。
    """
    from api.deps import _mark_calibrated
    from tfield.pipeline import FieldPipeline

    class FakeBundle:
        created_at = "2026-10-03T13:22:00+00:00"

    pipe = FieldPipeline.__new__(FieldPipeline)      # 不 __init__、不 fit
    _mark_calibrated(pipe, FakeBundle())
    assert pipe.calibrated is True
    _mark_calibrated(pipe, None)
    assert pipe.calibrated is False


def test_没有标注的管线读出来是假而不是抛错():
    """`getattr(..., False)` 的兜底方向必须是「未标定」。

    兜底成 True 会让界面把没标定的数说成标定过的 —— 这句谎话没人看得出来。
    """
    from tfield.pipeline import FieldPipeline
    assert getattr(FieldPipeline.__new__(FieldPipeline), "calibrated", False) is False
