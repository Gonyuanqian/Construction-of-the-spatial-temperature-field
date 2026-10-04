"""数据集资源。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from tfield import config as C

from .. import deps, paths

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
    }
