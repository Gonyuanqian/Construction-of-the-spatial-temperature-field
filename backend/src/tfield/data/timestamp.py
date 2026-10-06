"""时间轴校验与修复（R6）。

源数据缺陷：每天 16:00 的行被写成次日 00:00（+8 小时，时区二次换算痕迹），
共 5 行（索引 60/348/636/924/1212）。表现为文件顺序上一次「前进 8 小时、然后倒退 8 小时」。

修复判据（**不硬编码行号**）：在文件顺序上若 ts[i] > ts[i+1]，则第 i 行被过移了 8 小时；
再过移 8 小时后它应正好落在 i+1 行之前一个采样间隔的位置。判据不成立就报错，
不猜、不硬修。
"""
from __future__ import annotations

import pandas as pd

from .. import config as C
from .types import FixReport

TS_SHIFT = pd.Timedelta(hours=8)
_TOL = pd.Timedelta(minutes=1)


def _typical_step(values: list[pd.Timestamp]) -> pd.Timedelta:
    """文件顺序里最常出现的正向步长，作为采样间隔的估计。

    用众数而不是「假定 5 分钟」，这样判据不依赖采样率常量。
    """
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)
             if values[i + 1] > values[i]]
    if not diffs:
        return pd.Timedelta(minutes=5)
    return pd.Series(diffs).mode().iloc[0]


def _spacing_seconds(idx: pd.DatetimeIndex) -> float | None:
    if len(idx) < 2:
        return None
    return float(pd.Series(idx).diff().dropna().median().total_seconds())


def _find_gaps(idx: pd.DatetimeIndex,
               expected_s: float) -> tuple[tuple[pd.Timestamp, pd.Timestamp], ...]:
    diffs = pd.Series(idx).diff().dropna()
    bad = diffs[diffs.dt.total_seconds() != expected_s].index
    return tuple((idx[int(i) - 1], idx[int(i)]) for i in bad)


def repair_axis(ts: pd.Series) -> tuple[pd.DatetimeIndex, FixReport]:
    """校验并修复时间轴。返回 (修复后的索引, 审计记录)。

    幂等：对已修复的序列再跑一遍，不改变任何值。
    """
    raw = pd.DatetimeIndex(pd.to_datetime(ts))
    monotonic_before = bool(raw.is_monotonic_increasing)
    # 原始轴上的重复时刻。**必须在下面修之前算** —— 修完的轴严格递增，
    # 再算就是恒 0。多移 8 小时的那几行里，落在列内的会撞上已有时刻。
    duplicate_count = int(pd.Series(raw).duplicated().sum())

    values = list(raw)
    step = _typical_step(values)
    fixed_indices: list[int] = []
    for i in range(len(values) - 1):
        if values[i] > values[i + 1]:
            # i 行被过移 8 h 后，应恰好落在 i+1 行之前一个采样间隔处
            expected = values[i + 1] - step
            actual = values[i] - TS_SHIFT
            if abs(actual - expected) > _TOL:
                raise ValueError(
                    f"第 {i} 行时间戳乱序，按 8 小时回退得到 {actual}，"
                    f"与预期 {expected} 不符（偏差 {actual - expected}）。"
                    "这不是已知的 8 小时缺陷，请人工检查，不要自动修复。"
                )
            values[i] = actual
            fixed_indices.append(i)

    idx = pd.DatetimeIndex(values)
    if not idx.is_monotonic_increasing:
        raise ValueError("修复后时间轴仍非严格递增，说明存在未建模的时间戳缺陷，拒绝继续。")

    spacing = _spacing_seconds(idx)
    gaps = _find_gaps(idx, C.EXPECTED_SPACING_S)
    report = FixReport(
        n_rows=len(idx),
        fixed_indices=tuple(fixed_indices),
        monotonic_before=monotonic_before,
        monotonic_after=True,
        spacing_seconds=spacing,
        gaps=gaps,
        duplicate_count=duplicate_count,
    )
    return idx, report
