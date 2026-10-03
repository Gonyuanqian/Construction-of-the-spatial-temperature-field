"""物理约束：竖直方向软单调投影 + 光照门禁（设计文档 §9）。

白天棚膜下蓄热 → 温度随高度不降；夜间实测存在**微逆温**
（约 13.6% 的时刻 ΔT(z0.7 − z0.4) < 0，幅度 −0.067 ~ 0 °C），
硬约束会让夜间整体失真。所以门禁放在光照上：只在 bg_light > 0 时施加。

strength 是软投影的插值系数：0 = 不投影，1 = 完全投影到单调。
做投影而不是把它塞进损失函数，是因为投影可解释、可关闭、不改变趋势模型的训练。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .. import config as C
from .types import Field


@dataclass(frozen=True)
class MonotonicConfig:
    enabled: bool = True
    direction: str = "increasing"     # 白天：温度随高度不降
    strength: float = 1.0


def pava_nondecreasing(v: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    """池相邻违反者算法：v 在加权 L2 意义下的非降等距回归拟合。"""
    v = np.asarray(v, dtype=float)
    n = len(v)
    if n == 0:
        return v.copy()
    w = np.ones(n) if w is None else np.asarray(w, dtype=float)

    vals: list[float] = []
    wts: list[float] = []
    cnt: list[int] = []
    for i in range(n):
        vals.append(float(v[i]))
        wts.append(float(w[i]))
        cnt.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, w2, c2 = vals.pop(), wts.pop(), cnt.pop()
            v1, w1, c1 = vals.pop(), wts.pop(), cnt.pop()
            vals.append((v1 * w1 + v2 * w2) / (w1 + w2))
            wts.append(w1 + w2)
            cnt.append(c1 + c2)

    out = np.empty(n, dtype=float)
    k = 0
    for val, c in zip(vals, cnt):
        out[k: k + c] = val
        k += c
    return out


def light_at(pipe, t_index: int) -> float:
    """取该时刻的背景光照（门禁量）。"""
    return float(pipe.ds.wide[C.BG_LIGHT].iloc[int(t_index)])


def apply_monotonic(f: Field, light: float,
                    cfg: MonotonicConfig = MonotonicConfig()) -> Field:
    """对每一列（固定 x、沿 z）施加竖直软单调投影。光照门禁。"""
    if not cfg.enabled or light <= 0 or cfg.strength <= 0:
        return f

    values = f.values.copy()
    nz, nx = values.shape
    for j in range(nx):
        col = values[:, j]
        good = np.isfinite(col)
        if good.sum() < 2:
            continue
        seg = col[good]
        # decreasing 方向：把列取负 → 求非降 → **再取负回来**，得到非增。
        # 漏掉最后那次取负，整列会变成负温度（实测 −9 °C），那不是「反向投影」而是另一回事。
        target = (-pava_nondecreasing(-seg) if cfg.direction == "decreasing"
                  else pava_nondecreasing(seg))
        new_col = col.copy()
        new_col[good] = seg + cfg.strength * (target - seg)
        values[:, j] = new_col

    values = np.where(f.mask, values, np.nan)
    return Field(values=values, x=f.x, z=f.z, mask=f.mask,
                 outside_measured=f.outside_measured,
                 meta={**dict(f.meta), "monotonic": True, "light": light})
