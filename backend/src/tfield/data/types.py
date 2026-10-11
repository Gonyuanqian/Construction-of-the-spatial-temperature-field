from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pandas as pd

from .. import config as C


@dataclass(frozen=True)
class FixReport:
    """时间轴修复的审计记录。"""

    n_rows: int
    fixed_indices: tuple[int, ...]
    monotonic_before: bool
    monotonic_after: bool
    spacing_seconds: float | None
    gaps: tuple[tuple[pd.Timestamp, pd.Timestamp], ...]   # 相邻但不满足采样间隔的两个时刻
    #: 修复**前**的原始轴里有几个时刻是重复的（多出来的那几行，不是涉及的行数）。
    #:
    #: ⚠️ **只在原始文件上才有意义**：修完的轴严格递增（不递增就直接抛），
    #: 拿修完的轴算这个数恒为 0。页① 报的是这一份数据「从哪来」，
    #: 所以报的是原始文件里的那一份。
    duplicate_count: int = 0


@dataclass(frozen=True)
class SensorPos:
    x: float
    z: float
    layer: str          # "z0.4" / "z0.7" / "ztop"


@dataclass(frozen=True)
class Dataset:
    """一次加载的只读数据集。"""

    wide: pd.DataFrame                # 1308 × 52，索引 = 修复后的时间
    layout: Mapping[str, SensorPos]   # 8 个切面内位置 → (x, z, layer)
    sheds: Mapping[str, float]        # p1/p2/p3 → y = 3 / 9 / 15
    quality: pd.DataFrame             # 插值标记，同形状
    fix: FixReport
    signature: str                    # sha1(路径|mtime|size)[:16]
    _dict_layout: Mapping[str, SensorPos] = field(default_factory=dict, repr=False)

    def dict_layout(self) -> Mapping[str, SensorPos]:
        """从数据自带的「测点字典」sheet 读出的坐标，用于校验 config 没漂移。"""
        return self._dict_layout

    def sensor_ids(self) -> list[tuple[int, str, str]]:
        """传感器编号 → (编号, 棚, 测点)。棚主序：p1 的 8 个位置，然后 p2、p3。"""
        return [(i, shed, pos)
                for i, (shed, pos) in enumerate(
                    (s, p) for s in C.SHED_ORDER for p in C.SENSOR_LAYOUT)]
