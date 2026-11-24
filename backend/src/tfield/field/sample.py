"""连续网格取值。只混合非零权重的有效角点，不跨越缺失值补数。"""
from __future__ import annotations

from typing import Callable, Sequence
import numpy as np


def axis_weights(axis: Sequence[float], value: float) -> list[tuple[int, float]]:
    a = np.asarray(axis, dtype=float)
    if not np.isfinite(value) or not len(a) or value < a[0] - 1e-9 or value > a[-1] + 1e-9:
        raise ValueError("坐标超出这一卷的范围")
    i = int(np.searchsorted(a, value))
    for j in (i, i - 1):
        if 0 <= j < len(a) and abs(a[j] - value) <= 1e-9:
            return [(j, 1.0)]
    w = float((value - a[i - 1]) / (a[i] - a[i - 1]))
    return [(i - 1, 1.0 - w), (i, w)]


def sample_grid(xs, ys, zs, point, plane: Callable[[int], np.ndarray],
                blocked: Callable[[int, int], bool]) -> float | None:
    """三线性插值；plane 来自与三维载荷相同的约束后场。格点命中保持原值。"""
    x, y, z = point
    wx, wy, wz = axis_weights(xs, x), axis_weights(ys, y), axis_weights(zs, z)
    value = 0.0
    for iy, b in wy:
        values = plane(iy)
        for iz, c in wz:
            for ix, a in wx:
                v = values[iz, ix]
                if blocked(ix, iz) or not np.isfinite(v):
                    return None
                value += a * b * c * float(v)
    return value
