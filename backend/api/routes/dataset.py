"""数据集资源。"""
from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException

from tfield import config as C

from .. import deps, paths, ported

router = APIRouter(tags=["dataset"])


@router.get("/dataset")
def get_dataset() -> dict[str, Any]:
    path = paths.dataset_path()
    try:
        ds = deps.get_dataset(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"数据集不存在：{path}")
    ts = ds.wide[C.COL_TIMESTAMP]
    return {
        "signature": ds.signature,
        "file": path.name,
        "n_times": int(ds.wide.shape[0]),
        "n_columns": int(ds.wide.shape[1]),
        "time_start": ts.iloc[0].isoformat(),
        "time_end": ts.iloc[-1].isoformat(),
        "sheds": {s: float(y) for s, y in ds.sheds.items()},
        "positions": [
            {"id": pos, "x": float(p.x), "z": float(p.z), "layer": p.layer}
            for pos, p in ds.layout.items()
        ],
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
