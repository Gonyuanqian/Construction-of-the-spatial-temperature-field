"""拱形几何与掩膜。

不做掩膜会把棚外空气渲染成温度场 —— 可视化中最容易被看穿的错误。
"""
from __future__ import annotations

import numpy as np

from .. import config as C


def arch_height(x) -> np.ndarray:
    """拱面高度 z(x) = sqrt(R² − (x − XC)²) + K。"""
    x = np.asarray(x, dtype=float)
    inner = C.ARCH_R ** 2 - (x - C.ARCH_XC) ** 2
    return np.sqrt(np.maximum(inner, 0.0)) + C.ARCH_K


def arch_mask(X, Z) -> np.ndarray:
    """棚体内为 True（含边界）。"""
    X = np.asarray(X, dtype=float)
    Z = np.asarray(Z, dtype=float)
    inside_x = (X >= C.SHED_X_MIN) & (X <= C.SHED_X_MAX)
    return inside_x & (Z <= arch_height(X) + 1e-12)


def arch_area(x_min: float, x_max: float, n: int = 200_001) -> float:
    """梯形法积分截面面积。numpy < 2.0 没有 np.trapezoid，回退到 np.trapz。"""
    trapezoid = getattr(np, "trapezoid", None) or np.trapz
    x = np.linspace(x_min, x_max, n)
    return float(trapezoid(arch_height(x), x))
