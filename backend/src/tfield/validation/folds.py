"""折定义（R3：不同折族的数值不可直接比较，报告必须写明用的是哪一族）。

三族：
- position  留一测点：留出一个 (x, z) 位置在三个棚的全部数据。8 折 × 3 传感器。
            带 A/B 分组标签 —— A 组用于标定选参，B 组只用于报数。
- section   留一断面：留出整个棚（8 点），用另两棚训练。3 折。
            实测 MAE 恒等于 |T(y=9) − [T(y=3) + T(y=15)]/2| 的绝对值。
- region    留区域：留出一整块空间区域。4 折。

棚位与坐标全部取自 Dataset，不读 config 的副本 —— 折定义必须描述这份数据。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .. import config as C
from ..data.types import Dataset

Group = Literal["A", "B"] | None

# region 折按这个高度切「下层 / 上层」：0.7 是中间层测点的高度，
# 用它切才有物理含义（不是几何中点）。
REGION_SPLIT_Z = 0.7


@dataclass(frozen=True)
class Fold:
    name: str                                   # "position:x1.05_z0.4" / "section:p2" / "region:left_low"
    test_sensors: tuple[int, ...]
    group: Group = None


def fold_kind(name: str) -> str:
    return name.split(":", 1)[0]


def sensor_index(ds: Dataset, shed: str, pos: str) -> int:
    sheds = list(ds.sheds)
    positions = list(ds.layout)
    return sheds.index(shed) * len(positions) + positions.index(pos)


def position_folds(ds: Dataset) -> tuple[Fold, ...]:
    tuning = set(C.TUNING_POSITIONS)
    return tuple(
        Fold(
            name=f"position:{pos}",
            test_sensors=tuple(sensor_index(ds, shed, pos) for shed in ds.sheds),
            group="A" if pos in tuning else "B",
        )
        for pos in ds.layout
    )


def section_folds(ds: Dataset) -> tuple[Fold, ...]:
    return tuple(
        Fold(name=f"section:{shed}",
             test_sensors=tuple(sensor_index(ds, shed, pos) for pos in ds.layout))
        for shed in ds.sheds
    )


def region_folds(ds: Dataset) -> tuple[Fold, ...]:
    """左/右 × 下/上 —— 四个互斥的象限，合起来正好是全部 24 点。

    不能把「左半 / 右半 / 下层 / 上层」直接写成四折：那是两套二分，彼此重叠，
    24 个测点会被数两遍。折是**划分**，每个测点必须恰好留出一次，否则
    「折外预测」是什么就没有定义了。
    """
    mid_x = 0.5 * (C.SHED_X_MIN + C.SHED_X_MAX)
    blocks = {
        "left_low":   lambda x, z: x < mid_x and z <= REGION_SPLIT_Z,
        "left_high":  lambda x, z: x < mid_x and z > REGION_SPLIT_Z,
        "right_low":  lambda x, z: x >= mid_x and z <= REGION_SPLIT_Z,
        "right_high": lambda x, z: x >= mid_x and z > REGION_SPLIT_Z,
    }
    return tuple(
        Fold(name=f"region:{name}",
             test_sensors=tuple(
                 sensor_index(ds, shed, pos)
                 for shed in ds.sheds for pos in ds.layout
                 if pred(ds.layout[pos].x, ds.layout[pos].z)))
        for name, pred in blocks.items()
    )
