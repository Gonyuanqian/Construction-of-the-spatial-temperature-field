"""断面二维场 + 沿棚长方向的 1/dy 混合（R2）。

R2 的由来：树模型只在 y ∈ {3, 9, 15} 上训练过，查询中间 y 会输出阶梯
（旧实现实测 y = 6 处 2.44 °C 的断崖），且断崖在趋势项内、残差修正消不掉。

本模块绕开了它：**先在各断面自身的 y 上建好完整二维场，再在【匹配的 (x, z)】上
按 1/dy 混合**。趋势模型从头到尾只被查过**本次 fit 真的见过的** y ——
部署口径下就是 3 / 9 / 15（test_R2_绝不在中间y上查询趋势模型 守）；
留一断面时 p2 整棚不在源集里，y = 9 就不是合法查询集（test_留出整棚后* 守）。

⚠️ **合法的 y 集是本次 fit 的属性，不是 `C.SHED_Y` 这个常数** ——
把「合法」写死成「三个棚的 y」，在留出整个棚的那一折上就会静默违规。
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .. import config as C
from ..pipeline import FieldPipeline
from .arch import arch_mask
from .constraints import MonotonicConfig, apply_monotonic, light_at
from .grid import GridSpec, outside_measured_mask
from .types import Field

__all__ = ["Field", "available_sheds", "bracketing_sheds", "section_field",
           "blend_fields", "field_at"]


def available_sheds(pipe: FieldPipeline) -> tuple[str, ...]:
    """本次 fit 的源传感器覆盖到的棚（按 C.SHED_ORDER 排序）。

    留一断面时整个棚被排除，它的 y 就没有任何训练样本 —— 必须从可用集里消失，
    否则 `field_at` 会短路到那个断面、在没有样本的 y 上查趋势（R2）。
    """
    levels = {round(float(v), 6) for v in pipe.source_y_levels()}
    out = tuple(s for s in C.SHED_ORDER if round(float(C.SHED_Y[s]), 6) in levels)
    if not out:
        raise ValueError("本次 fit 没有任何可用的断面源传感器")
    return out


def bracketing_sheds(y: float, sheds: Sequence[str] | None = None) -> tuple[str, str] | None:
    """返回把 y 夹在中间的两个棚；y 在两端之外返回 None。

    `sheds` 给出参与混合的棚集合（默认全部三个）。传 `available_sheds(pipe)`
    才能正确处理留一断面 —— 被留出的棚不在集合里，它那一对就不会出现。

    区间约定：[lo, hi) —— 内部的分界点归上面那一对；**最后一对的上端闭合**，
    否则 y = 15 会掉出所有区间。这样集合范围内每个 y 恰好属于一对。
    """
    order = tuple(sheds) if sheds is not None else C.SHED_ORDER
    for i in range(len(order) - 1):
        lo, hi = order[i], order[i + 1]
        y_lo, y_hi = C.SHED_Y[lo], C.SHED_Y[hi]
        last = i == len(order) - 2
        if y_lo <= y and (y < y_hi or (last and y <= y_hi)):
            return lo, hi
    return None


def section_field(pipe: FieldPipeline, shed: str, t_index: int, grid: GridSpec,
                  *, monotonic: "MonotonicConfig | None" = None) -> Field:
    """在某个断面自身的 y 上重建完整二维温度场。"""
    X, Z = grid.mesh()
    y = C.SHED_Y[shed]
    coords = np.column_stack([X.ravel(), np.full(X.size, y), Z.ravel()])
    ti = np.array([t_index])
    values = pipe.trend_at_coords(coords, ti) + pipe.residual_at_coords(coords, ti)
    values = values[:, 0].reshape(X.shape)

    mask = arch_mask(X, Z)
    values = np.where(mask, values, np.nan)
    field = Field(values=values, x=grid.x(), z=grid.z(), mask=mask,
                  outside_measured=outside_measured_mask(X, Z) & mask,
                  meta={"shed": shed, "y": y, "t_index": t_index})
    if monotonic is not None:
        field = apply_monotonic(field, light_at(pipe, t_index), monotonic)
    return field


def _same_geometry(a: Field, b: Field) -> bool:
    return (np.array_equal(a.mask, b.mask)
            and np.array_equal(a.x, b.x) and np.array_equal(a.z, b.z))


def _relabel(f: Field, y: float) -> Field:
    return Field(values=f.values, x=f.x, z=f.z, mask=f.mask,
                 outside_measured=f.outside_measured,
                 meta={**dict(f.meta), "y": y})


def blend_fields(a: Field, b: Field, *, y: float, ya: float, yb: float) -> Field:
    """在匹配的 (x, z) 上按 1/dy 加权混合两个断面场。y 到端点时退化为端点。"""
    if not _same_geometry(a, b):
        raise ValueError("两个断面场的掩膜或网格不一致，不能混合")
    lo, hi = (a, b) if ya <= yb else (b, a)
    y_lo, y_hi = (ya, yb) if ya <= yb else (yb, ya)

    if y <= y_lo:
        return _relabel(lo, y)
    if y >= y_hi:
        return _relabel(hi, y)

    w_lo, w_hi = 1.0 / (y - y_lo), 1.0 / (y_hi - y)
    tot = w_lo + w_hi
    values = (w_lo * lo.values + w_hi * hi.values) / tot
    values = np.where(a.mask, values, np.nan)
    return Field(values=values, x=a.x, z=a.z, mask=a.mask,
                 outside_measured=a.outside_measured & b.outside_measured,
                 meta={"y": y, "blend": (y_lo, y_hi), "weights": (w_lo / tot, w_hi / tot)})


def field_at(pipe: FieldPipeline, y: float, t_index: int, grid: GridSpec,
             *, monotonic: "MonotonicConfig | None" = None) -> Field:
    """任意 y 处的温度场。**只查询夹住 y 的那两个【可用】断面**（R2）。

    可用的断面不是常数，而是**本次 fit 的源传感器覆盖到的那些棚**
    （`available_sheds`）。留一断面时 p2 整棚被排除，y = 9 就没有训练样本，
    此时查询 y = 9 会改混合 p1 与 p3 —— 而不是短路到 p2 断面去查那个陌生的 y。

    monotonic 在**混合之后**施加：逐断面施加再混合会投影两次（且混合权重随 y 变），
    统一在最后做一次，保证「出口处的场一定满足约束」这条不变量。所以这里给
    section_field 传的是 monotonic=None。
    """
    Y = C.SHED_Y
    avail = available_sheds(pipe)
    if len(avail) == 1:
        f = _relabel(section_field(pipe, avail[0], t_index, grid), y)
    elif y < Y[avail[0]]:
        f = _relabel(section_field(pipe, avail[0], t_index, grid), y)
    elif y > Y[avail[-1]]:
        f = _relabel(section_field(pipe, avail[-1], t_index, grid), y)
    else:
        pair = bracketing_sheds(y, avail)
        assert pair is not None                   # y 在可用集范围内，必有一对
        lo, hi = pair
        if Y[lo] == y:
            f = _relabel(section_field(pipe, lo, t_index, grid), y)
        elif Y[hi] == y:
            f = _relabel(section_field(pipe, hi, t_index, grid), y)
        else:
            f = blend_fields(section_field(pipe, lo, t_index, grid),
                             section_field(pipe, hi, t_index, grid),
                             y=y, ya=Y[lo], yb=Y[hi])
    if monotonic is not None:
        f = apply_monotonic(f, light_at(pipe, t_index), monotonic)
    return f
