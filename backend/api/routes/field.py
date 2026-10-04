"""空间场的几何与取值。

页③（V5 切面场）的三个接口住在这里：`/field/sections`、`/field/curve`、
`/field/compare`。`/field/volume`（V7 棚体三维场）属于下一份计划。

**这一层只做两件事**：把 `tfield` 算出的场翻成 JSON（拱外 NaN → null），
以及算共享色标范围这一个**派生的表现量**。任何真正的计算都在 `tfield` 里 ——
接口层再算一遍就是把 R2 之类的规则实现了两遍，迟早对不上（spec 硬约束 1）。
"""
from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from tfield import config as C
from tfield.field.arch import arch_height, arch_mask
from tfield.field.build import section_field
from tfield.field.constraints import MonotonicConfig
from tfield.field.grid import GRID_PRESETS, GridSpec

from .. import deps

router = APIRouter(tags=["field"])

#: 拱线折线的点数。121 点 → 每 0.0175 m 一段：屏幕上一像素以内，
#: 而 JSON 只有两百多个数。**点数由后端定**，前端不生成几何。
ARCH_SAMPLES = 121

DEFAULT_PRESET = "standard"


def _check_preset(preset: str) -> GridSpec:
    if preset not in GRID_PRESETS:
        allowed = "、".join(sorted(GRID_PRESETS))
        raise HTTPException(400, f"认不出的 preset：{preset!r}（可选：{allowed}）")
    return GridSpec.from_preset(preset)


def _check_t_index(t_index: int, n_times: int) -> int:
    if not 0 <= t_index < n_times:
        raise HTTPException(400, f"t_index 越界：{t_index}（本数据集共 {n_times} 个时刻）")
    return t_index


def temp_range(*grids: np.ndarray) -> tuple[float, float]:
    """共享色标范围：**所有格子里有限值的并集**，0.1 °C 取整对齐。

    三格共用一个范围是这张图存在的全部理由 —— 各自拉伸的话，
    同一个颜色在三个棚里代表不同温度，并排看就失去意义（spec §七 V5）。

    退化保护（`vmax - vmin < 0.2` 时各让 0.1）与 Streamlit 版
    `fig_sections` 里的那条**同一条规则**：不让色标塌成零宽，
    否则一整张场是一个颜色，看起来像「处处一样温」。
    """
    vals = np.concatenate([np.asarray(g)[np.isfinite(np.asarray(g))] for g in grids])
    if vals.size == 0:
        return 0.0, 1.0
    lo = float(np.floor(float(vals.min()) * 10.0) / 10.0)
    hi = float(np.ceil(float(vals.max()) * 10.0) / 10.0)
    if hi - lo < 0.2:
        lo, hi = lo - 0.1, hi + 0.1
    return lo, hi


def _grid_or_none(values: np.ndarray) -> list[list[float | None]]:
    """NaN → None。**这一步是必须的**：`allow_nan=False` 会把 NaN 变成 HTTP 500。"""
    return [[float(v) if np.isfinite(v) else None for v in row] for row in values]


def _arch_polyline() -> list[list[float]]:
    x = np.linspace(C.SHED_X_MIN, C.SHED_X_MAX, ARCH_SAMPLES)
    return [[float(a), float(b)] for a, b in zip(x, arch_height(x))]


def _sensors() -> list[dict[str, Any]]:
    return [
        {"id": key, "x": float(px), "z": float(pz), "layer": layer}
        for key, (px, pz, layer) in C.SENSOR_LAYOUT.items()
    ]


@router.get("/field/arch")
def get_arch() -> dict[str, Any]:
    """拱形轮廓与三座棚的 y。（页① 用的；原样保留。）

    **前端不许自己算这条线。** 拱是 `z(x) = √(R² − (x−Xc)²) + K`，
    常数住在 `tfield.config` 里；在前端重抄一遍公式，抄错一个常数
    画出来的就不是这座棚，而且它看起来仍然像一条拱 —— 不会报错。
    测试拿 `arch_height` 与本接口逐位对（后端库就是那个 oracle）。

    ⚠️ 这条线**不会**产生非有限值：`arch_height` 里 `np.maximum(inner, 0.0)`
    把负的根号内挡成 0，所以任何 x 上都是有限的。前端可直接画，
    不必像 `layer-timeheight` 那样担心 null。
    """
    return {
        "x_min": float(C.SHED_X_MIN),
        "x_max": float(C.SHED_X_MAX),
        "z_max": float(C.SHED_Z_MAX),
        "max_measured_z": float(C.MAX_MEASURED_Z),
        "arch": _arch_polyline(),
        "sheds": [{"id": s, "y": float(C.SHED_Y[s])} for s in C.SHED_ORDER],
    }


@router.get("/field/sections")
def get_sections(
    t_index: int = Query(0, description="时刻下标"),
    preset: str = Query(DEFAULT_PRESET, description="网格档位"),
    monotonic: bool = Query(True, description="是否施加竖直软单调投影"),
) -> dict[str, Any]:
    """V5 切面场：三个断面的网格 + 无测量带下标 + 拱线 + 共享色标范围。"""
    grid = _check_preset(preset)
    pipe = deps.get_pipeline()
    n_times = int(pipe.ds.wide.shape[0])
    t_index = _check_t_index(t_index, n_times)
    cfg = MonotonicConfig(enabled=True) if monotonic else None

    fields = [section_field(pipe, s, t_index, grid, monotonic=cfg) for s in C.SHED_ORDER]
    vmin, vmax = temp_range(*[f.values for f in fields])

    sheds = []
    for shed, f in zip(C.SHED_ORDER, fields):
        # `np.nonzero` 返回 (行, 列)；场是 (nz, nx)，所以行是 z 下标、列是 x 下标。
        # 对外的边界是 `[ix, iz]`（前端按 x 再 z 读），所以这里先接 z 再接 x。
        iz, ix = np.nonzero(f.outside_measured)
        sheds.append({
            "shed": shed,
            "y": float(C.SHED_Y[shed]),
            "values": _grid_or_none(f.values),
            "stripes": [[int(a), int(b)] for a, b in zip(ix, iz)],
        })

    time = pipe.ds.wide[C.COL_TIMESTAMP].iloc[t_index]
    return {
        "t_index": t_index,
        "time": str(time),
        "n_times": n_times,
        "preset": preset,
        "monotonic": bool(monotonic),
        "calibrated": bool(getattr(pipe, "calibrated", False)),
        "vmin": vmin,
        "vmax": vmax,
        "max_measured_z": float(C.MAX_MEASURED_Z),
        "x_min": float(C.SHED_X_MIN),
        "x_max": float(C.SHED_X_MAX),
        "z_max": float(C.SHED_Z_MAX),
        "x": [float(v) for v in fields[0].x],
        "z": [float(v) for v in fields[0].z],
        "arch": _arch_polyline(),
        "sensors": _sensors(),
        "sheds": sheds,
        "note": (
            "三格共享同一个色标范围。拱外不画。z 高于 "
            f"{C.MAX_MEASURED_Z:.2f} m 是无测量带，带内是外推值，不报数。"
        ),
    }


def _finite_or_none(values: np.ndarray) -> list[float | None]:
    """一维的 NaN → None。与 `_grid_or_none` 同一条理由：`allow_nan=False`。"""
    return [float(v) if np.isfinite(v) else None for v in np.asarray(values).ravel()]


CURVE_NOTE = (
    "这条曲线没有施加竖直软单调投影：软投影要同一时刻的竖直邻点，"
    "单点没有邻点可投影。相邻时刻之间的差是真实的；竖直方向的单调性"
    "在单点上无从谈起。"
)


@router.get("/field/curve")
def get_curve(
    shed: str = Query(..., description="棚号"),
    x: float = Query(..., description="棚长方向坐标 / m"),
    z: float = Query(..., description="高度 / m"),
) -> dict[str, Any]:
    """某个点在整个时间轴上的温度。拱外或落在无测量带里 → 全 null、「无定义」。"""
    if shed not in C.SHED_ORDER:
        allowed = "、".join(C.SHED_ORDER)
        raise HTTPException(400, f"认不出的 shed：{shed!r}（可选：{allowed}）")

    pipe = deps.get_pipeline()
    n_times = int(pipe.ds.wide.shape[0])
    y = float(C.SHED_Y[shed])

    # 拱内判定用库自己的 arch_mask（1×1 网格）—— 界面上不重算几何，
    # 后台也不重打一遍规则。库改了拱的定义，这里跟着改，不会漂。
    inside = bool(arch_mask(np.array([[x]]), np.array([[z]]))[0, 0])
    defined = inside and z <= C.MAX_MEASURED_Z

    if defined:
        coords = np.array([[x, y, z]], dtype=float)
        # 一次算完这个点的所有时刻。写成逐时刻循环就是 1308 次二维场构建。
        values = pipe.predict_points(coords, np.arange(n_times)).reshape(-1)
    else:
        values = np.full(n_times, np.nan)

    return {
        "shed": shed,
        "x": float(x),
        "y": y,
        "z": float(z),
        "label": f"{shed}  x {x:.2f}  z {z:.2f}",
        "n_times": n_times,
        "time": [str(v) for v in pipe.ds.wide[C.COL_TIMESTAMP]],
        "values": _finite_or_none(values),
        "defined": bool(defined),
        "note": CURVE_NOTE,
    }
