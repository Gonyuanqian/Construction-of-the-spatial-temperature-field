"""留出切分：把数据集切成「训练段」与「留出段」。

这两个词的用法在本项目里是固定的：**训练段**是模型与构场看得到的那个世界
（时间轴到 2026-07-27 11:55），**留出段**是实时模式一帧一帧接进来的那 144 帧。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tfield import config as C
from tfield.data.loader import (HOLDOUT_CUTOFF, derived_signature, load_dataset,
                                split_holdout, test_data_path)

pytestmark = pytest.mark.skipif(not test_data_path().exists(),
                                reason="数据集不在（与 test_acceptance.py 同一口径）")


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


def test_两段加起来正好是全量(ds):
    h = split_holdout(ds, HOLDOUT_CUTOFF)
    assert len(h.train.wide) == 1164
    assert len(h.live) == 144
    assert len(h.train.wide) + len(h.live) == len(ds.wide) == C.EXPECTED_ROWS


def test_切点落在时间戳上_不落在行号上(ds):
    h = split_holdout(ds, HOLDOUT_CUTOFF)
    ts_train = pd.to_datetime(h.train.wide[C.COL_TIMESTAMP])
    ts_live = pd.to_datetime(h.live[C.COL_TIMESTAMP])
    assert bool((ts_train < HOLDOUT_CUTOFF).all())
    assert bool((ts_live >= HOLDOUT_CUTOFF).all())
    assert ts_live.iloc[0] == pd.Timestamp("2026-07-27 12:00:00")
    assert ts_live.iloc[-1] == pd.Timestamp("2026-07-27 23:55:00")


def test_两段不重叠_并集是全量(ds):
    h = split_holdout(ds, HOLDOUT_CUTOFF)
    full = pd.to_datetime(ds.wide[C.COL_TIMESTAMP]).to_numpy()
    both = np.concatenate([
        pd.to_datetime(h.train.wide[C.COL_TIMESTAMP]).to_numpy(),
        pd.to_datetime(h.live[C.COL_TIMESTAMP]).to_numpy()])
    assert sorted(both.tolist()) == sorted(full.tolist())
    assert len(set(both.tolist())) == len(both), "两段有重叠的时刻"


def test_宽表与质检表同步切(ds):
    """质检列是逐行的 —— 错位会静默把 A 行的标记贴到 B 行上。"""
    h = split_holdout(ds, HOLDOUT_CUTOFF)
    assert len(h.train.quality) == len(h.train.wide)
    same = (pd.to_datetime(h.train.quality[C.COL_TIMESTAMP]).to_numpy()
            == pd.to_datetime(h.train.wide[C.COL_TIMESTAMP]).to_numpy())
    assert bool(same.all())


def test_派生签名稳定_与全量不同_且不含冒号(ds):
    s1 = derived_signature(ds.signature, HOLDOUT_CUTOFF)
    s2 = derived_signature(ds.signature, HOLDOUT_CUTOFF)
    assert s1 == s2, "同一个输入跑两次给了两个签名，缓存键与包名都会漂"
    assert s1 != ds.signature, "训练段与全量共用了一个身份"
    for bad in (":", "/", "\\", "*", "?"):
        assert bad not in s1, f"签名里有 Windows 文件名非法字符 {bad!r}：{s1}"


def test_训练段带派生签名_修复报告原样(ds):
    h = split_holdout(ds, HOLDOUT_CUTOFF)
    assert h.train.signature == derived_signature(ds.signature, HOLDOUT_CUTOFF)
    assert h.train.fix == ds.fix


def test_带时区的切点直接抛(ds):
    """数据集的 timestamp 列是 naive 的（实测 `datetime64[us]`、`tzinfo=None`）。

    这条钉的不是「异常的类型」，是**不许静默切错**：naive 与 aware 比大小
    在任何一份实现里都不成立，要么抛、要么明确报错。
    """
    with pytest.raises((TypeError, ValueError)):
        split_holdout(ds, pd.Timestamp("2026-07-27 12:00:00", tz="UTC"))
