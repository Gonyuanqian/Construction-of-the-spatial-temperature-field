from __future__ import annotations
import pandas as pd
import pytest
from tfield.data.timestamp import repair_axis, TS_SHIFT

N = 1308          # 与真实数据同长：11:00 起、5 min 一点、共 4.54 天
FIXED = (60, 348, 636, 924, 1212)


def _clean(n: int = N) -> pd.Series:
    return pd.Series(pd.date_range("2026-07-23 11:00", periods=n, freq="5min"))


def _corrupt(ts: pd.Series) -> pd.Series:
    """复刻源数据缺陷：把每天 16:00 的行写成次日 00:00（+8 h）。"""
    out = ts.copy()
    for i in FIXED:
        if i < len(out):
            out.iloc[i] = out.iloc[i].normalize() + pd.Timedelta(hours=24)
    return out


def test_造出来的测试数据确实复刻了缺陷():
    ts = _clean()
    # 索引 60 = 11:00 + 300 min = 当天 16:00；被写成次日 00:00
    assert ts.iloc[60] == pd.Timestamp("2026-07-23 16:00")
    bad = _corrupt(ts)
    assert bad.iloc[60] == pd.Timestamp("2026-07-24 00:00")
    assert len(pd.unique(bad)) < len(bad)


def test_干净序列不被改动():
    ts = _clean()
    fixed, rep = repair_axis(ts)
    assert rep.fixed_indices == ()
    assert rep.monotonic_before and rep.monotonic_after
    assert (fixed.to_numpy() == ts.to_numpy()).all()


def test_修复必须幂等():
    """Review Focus #4：第二遍不能改变任何东西。"""
    fixed1, rep1 = repair_axis(_corrupt(_clean()))
    fixed2, rep2 = repair_axis(pd.Series(fixed1))
    assert rep1.fixed_indices == FIXED
    assert rep2.fixed_indices == ()
    assert (fixed1.to_numpy() == fixed2.to_numpy()).all()


def test_检出并修复全部五处():
    fixed, rep = repair_axis(_corrupt(_clean()))
    assert rep.fixed_indices == FIXED
    assert not rep.monotonic_before
    assert rep.monotonic_after
    assert rep.spacing_seconds == 300.0
    assert rep.gaps == ()


def test_修复后严格递增且唯一():
    fixed, _ = repair_axis(_corrupt(_clean()))
    assert fixed.is_monotonic_increasing and fixed.is_unique
    assert len(fixed) == N


def test_修复后与原始时刻逐位一致():
    """修复必须还原成真值，不是「能排上序就行」。"""
    fixed, _ = repair_axis(_corrupt(_clean()))
    assert (fixed.to_numpy() == _clean().to_numpy()).all()


def test_异常超过八小时则报错而不是硬修():
    """偏移量不等于 8 h 的乱序是另一种缺陷，不该被当成同一个问题悄悄改掉。"""
    ts = _clean().copy()
    ts.iloc[10] = ts.iloc[10] + pd.Timedelta(hours=30)
    with pytest.raises(ValueError, match="8 小时"):
        repair_axis(ts)


def test_偏移量常量():
    assert TS_SHIFT == pd.Timedelta(hours=8)


def test_报出原始文件里的重复时刻数():
    """重复只在**修复前**的原始轴上存在 —— 修完的轴严格递增，拿它算必然恒为 0。

    五处缺陷里只有四处真的撞上了已有时刻：最后那处（索引 1212）被移到
    2026-07-28 00:00，落在这一列之外，所以它只是乱序，不构成重复。
    """
    _, rep = repair_axis(_corrupt(_clean()))
    assert rep.duplicate_count == 4


def test_干净序列的重复数是零():
    _, rep = repair_axis(_clean())
    assert rep.duplicate_count == 0
