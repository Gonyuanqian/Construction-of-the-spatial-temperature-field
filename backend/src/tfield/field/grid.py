"""输出网格。

用【间距 dx】而不是【点数 nx/nz】作为主字段：测点高度 0.4 / 0.7 / 1.1 都是 0.01 的
整数倍，arange 会把它们精确落在格点上；若用 linspace(0, 1.3017, nz)，0.01 的整数倍
一般不落在格点上，测点处复现实测的断言就会因为半毫米的偏移而失效。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config as C

GRID_PRESETS = {"interactive": 0.10, "standard": 0.05, "export": 0.02}
_EPS = 1e-9


@dataclass(frozen=True)
class GridSpec:
    dx: float = 0.05
    x_min: float = C.SHED_X_MIN
    x_max: float = C.SHED_X_MAX
    z_min: float = 0.0
    z_max: float = C.SHED_Z_MAX

    @classmethod
    def from_preset(cls, preset: str) -> "GridSpec":
        if preset not in GRID_PRESETS:
            raise KeyError(f"未知网格档位 {preset!r}；可选 {sorted(GRID_PRESETS)}")
        return cls(dx=GRID_PRESETS[preset])

    @classmethod
    def from_spacing(cls, dx: float) -> "GridSpec":
        return cls(dx=float(dx))

    def x(self) -> np.ndarray:
        return np.arange(self.x_min, self.x_max + _EPS, self.dx)

    def z(self) -> np.ndarray:
        return np.arange(self.z_min, self.z_max + _EPS, self.dx)

    @property
    def nx(self) -> int:
        return len(self.x())

    @property
    def nz(self) -> int:
        return len(self.z())

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nz, self.nx)

    def mesh(self) -> tuple[np.ndarray, np.ndarray]:
        return np.meshgrid(self.x(), self.z())


def outside_measured_mask(X, Z) -> np.ndarray:
    """拱顶下 z > 1.10 m 的「无测量带」：没有任何传感器，值是外推产物。

    做成数据结构的一部分，而不是界面上的一句文案 —— 旧版的教训是界面写死了一句
    「顶部外推区 σ 明显更大」而数据根本不支持（σ 那时是常数）。
    """
    return np.asarray(Z, dtype=float) > C.MAX_MEASURED_Z
