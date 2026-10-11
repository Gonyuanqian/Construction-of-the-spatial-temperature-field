"""空间场的几何与取值。

页③（V5 切面场）的三个接口住在这里：`/field/sections`、`/field/curve`、
`/field/compare`；页③ 的三维视图（V7 棚体）走 `/field/volume`。

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
from tfield.field.build import available_sheds, field_at, section_field
from tfield.field.constraints import MonotonicConfig, light_at
from tfield.field.grid import GRID_PRESETS, GridSpec

from .. import deps

from time import perf_counter

router = APIRouter(tags=["field"])

#: 拱线折线的点数。121 点 → 每 0.0175 m 一段：屏幕上一像素以内，
#: 而 JSON 只有两百多个数。**点数由后端定**，前端不生成几何。
ARCH_SAMPLES = 121

DEFAULT_PRESET = "standard"

#: 整卷的格子数上限。**挡住的是 `preset=export`**：dx=0.02 把格子数放大 25 倍
#: （106 × 66 = 6996 一片），默认 37 片就是 258852 个格子、十几 MB 载荷 ——
#: 而这条路上既没有大小上限也没有 gzip（规格书 §三、§九）。
#: 正常用法留足余量：standard 下 y_step=0.125（145 片）是 168345，仍在限内。
VOLUME_MAX_CELLS = 200_000

#: 片间隔上限 / m。比 6 m 还疏的话整卷只有三四片，「体」就不成立了。
_Y_STEP_MAX = 6.0

#: 浮点容差。`y_min + k · y_step` 与 `C.SHED_Y[s]` 的比较用它 ——
#: y_step = 0.1 时 30 × 0.1 = 3.0000000000000004，不认容差就漏掉一片实测断面。
_Y_EPS = 1e-9


def _y_plane_count(y_min: float, y_max: float, y_step: float) -> int:
    """片数。**先算数、后分配** —— `_y_planes` 会按这个数建一个数组，
    所以判上限必须排在它前面（见 `get_volume`）。"""
    span = float(y_max) - float(y_min)
    q = span / float(y_step)
    # `span / y_step` 溢出 float（步长小到 5e-324 那种）时它给不出一个有限的片数。
    # **不能让它落到 `int()` 上** —— 那是 OverflowError，也就是 500。无论它到底是
    # 多少，片数乘以 nx·nz（至少 1）都必然超过格子上限，所以拿哨兵顶上：
    # 调用方永远得到一个能被 `_check_volume_size` 挡下的整数。
    if not np.isfinite(q):
        return VOLUME_MAX_CELLS + 1
    return int(np.floor(q + _Y_EPS)) + 1


def _y_planes(y_min: float, y_max: float, y_step: float) -> np.ndarray:
    """`y_min + k · y_step`，取到**不超过** `y_max` 的最后一个。至少一片。

    用 `floor(span / y_step + eps)` 而不是 `np.arange(y_min, y_max, y_step)`：
    arange 的端点判据是浮点的，「正好整除」的那些情形（0 到 18、步长 0.5）
    会随二进制表示时多时少一片 —— 而片数是**载荷大小与上限判定**的一部分，
    不能靠运气。规格书 §三 那几个数（19 / 37 / 73 片）就是这条的参照。

    片数一律由 `_y_plane_count` 给 —— 判上限用的和这里分配的必须是同一个数。
    **调用方先按它判上限**（`_check_volume_size`），再进来分配。
    """
    return float(y_min) + np.arange(_y_plane_count(y_min, y_max, y_step)) * float(y_step)


def _check_y_range(y_min: float, y_max: float, y_step: float) -> None:
    if not (y_step > 0):                     # 顺手挡下 NaN
        raise HTTPException(400, f"y_step 必须大于 0：{y_step}")
    if y_step > _Y_STEP_MAX:
        raise HTTPException(400, f"y_step 太大：{y_step}（上限 {_Y_STEP_MAX} m）")
    # `-inf < 18` 是成立的，所以光比大小挡不住无限区间；而它的跨度是 inf，
    # 后面的片数算式只会得到一个「反正超上限」的哨兵数 —— 那句提示对改参数的人
    # 没有用（他会去调 y_step，而问题在 y_min）。这里先按原话挡下来。
    if not (np.isfinite(y_min) and np.isfinite(y_max)):
        raise HTTPException(400, f"y_min / y_max 必须是有限数：{y_min} / {y_max}")
    if not (y_min < y_max):
        raise HTTPException(400, f"y_min 必须小于 y_max：{y_min} / {y_max}")


def _check_volume_size(nx: int, nz: int, n_planes: int) -> None:
    total = int(nx) * int(nz) * int(n_planes)
    if total > VOLUME_MAX_CELLS:
        raise HTTPException(400, (
            f"这一卷有 {total} 个格子，超过上限 {VOLUME_MAX_CELLS}"
            f"（{nx} × {nz} × {n_planes}）。把 y_step 调大，或换更粗的 preset。"
        ))


def _measured_at(y: float, avail: tuple[str, ...]) -> tuple[bool, str | None]:
    """这一片是不是**实测断面**。判据是 `available_sheds`，**不是** `C.SHED_Y` 这个常数。

    留一断面时被留出的棚不在可用集里，`field_at(y = 9)` 会去混合 p1 与 p3 ——
    那时 y = 9 是算出来的。按「y ∈ {3, 9, 15}」标成实测就是说反了（规格书 §四.3）。
    主折（留一测点）下三座棚都在，行为与原来完全一样；换折时它才显出不样来 ——
    而那正是它该显出来的时候。
    """
    for s in avail:
        if abs(float(y) - float(C.SHED_Y[s])) < _Y_EPS:
            return True, s
    return False, None


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

    退化保护（`vmax - vmin < 0.2` 时各让 0.1）是一条**独立的规则**：
    不让色标塌成零宽，否则一整张场是一个颜色，看起来像「处处一样温」。
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
    t_index = _check_t_index(t_index, pipe.n_times)
    return sections_payload(pipe, t_index=t_index, preset=preset,
                            monotonic=monotonic, grid=grid)


def sections_payload(pipe, *, t_index: int, preset: str, monotonic: bool,
                     grid: GridSpec | None = None) -> dict[str, Any]:
    """页③ 断面那一屏的载荷。**实时模式的 `frame/{n}` 用的就是这个函数。**

    没有校验、没有取管线 —— 那两件事留在路由里（`test_拒绝路径不碰管线`
    钉着「参数坏就不该等一次 fit」这条顺序）。
    """
    grid = grid or _check_preset(preset)
    n_times = pipe.n_times
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

    return {
        "t_index": t_index,
        "time": str(pipe.time_at(t_index)),
        "n_times": n_times,
        "preset": preset,
        "monotonic": bool(monotonic),
        "calibrated": bool(getattr(pipe, "calibrated", False)),
        "mismatch_note": str(getattr(pipe, "mismatch_note", "")),
        "artifact_note": str(getattr(pipe, "artifact_note", "")),
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


def _mean_in_arch(fields: list) -> float | None:
    """这几片里**拱内、且不在无测量带里**那些格子的平均温度。

    ⚠️ 三个坑都在这三行里，少踩一个这个数就是错的，而且屏上没有任何提示：

    1. **拱外那些格子是 NaN**（`build.py` 用 `np.where(arch_mask, values, np.nan)`），
       所以掩膜必须用 `f.mask`。直接 `f.values.mean()` 得到 NaN —— 而
       `JSONResponse(allow_nan=False)` 会把 NaN 变成 500，「不画」是一个正常的
       答案，不是一次故障。
    2. **z 高于 `C.MAX_MEASURED_Z` 那一条是外推出来的**。`f.outside_measured`
       已经与 `f.mask` 求过交（`types.py` 的字段注释），所以 `& ~f.outside_measured`
       一次就把它摘干净。不摘的话这个数会**偏高** —— 拱顶下没有测点，
       那里是按上下的测点推出来的。
    3. **平均在软单调投影之后取**。`f.values` 是投影后的场（`field_at(...,
       monotonic=cfg)` 交出来的），所以这里什么都不用做；但**换序就等于换了一个数**：
       先平均再投影，与先投影再平均，结果不一样。

    传的是**一串** `Field`（一片也行、整卷也行）：整卷那份要是**合起来**算的，
    不是各片均值的平均 —— 两者在等权时相等，而「等权」是一个会悄悄失效的前提。

    一片都没有可用格子时返回 `None`（不是 0）：屏上「不报数」与「0 °C」是两件事。
    """
    parts = [f.values[f.mask & ~f.outside_measured] for f in fields]
    parts = [v for v in parts if v.size]
    if not parts:
        return None
    return float(np.concatenate(parts).mean())


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
    n_times = pipe.n_times
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
        "time": [str(v) for v in pipe.timestamps()],
        "values": _finite_or_none(values),
        "defined": bool(defined),
        "note": CURVE_NOTE,
    }


@router.get("/field/compare")
def get_compare(
    shed: str = Query(..., description="棚号"),
    t_index: int = Query(0, description="时刻下标"),
    preset: str = Query(DEFAULT_PRESET, description="网格档位"),
) -> dict[str, Any]:
    """竖直软单调投影的前后对比。**门禁关闭时两张图逐位相同**（夜里无光照）。

    这里走 `field_at(y = 该棚的 y)` 而不是 `section_field`：y 恰好撞上某个棚的 y 时
    `field_at` 会短路到该断面（build.py:139-142），两条路径**逐位相等** ——
    第四格画的因此就是第一格那片场。用 `section_field` 也行，但那样
    「两张图必须同源」就只是一句约定，而不是一条可测的性质。
    """
    if shed not in C.SHED_ORDER:
        allowed = "、".join(C.SHED_ORDER)
        raise HTTPException(400, f"认不出的 shed：{shed!r}（可选：{allowed}）")

    grid = _check_preset(preset)
    pipe = deps.get_pipeline()
    n_times = pipe.n_times
    t_index = _check_t_index(t_index, n_times)
    y = float(C.SHED_Y[shed])

    before = field_at(pipe, y, t_index, grid)
    after = field_at(pipe, y, t_index, grid, monotonic=MonotonicConfig(enabled=True))
    light = float(light_at(pipe, t_index))
    gate_open = light > 0

    # ΔT = 约束前 − 约束后（spec §七 V5 的签号方向）。
    # 正值 = 这一格被约束压低了；负值 = 被抬高了。
    # 单调投影沿 z 投影（PAVA 把违反块换成块内加权均值），所以两个方向都真的会出现 ——
    # 不能写成 abs()。写成 abs 的话图上就只剩「改了多少」，看不出改的方向，
    # 而那正是这张图要回答的问题。
    delta = np.asarray(before.values, dtype=float) - np.asarray(after.values, dtype=float)
    finite = np.isfinite(delta)
    delta_vmax = float(np.max(np.abs(delta[finite]))) if finite.any() else 0.0
    vmin, vmax = temp_range(before.values, after.values)
    identical = bool(np.array_equal(before.values, after.values, equal_nan=True))

    return {
        "shed": shed,
        "y": y,
        "t_index": t_index,
        "time": str(pipe.time_at(t_index)),
        "n_times": n_times,
        "preset": preset,
        "x": [float(v) for v in before.x],
        "z": [float(v) for v in before.z],
        "arch": _arch_polyline(),
        "sensors": _sensors(),
        "max_measured_z": float(C.MAX_MEASURED_Z),
        "before": _grid_or_none(before.values),
        "after": _grid_or_none(after.values),
        "delta": _grid_or_none(delta),
        # 与 /field/sections 送出的是**同一份事实**。前端不许自己从 x/z/max_measured_z
        # 推一遍 —— 那是把后端的一条规则实现了第二遍（硬约束 1）。
        # np.nonzero 返回 (行, 列) = (z, x)；契约要的是 [ix, iz]，所以接的时候倒过来。
        "stripes": [[int(c), int(r)]
                    for r, c in zip(*np.nonzero(before.outside_measured))],
        "vmin": vmin,
        "vmax": vmax,
        "delta_vmax": delta_vmax,
        "light": light,
        "gate_open": gate_open,
        "gate_label": "开（有光照）" if gate_open else "关（无光照，严格不变）",
        "identical": identical,
        "note": (
            "竖直软单调投影的逐格差，签号是「约束前 − 约束后」："
            "正值 = 这一格被约束压低了，负值 = 被抬高了。"
            "左中两格共用同一个色标范围，右格用对称的发散色标（中点必须落在 0）。"
        ),
    }


VOLUME_NOTE = (
    "整卷按 y 切成一片片，每片都是一次独立的场重建。实测断面画成实心，"
    "混合出来的逐层变透。"
    f"z 高于 {C.MAX_MEASURED_Z:.2f} m 是无测量带，带内有外推值，"
    "三维里不填色、也不报数。"
)


@router.get("/field/volume")
def get_volume(
    t_index: int = Query(0, description="时刻下标"),
    preset: str = Query(DEFAULT_PRESET, description="网格档位"),
    monotonic: bool = Query(True, description="是否施加竖直软单调投影"),
    y_step: float = Query(0.5, description="沿棚长 y 的切片间隔 / m"),
    y_min: float = Query(0.0, description="y 的起点 / m"),
    y_max: float = Query(18.0, description="y 的终点 / m"),
) -> dict[str, Any]:
    """V7 棚体三维温度场：一整卷按 y 切开的二维场。

    **逐片调用 `field_at`，一行 R2 的逻辑都不重写**（硬约束 1）。夹住 y 的是哪两个
    断面、怎么按 1/dy 加权、单调投影为什么在混合**之后**施加 —— 全部留在
    `tfield.field.build` 里。这里只做循环与装箱。

    不做那个「缓存三个断面、逐片自己混合」的优化（实测能把 1.22 s 压到约 0.06 s）：
    它要复现 `field_at` 的整套调度（可用断面的取用、两端的退化、`Y[lo] == y` 的短路、
    投影施加在混合之后），那是把 R2 实现第二遍 —— 两条路径漂了不报错，
    正是硬约束 1 要防的事。1.22 s 已经够用（规格书 §4.1）。

    **参数的合法性全在 `deps.get_pipeline()` 之前判完**：敲错一个参数不该等一次
    fit 才听到「参数不对」，而 fit 要几十秒。`test_拒绝路径不碰管线` 钉着这条。

    片数**先算、后判、最后才分配**：`_y_planes` 会按片数建一个数组，
    而 `y_step = 1e-9` 那一步要 144 GB。先分配再判上限的话，参数坏掉时
    用户拿到的不是 400 而是 OOM。`test_片数超限时不去分配那个数组` 钉着这条。
    """
    grid = _check_preset(preset)
    _check_y_range(y_min, y_max, y_step)
    _check_volume_size(grid.nx, grid.nz, _y_plane_count(y_min, y_max, y_step))

    pipe = deps.get_pipeline()
    t_index = _check_t_index(t_index, pipe.n_times)
    return volume_payload(pipe, t_index=t_index, preset=preset, monotonic=monotonic,
                          y_step=y_step, y_min=y_min, y_max=y_max, grid=grid)


def volume_payload(pipe, *, t_index: int, preset: str, monotonic: bool,
                   y_step: float, y_min: float, y_max: float,
                   grid: GridSpec | None = None) -> dict[str, Any]:
    """页③ 三维那一屏的载荷。**实时模式的 `volume/{n}` 用的就是这个函数。**

    与 `sections_payload` 同一条分工：校验与取管线留在路由里，这里只装箱。
    """
    grid = grid or _check_preset(preset)
    ys = _y_planes(y_min, y_max, y_step)
    n_times = pipe.n_times
    cfg = MonotonicConfig(enabled=True) if monotonic else None

    t0 = perf_counter()
    fields = [field_at(pipe, float(y), t_index, grid, monotonic=cfg) for y in ys]
    elapsed_ms = int(round((perf_counter() - t0) * 1000))

    avail = available_sheds(pipe)
    vmin, vmax = temp_range(*[f.values for f in fields])

    # 无测量带**只发一份**（规格书 §四.4）。它由 `outside_measured` 决定，而那一份
    # 是 `outside_measured_mask(X, Z) & mask` —— 只看网格，与 y 和棚号都无关；
    # `blend_fields` 又是取两个断面的**与**。实测 37 片完全一致，测试里钉着这条。
    # np.nonzero 返回 (行, 列) = (z, x)；契约要的是 [ix, iz]，所以接的时候倒过来。
    iz_s, ix_s = np.nonzero(fields[0].outside_measured)
    stripes = [[int(a), int(b)] for a, b in zip(ix_s, iz_s)]

    planes: list[dict[str, Any]] = []
    for y, f in zip(ys, fields):
        measured, shed = _measured_at(float(y), avail)
        planes.append({
            "y": float(y),
            "measured": measured,
            "shed": shed,
            "values": _grid_or_none(f.values),
            # 这一片的拱内均温。**后端算**，前端不重算 —— 三个坑（拱外是 NaN、
            # 无测量带是外推、平均要在投影之后）少踩一个，屏上就是一个偏高的数。
            "mean": _mean_in_arch([f]),
        })

    return {
        "t_index": t_index,
        "time": str(pipe.time_at(t_index)),
        "n_times": n_times,
        "preset": preset,
        "monotonic": bool(monotonic),
        "calibrated": bool(getattr(pipe, "calibrated", False)),
        "mismatch_note": str(getattr(pipe, "mismatch_note", "")),
        "artifact_note": str(getattr(pipe, "artifact_note", "")),
        "y_step": float(y_step),
        "y_min": float(y_min),
        "y_max": float(y_max),
        "x_min": float(C.SHED_X_MIN),
        "x_max": float(C.SHED_X_MAX),
        "z_max": float(C.SHED_Z_MAX),
        "max_measured_z": float(C.MAX_MEASURED_Z),
        "vmin": vmin,
        "vmax": vmax,
        # 本载荷这些片**合起来**的拱内均温。与逐片的同一口径、同一个函数。
        "mean": _mean_in_arch(fields),
        "x": [float(v) for v in fields[0].x],
        "z": [float(v) for v in fields[0].z],
        "arch": _arch_polyline(),
        "sheds": [{"id": s, "y": float(C.SHED_Y[s])} for s in C.SHED_ORDER],
        "sensors": _sensors(),
        "available_sheds": list(avail),
        "stripes": stripes,
        "planes": planes,
        "elapsed_ms": elapsed_ms,
        "note": VOLUME_NOTE,
    }
