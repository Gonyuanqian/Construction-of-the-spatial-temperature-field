"""成品字节的格式：存进去、装回来，以及三种读不动。

⭐ 这一层不认识管线，也不碰数据库 —— 一个纯字节格式。所以它不要 MySQL、
不要数据集，跑起来是毫秒级的。
"""
from __future__ import annotations

import dataclasses
import pickle

import numpy as np
import pytest

from tfield.artifact import (FORMAT_VERSION, MAGIC, ArtifactCorruptError,
                             ArtifactVersionError, PipelineArtifact)
from tfield.models.idw import AnisoMetric

_VERSION_BYTES = 4


class _FakeTrend:
    """够用就行的趋势桩：只回答「是你吗」。

    定义在模块层（不是测试函数里）是为了**能被 pickle**：`from_bytes` 装的是
    正文，正文里就是它的一个实例。
    """

    def __init__(self, v: float = 1.0) -> None:
        self.v = float(v)

    def predict(self, X) -> np.ndarray:
        return np.full(len(X), self.v)


def _art(**over) -> PipelineArtifact:
    base = dict(
        tool_version="0.1.0", trend_kind="xgboost",
        feature_groups=("coord", "meteo"), feature_names=("x", "y", "z"),
        metric=AnisoMetric(lx=20.0, ly=1.0, lz=0.03, power=0.5),
        cross_shed=False, n_times=1164, trend=_FakeTrend(7.5),
    )
    base.update(over)
    return PipelineArtifact(**base)


def test_存进去装回来逐字段相同():
    art = _art()
    got = PipelineArtifact.from_bytes(art.to_bytes())
    # trend 换成 None 再比：它是**另一个对象**（pickle 造出来的），而
    # `_FakeTrend` 没有 __eq__，直接比会挂在身份上，测的就不是格式了。
    assert dataclasses.replace(got, trend=None) == dataclasses.replace(art, trend=None)
    assert got.trend.predict(np.zeros((3, 3))).tolist() == [7.5, 7.5, 7.5]


def test_格式版本写在字节最前面():
    """⭐ 规格书 D8。版本必须能在**解开正文之前**读到 —— 不这样，
    「格式变了」就只能靠「解开炸了」来发现，于是它与「字节坏了」变成同一件事。
    """
    raw = _art().to_bytes()
    assert raw[:len(MAGIC)] == MAGIC
    assert raw[len(MAGIC):len(MAGIC) + _VERSION_BYTES] == FORMAT_VERSION.to_bytes(
        _VERSION_BYTES, "big")


def test_版本对不上时说得出两边是第几版():
    raw = _art().to_bytes()
    bad = (MAGIC + (FORMAT_VERSION + 1).to_bytes(_VERSION_BYTES, "big")
           + raw[len(MAGIC) + _VERSION_BYTES:])
    with pytest.raises(ArtifactVersionError) as ei:
        PipelineArtifact.from_bytes(bad)
    assert ei.value.found == FORMAT_VERSION + 1
    assert ei.value.expected == FORMAT_VERSION


def test_抬头对不上算坏_不算版本不对():
    """⭐ 规格书 §八：`bundle` 的 JSON、或者随便一张图片，都不是「版本不对」。
    两种错的屏上那句话不一样（`deps._artifact_note`），所以类型也必须不一样。
    """
    with pytest.raises(ArtifactCorruptError):
        PipelineArtifact.from_bytes(b'{"dataset_sig": "...", "groups_sig": "..."}')


def test_截断的字节算坏():
    raw = _art().to_bytes()
    with pytest.raises(ArtifactCorruptError):
        PipelineArtifact.from_bytes(raw[:len(MAGIC) + 2])            # 版本号都不完整
    with pytest.raises(ArtifactCorruptError):
        PipelineArtifact.from_bytes(raw[:len(MAGIC) + _VERSION_BYTES + 40])  # 正文被砍


def test_正文不是这个类时算坏():
    raw = (MAGIC + FORMAT_VERSION.to_bytes(_VERSION_BYTES, "big")
           + pickle.dumps({"nope": 1}))
    with pytest.raises(ArtifactCorruptError):
        PipelineArtifact.from_bytes(raw)
