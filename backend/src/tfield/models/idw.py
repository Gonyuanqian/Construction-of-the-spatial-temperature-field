"""各向异性反距离加权的残差修正。

IDW 是**精确插值器**：在源点处权重为 1，恰好复现该点的残差。
因此评估时必须把被留出的点从源集里排除（R1），否则 MAE 会假性趋零。

fit() 收的就是源集 —— 「排除自身」是调用方的责任，因为只有折知道谁被留出了。
设计成「调用方必须显式给源集」，就不可能忘。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 距离下限（归一化坐标下的长度）。不能用机器极小：`tiny ** power` 会下溢成 0，
# 于是 1/0 = inf、再被下面的 isinf 分支清零，重合点的权重反而变成 0 ——
# IDW 就不再是精确插值器了，而 R1 整条规则正建立在这个性质上。
_MIN_DIST = 1e-9


@dataclass(frozen=True)
class AnisoMetric:
    """各向异性距离 d = sqrt((Δx/lx)² + (Δy/ly)² + (Δz/lz)²)。"""

    lx: float = 1.0
    ly: float = 1.0
    lz: float = 0.12
    power: float = 2.0

    def scales(self) -> np.ndarray:
        return np.array([self.lx, self.ly, self.lz], dtype=float)

    def distances(self, target: np.ndarray, source: np.ndarray) -> np.ndarray:
        """→ (n_tgt, n_src)"""
        t = np.atleast_2d(np.asarray(target, dtype=float))
        s = np.atleast_2d(np.asarray(source, dtype=float))
        diff = (t[:, None, :] - s[None, :, :]) / self.scales()
        return np.sqrt((diff ** 2).sum(axis=-1))


class IDWCorrector:
    def __init__(self, metric: AnisoMetric, cross_shed: bool = True) -> None:
        self.metric = metric
        self.cross_shed = cross_shed
        self._coords: np.ndarray | None = None
        self._resid: np.ndarray | None = None

    def fit(self, coords: np.ndarray, resid: np.ndarray) -> "IDWCorrector":
        coords = np.asarray(coords, dtype=float)
        resid = np.asarray(resid, dtype=float)
        if resid.ndim == 1:
            resid = resid[:, None]
        if coords.ndim != 2 or coords.shape[1] != 3:
            raise ValueError(f"源点坐标应为 (n, 3)，实际 {coords.shape}")
        if resid.shape[0] != coords.shape[0]:
            raise ValueError(
                f"源点残差行数 {resid.shape[0]} 与源点坐标行数 {coords.shape[0]} 不一致；"
                "fit() 只接受【源点】的残差"
            )
        self._coords, self._resid = coords, resid
        return self

    def predict(self, target_coords: np.ndarray) -> np.ndarray:
        if self._coords is None or self._resid is None:
            raise RuntimeError("predict() 之前必须先 fit()")
        tgt = np.atleast_2d(np.asarray(target_coords, dtype=float))
        d = self.metric.distances(tgt, self._coords)

        if not self.cross_shed:
            # 只保留与目标最近的棚的源点：其余权重置零
            dy = np.abs(tgt[:, None, 1] - self._coords[None, :, 1])
            nearest = dy.min(axis=1, keepdims=True)
            keep = dy <= nearest + 1e-9
            d = np.where(keep, d, np.inf)

        d = np.maximum(d, _MIN_DIST)             # 重合点用极小距离，避免除零
        w = 1.0 / d ** self.metric.power
        w = np.where(np.isinf(w), 0.0, w)
        w = w / w.sum(axis=1, keepdims=True)
        # w: (n_tgt, n_src)，_resid: (n_src, n_t) → (n_tgt, n_t)
        return w @ self._resid
