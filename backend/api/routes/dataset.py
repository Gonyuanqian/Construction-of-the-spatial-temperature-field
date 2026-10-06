"""数据集资源。"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException

from tfield import config as C

from .. import deps, paths, ported

router = APIRouter(tags=["dataset"])


@router.get("/dataset")
def get_dataset() -> dict[str, Any]:
    # ⚠️ **不再显式传 path**。以前这里写 `deps.get_dataset(paths.dataset_path())`，
    # 于是它绕过了「空态」，永远读交付数据集 —— 与规格书 §1.1「不预置、不代劳」
    # 正相反，而且**不报错**：界面看起来一切正常，只是用的不是用户导的那一份。
    #
    # 现在问的是「现在在用哪一份」：
    #   空态      → `deps.current_dataset_path()` 抛 `NoDatasetError`，main.py 翻成 409
    #   文件不见了 → `get_dataset()` 抛 `FileNotFoundError`，下面接住翻成 404
    cur = deps.current_dataset_path()
    try:
        ds = deps.get_dataset()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"数据集不存在：{cur}")
    ts = ds.wide[C.COL_TIMESTAMP]
    codes = _point_codes(ds)
    return {
        "signature": ds.signature,
        "file": cur.name,
        "n_times": int(ds.wide.shape[0]),
        "n_columns": int(ds.wide.shape[1]),
        # 页① 那排卡片要的另外两格。**都由后端算**：前端不做任何数值计算。
        #
        # `n_missing` 是缺失的**格子**数（不是「有缺失的行数」），与
        # `ported.check_missing` 同一口径 —— 同一屏上两个「缺失」必须是一个意思。
        #
        # `n_dup_times` 来自修复**前**的原始轴（`FixReport.duplicate_count`）。
        # 修完的轴严格递增（不递增就直接抛），拿它算这个数恒为 0 —— 那样这一格
        # 就成了一句永远不变的套话，而不是「这份数据从哪来」。
        "n_missing": int(ds.wide.isna().sum().sum()),
        "n_dup_times": int(ds.fix.duplicate_count),
        "time_start": ts.iloc[0].isoformat(),
        "time_end": ts.iloc[-1].isoformat(),
        "sheds": {s: float(y) for s, y in ds.sheds.items()},
        "positions": [
            {"id": pos, "x": float(p.x), "z": float(p.z), "layer": p.layer}
            for pos, p in ds.layout.items()
        ],
        # 测点编号单独一格，**不塞进 `positions`**：那一格是几何
        # （`test_测点的几何形状没有被这次改动动到` 守着），而编号是展示。
        # 混在一起的话，每个读 `positions` 的地方都要重新想一遍
        # 「多出来的那个字段是不是几何」。
        "point_codes": codes,
        "fix": {
            "n_rows": ds.fix.n_rows,
            "fixed_indices": list(ds.fix.fixed_indices),
            # 修复前后都报：① 页要拿「修复后单调」当作一条校验通过的证据，
            # 而「修复前不单调」正是这条校验存在的理由，缺一半就讲不清。
            "monotonic_before": ds.fix.monotonic_before,
            "monotonic_after": ds.fix.monotonic_after,
            "spacing_seconds": ds.fix.spacing_seconds,
            "n_gaps": len(ds.fix.gaps),
        },
        "checks": [
            {"no": r.no, "name": r.name, "what": r.what,
             "status": r.status, "evidence": r.evidence}
            for r in ported.dataset_checks(ds)
        ],
        "checks_note": ported.checks_note(),
        "temperature": _temperature_stats(ds),
    }


def _point_codes(ds) -> dict[str, str]:
    """测点的展示编号：`B1`、`B2`……（页① 切面图上点旁那一个）。

    **不来自数据集。** `测点字典` sheet 里只有设备通道号（`1, 0.15, 0.40`
    —— 1 是棚 1、3 是棚 2、5 是棚 3），没有 B 编号。这一套是用户给的那张
    切面图上的编号，次序从图上逐点抄下来：**先按高度分层、层从高到低
    （拱顶那层在前），同层按 x 从左到右。**

    为什么在后端算：编号是**屏上要显示的字符串**，而前端不做任何计算
    （spec §六 硬约束 1）。为什么落在这里而不是 `tfield` 库里：它是展示
    约定，不是数据 —— 库里放的是这个棚怎么长的，不是这张图怎么标。

    按规则算而不是写一张八行的表：换一份数据集时表会缺项，而缺项在图上
    表现为「有几个点没编号」，最容易被当成有意为之。规则永远覆盖得住，
    而规则本身由 `test_测点编号按参考图的次序排` 钉在参考图的那八个编号上。
    """
    order = sorted(ds.layout.items(), key=lambda kv: (-kv[1].z, kv[1].x))
    return {pos: f"B{i}" for i, (pos, _) in enumerate(order, start=1)}


def _finite(v: float) -> float | None:
    """把非有限浮点（NaN / ±Inf）翻成 None。

    ⚠️ 这不是洁癖：响应由 Starlette 的 `JSONResponse` 序列化，它用
    `json.dumps(..., allow_nan=False)`。任何 NaN/Inf 一旦进了响应体就是
    `ValueError` → HTTP 500，而不是 null —— 这件事在本项目上实测过。
    """
    f = float(v)
    return f if math.isfinite(f) else None


def _temperature_stats(ds) -> list[dict[str, Any]]:
    """每个 (棚, 测点) 的全时段均值 / 最小 / 最大。

    为什么由后端算：V1 要在测点旁边标 5 天均值，而「求个平均」是数值计算 ——
    前端不做（spec §六 硬约束 1）。Streamlit 版的 `fig_layout` 也是在这里算的。

    为什么是 (棚, 测点) 而不是只有测点：三个棚并排画，同一个点位在三座棚里
    的均值是不一样的，只报一个数就把三座棚画成一样了。

    ⚠️ 退化输入必须挡住，否则会 500：全缺失列 → mean/min/max 全是 NaN；
    空列 → pandas 的 min()/max() 直接抛 ValueError。两者都翻成 None，
    因为 `JSONResponse(allow_nan=False)` 不吃 NaN/Inf（见 `_finite`）。
    """
    out: list[dict[str, Any]] = []
    for shed in C.SHED_ORDER:
        for pos in ds.layout:
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col not in ds.wide.columns:
                continue
            v = ds.wide[col].astype(float)
            if len(v) == 0:
                stat: dict[str, float | None] = {"mean": None, "min": None, "max": None}
            else:
                stat = {"mean": _finite(v.mean()), "min": _finite(v.min()),
                        "max": _finite(v.max())}
            out.append({"shed": shed, "position": pos, **stat})
    return out


# ── 页① 的两张图 ──


def _load() -> Any:
    """取当前在用的数据集；文件不在时翻成 404，与 `/api/dataset` 同一口径。

    走 `deps.get_dataset()`（无 path）—— 它问的是「现在在用哪一份」，
    空态会抛 `NoDatasetError`，由 `main.py` 的全局 handler 翻成 409。
    这里只接住 `FileNotFoundError`：那是另一种错，404。

    ⚠️ 404 的 detail 报的是**当前那份**的路径，不再是 `paths.dataset_path()`
    （交付数据集）。报错里给一个不是正在用的路径，等于把人指错地方。
    """
    try:
        return deps.get_dataset()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"数据集不存在：{deps.current_dataset_path()}",
        ) from None


def _sensor_keys(ds) -> list[tuple[str, str, str]]:
    """→ [(key, shed, position)]，key = "p1|x0.15_z0.4"。顺序固定。"""
    out: list[tuple[str, str, str]] = []
    for shed in C.SHED_ORDER:
        for pos in ds.layout:
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col in ds.wide.columns:
                out.append((f"{shed}|{pos}", shed, pos))
    return out


@router.get("/dataset/timeseries")
def get_timeseries() -> dict[str, Any]:
    """V2 的上格与下格。

    **下格那个「减去背景」是这里算的**，不是前端（spec §六 硬约束 1）。
    前端做这一步的话，界面上显示的数与后端算出的数就成了两条独立的计算路径 ——
    漂了不会报错，只会让人对着一个错的数做判断。

    `detrended_domain` 由后端给出 ±3 °C：纵轴范围也是判断的一部分，
    让前端各自去猜会得到三个棚不同的纵轴，并排看就失去意义。

    ⚠️ 每个数都过 `_finite`：任何非有限浮点（某列有缺失时，原始棚温与
    「棚温 − 背景」都会是 NaN）一旦进响应体，`JSONResponse(allow_nan=False)`
    就抛 `ValueError` → HTTP 500。翻成 None（JSON null）才是「这段没有值」。
    """
    ds = _load()
    wide = ds.wide
    bg = wide[C.BG_TEMP].to_numpy(float)

    sensors: dict[str, list[float | None]] = {}
    detrended: dict[str, list[float | None]] = {}
    means: dict[str, list[float | None]] = {}
    dmeans: dict[str, list[float | None]] = {}

    for key, shed, pos in _sensor_keys(ds):
        v = wide[f"{shed}_{pos}_{C.VAR_TEMP}"].to_numpy(float)
        sensors[key] = [_finite(a) for a in v]
        detrended[key] = [_finite(a - b) for a, b in zip(v, bg)]

    for shed in C.SHED_ORDER:
        cols = [f"{shed}_{pos}_{C.VAR_TEMP}" for pos in ds.layout
                if f"{shed}_{pos}_{C.VAR_TEMP}" in wide.columns]
        m = wide[cols].to_numpy(float).mean(axis=1)
        means[shed] = [_finite(a) for a in m]
        dmeans[shed] = [_finite(a - b) for a, b in zip(m, bg)]

    ts = pd.to_datetime(wide[C.COL_TIMESTAMP])
    return {
        "n_times": int(len(wide)),
        "time": [t.isoformat() for t in ts],
        "bg_temp": [_finite(a) for a in bg],
        "sensors": sensors,
        "shed_mean": means,
        "detrended": detrended,
        "detrended_mean": dmeans,
        "detrended_domain": [-3.0, 3.0],
        "note": ("下面那一格是棚温减背景温度；减法在后端做，前端只负责画。"
                 "减去昼夜之后剩下的才是空间信号。"),
    }


@router.get("/dataset/layer-timeheight")
def get_layer_timeheight(step: int | None = None) -> dict[str, Any]:
    """V2 的第三格：「时间 × 高度」热图。

    **数据源是实测棚温，不是模型预测。** 页① 回答的是「信号藏在哪」，
    那就该看实测值。Streamlit 版这张图走的是 `pipe.predict_points`
    （`app/app.py:1809`），那会让数据页依赖训练好的模型 —— 见本任务的 Ruling。

    行 = 层：同一层的多个测点合成一行（z0.4 上有三个点），
    但**拱顶那两个测点高度同为 1.10 m、x 不同**，合成一行就把前坡后坡的差别抹了，
    所以它们按 x 分开列。行序按 (z, x) 升序 —— 低的在下面。

    1308 个时刻画不出条纹，等间隔抽稀到 300 列上下。

    ⚠️ 矩阵里的每个格子都过 `_finite`：某一层的三个测点若在某时刻全缺失，
    `groupby.mean()` 会给 NaN，直接进响应体就是 HTTP 500（非有限值必须在
    序列化之前翻成 null）。空出的一格仍是合法的热图输入。
    """
    ds = _load()
    wide = ds.wide
    n_t = len(wide)
    step = max(1, n_t // 300) if step is None else max(1, int(step))
    idx = list(range(0, n_t, step))
    ts = pd.to_datetime(wide[C.COL_TIMESTAMP])

    out: dict[str, Any] = {}
    for shed in C.SHED_ORDER:
        labels: list[str] = []
        zs: list[float] = []
        xs: list[float] = []
        rows: list[list[float]] = []
        for pos, sp in ds.layout.items():
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col not in wide.columns:
                continue
            # 拱顶两点 layer 都是 ztop —— 用 x 把标签分开
            labels.append(f"zH({sp.x:.2f})" if sp.layer == "ztop" else sp.layer)
            zs.append(float(sp.z))
            xs.append(float(sp.x))
            rows.append([float(a) for a in wide[col].to_numpy(float)[idx]])

        df = pd.DataFrame(rows, index=labels, columns=idx)
        order = (pd.DataFrame({"label": labels, "z": zs, "x": xs})
                 .drop_duplicates("label").sort_values(["z", "x"])["label"].to_numpy())
        z_of = {lb: z for lb, z in zip(labels, zs)}
        mat = df.groupby(level=0, sort=False).mean().reindex(order)
        out[shed] = {
            "labels": [str(v) for v in order],
            "z": [float(z_of[str(v)]) for v in order],
            "values": [[_finite(x) for x in row]
                       for row in mat.to_numpy(float).tolist()],
        }

    return {
        "step": step,
        "n_times": int(n_t),
        "n_columns": len(idx),
        "time": [ts.iloc[i].isoformat() for i in idx],
        "x_label": f"时刻（每 {step} 个时刻取一个）",
        # Ruling P2：这句会由前端直接渲染，属用户可见字符串 ——
        # brief 原文用的是带空格的破折号（禁用连接符），改成「；」，句意未变。
        "source": "实测棚温（每层各测点的实测值取均值），不是模型预测",
        "sheds": out,
    }
