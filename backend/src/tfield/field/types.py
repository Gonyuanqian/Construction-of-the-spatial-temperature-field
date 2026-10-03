"""场的容器类型。

单独成文件是为了打断循环导入：constraints.py 需要 Field，build.py 需要
constraints.apply_monotonic，若 Field 定义在 build.py 里就会成环。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


@dataclass(frozen=True)
class Field:
    values: np.ndarray              # (nz, nx)，掩膜外为 NaN
    x: np.ndarray
    z: np.ndarray
    mask: np.ndarray                # 拱形内为 True
    outside_measured: np.ndarray    # 拱顶下无测量带（已与 mask 求交）
    meta: Mapping[str, Any]

    @property
    def nz(self) -> int:
        return self.values.shape[0]

    @property
    def nx(self) -> int:
        return self.values.shape[1]
