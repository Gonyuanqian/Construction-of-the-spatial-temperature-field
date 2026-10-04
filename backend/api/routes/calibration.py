"""页② 第二三段：最优参数的选择与模型训练的效果。

**这个文件只读。** 启动标定是一个长任务子系统（提交、轮询、取消，
`max_output_workers=1`），它要先有一个能在页面上改特征组的界面才有意义 ——
那是页② 的第二轮。本计划只回答「有没有包、包里是什么」。

⚠️ **这一页最大的谎是「最优参数」四个字。** 那个「最优」最优的对象是
**这一份数据集 + 这一组特征组 + 留一测点这个准则**，而且只在 A 组上挑出来的。
`CALIBRATION_NOTE` 因此**随数据一起从后端来**，不让前端各自去写。
"""
from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter

from tfield import config as C
from tfield.calibration import load_for
from tfield.pipeline import PipelineConfig

from .. import deps, paths, ported

router = APIRouter(tags=["calibration"])

#: 标定包读哪儿。做成模块级常量而不是直接写 `paths.CONFIGS`：
#: 这是「这个路由读哪儿」的**单一可替换点**（测试要能把它指到空目录上，
#: 才能验「没有包时」那条路径）。
CONFIGS_ROOT = paths.CONFIGS

#: 口径说明。缺了它，页② 上那几个数就会被读成「这个模型的最好水平」。
CALIBRATION_NOTE = (
    "「最优」最优的对象是**这一份数据集 + 这一组特征组 + 留一测点这个准则**，"
    "而且参数只在 A 组（调参组）上挑出来的 —— B 组（报告组）自始至终只报数。"
    "没有标定包时用的是 `FALLBACK_*` 兜底参数：那不是最优，只是不在坏角上。"
    "**兜底参数与标定后的数同折族、不同参数，两个数不可直接比大小。**"
)

NO_BUNDLE_REASON = (
    "这一份数据集还没有标定包。下面报的是兜底参数 —— 它不是最优，"
    "只是不在坏角上；要拿到最优参数需要跑一次标定。"
)

_AB_NOTE = ("gap = A 组 MAE − B 组 MAE。**负数是好消息**：A 组是挑参数用的那一组，"
            "它比 B 组好是必然的；这个差有多大，才说明「调参调出来的是不是只对 A 组有效」。")


@router.get("/calibration")
def get_calibration() -> dict[str, Any]:
    ds = deps.get_dataset()
    bundle = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=CONFIGS_ROOT)

    if bundle is None:
        cfg = PipelineConfig.fallback()
        return {
            "present": False,
            "reason": NO_BUNDLE_REASON,
            "created_at": None, "tool_version": None,
            "groups_sig": None, "dataset_sig": ds.signature,
            "feature_groups": list(C.DEFAULT_FEATURE_GROUPS),
            "trend_kind": cfg.trend_kind,
            "tuned_keys": [], "plateau": [], "lz_note": None,
            "params": _fallback_params(cfg),
            "metrics": [], "per_point": [], "ab": None,
            "fold_kind": None, "n_folds": 0, "worst_fold": None,
            "ab_note": _AB_NOTE,
            "note": CALIBRATION_NOTE,
        }

    # 原始记录先留一份：「最差的那一折」必须从**原始数值**里挑（见 _worst_fold）。
    # 一旦先过了 `_jsonable`，NaN 已成 None，再对它 float(...) 就是 TypeError → 500。
    raw_metrics = bundle.metrics.to_dict(orient="records")
    metrics = [
        {k: (str(v) if k in ("fold", "region", "group", "tag") else _jsonable(v))
         for k, v in row.items()}
        for row in raw_metrics
    ]
    per_point = [
        {k: (str(v) if k in ("shed", "position", "layer", "group") else _jsonable(v))
         for k, v in row.items()}
        for row in bundle.per_point.to_dict(orient="records")
    ]
    worst = _worst_fold(raw_metrics)
    fold_kinds = sorted({str(r["fold_kind"]) for r in metrics})

    return {
        "present": True,
        "reason": None,
        "created_at": bundle.created_at,
        "tool_version": bundle.tool_version,
        "groups_sig": bundle.groups_sig,
        "dataset_sig": bundle.dataset_sig,
        "feature_groups": list(bundle.feature_groups),
        "trend_kind": bundle.trend_kind,
        "tuned_keys": _tuned_keys(bundle),
        "params": _params(bundle),
        "plateau": [{"dim": k, "lo": ported.fmt_value(lo), "hi": ported.fmt_value(hi)}
                    for k, (lo, hi) in bundle.search.plateau.items()],
        "lz_note": _lz_note(bundle),
        "metrics": metrics,
        "per_point": per_point,
        # ab 里的三个数也是从包里来的浮点，同样要过 `_finite`（见其说明）。
        "ab": {k: _finite(v) for k, v in bundle.ab.items()} if bundle.ab is not None else None,
        "fold_kind": fold_kinds[0] if len(fold_kinds) == 1 else None,
        "n_folds": len(metrics),
        # worst 可能为 None：一折都没有有限 MAE 时，不硬报一折（见 _worst_fold）。
        "worst_fold": worst,
        "ab_note": _AB_NOTE,
        "note": CALIBRATION_NOTE,
    }


def _finite(v: float | None) -> float | None:
    """把非有限浮点（NaN / ±Inf）翻成 None。

    与 `routes/dataset.py::_finite` **同一手法**（照抄，不另发明一种）：
    响应由 Starlette 的 `JSONResponse` 序列化，它用
    `json.dumps(..., allow_nan=False)`。任何 NaN/Inf 一旦进了响应体就是
    `ValueError` → HTTP 500，而不是 null —— 这件事在本项目上实测过。

    标定包的 `metrics` / `per_point` / `ab` 是从盘上包读进来的 pandas 数值，
    `float(cell)` 对 NaN 单元格**照样返回 NaN**，不挡就会 500。

    ⚠️ 开头的 None 短路不是洁癖：这条路径上会把**已经置空过一次**的值再送进来
    （例如 `_jsonable` 已翻过的 NaN），`float(None)` 会抛。加上它之后
    `_finite` 对自己幂等，怎么重复过都不出错。
    """
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _worst_fold(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """MAE 最大的一折 —— 从**原始**记录里挑，一折都没有有限 MAE 时返回 None。

    ⚠️ 不能拿已过 `_jsonable` 的那一份挑：那时 NaN 已是 None，`float(None)`
    直接抛 TypeError → HTTP 500。也不能「全 NaN 时硬报第一折」——
    把这些折都报成「最差」是句谎话，而这一页最怕的就是口径不清。
    """
    worst_row: dict[str, Any] | None = None
    worst_mae: float | None = None
    for row in rows:
        v = row.get("mae")
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(f):
            continue
        if worst_mae is None or f > worst_mae:
            worst_mae, worst_row = f, row
    if worst_row is None:
        return None
    return {"fold": str(worst_row["fold"]), "mae": _finite(worst_row["mae"])}


def _jsonable(v):
    """numpy 的标量不是 JSON 可序列化的 —— 转成 Python 标量。

    ⚠️ 不要靠 `float(v)` 一把抓：`group` 是字符串、`n` 是整数，
    一律 float 会把整数变成 `3924.0`，界面上就多出一个小数点。

    浮点分支再过一道 `_finite`：非有限值必须在序列化之前翻成 null。
    """
    import numpy as np
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return _finite(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float):
        return _finite(v)
    return v


#: `bundle.tuned_keys` 的键 → `bundle.search.space` 的键。
#:
#: **两个键空间不一样，这是实测出来的，不是设计。**
#: `tuned_keys` 里参数叫 `metric.power`，而 `search.space` 里同一维叫 `idw.power`；
#: `cross_shed` 在调参侧光秃秃一个词，在搜索侧却挂了 `idw.` 前缀。
#: 拿 `k.replace("metric.", "idw.")` 一把梭会漏掉 `cross_shed` ——
#: 它的搜索空间会静默显示成「—」，看起来像「这一维没搜过」。
_SPACE_KEY = {
    "metric.power": "idw.power",
    "metric.lx": "idw.lx",
    "metric.lz": "idw.lz",
    "cross_shed": "idw.cross_shed",
}
#: `trend.*` 两边同名，直接透传。


def _tuned_keys(bundle) -> list[dict[str, Any]]:
    """明写「以下参数真的进过搜索空间」—— 与 `bundle.tuned_keys` 一一对应。

    值的一面是「挑出来是多少」，空间的一面是「是从哪些值里挑的」。
    少了任何一面，「最优参数」就没法被质疑。
    """
    space = bundle.search.space
    out = []
    for k in bundle.tuned_keys:
        cand = list(space.get(_SPACE_KEY.get(k, k), []))
        out.append({
            "key": k,
            "value": ported.fmt_value(_tuned_value(bundle, k)),
            "space": "、".join(ported.fmt_value(v) for v in cand) if cand else "—",
        })
    return out


def _tuned_value(bundle, key):
    """把 `metric.power` / `cross_shed` / `trend.max_depth` 这样的键读回真值。"""
    if key == "cross_shed":
        return bundle.cross_shed
    head, _, tail = key.partition(".")
    if head == "metric":
        return getattr(bundle.metric, tail)
    if head == "trend":
        return bundle.trend_params.get(tail)
    return None


def _params(bundle) -> list[dict[str, str]]:
    m = bundle.metric
    tp = bundle.trend_params
    rows = [
        ("metric.power", m.power, "IDW 距离幂"),
        ("metric.lx", m.lx, "IDW 棚长方向尺度 / m"),
        ("metric.ly", m.ly, "固定 1.0 —— 从未进过搜索空间"),
        ("metric.lz", m.lz, "IDW 竖直方向尺度 / m"),
        ("cross_shed", bundle.cross_shed, "跨棚邻居是否参与（独立开关，不是 metric 字段）"),
    ]
    for k in ("objective", "max_depth", "learning_rate", "n_estimators",
              "min_child_weight", "subsample", "colsample_bytree", "reg_lambda"):
        rows.append((f"trend.{k}", tp.get(k), ""))
    return [{"param": p, "value": ported.fmt_value(v), "note": note}
            for p, v, note in rows]


def _fallback_params(cfg) -> list[dict[str, str]]:
    m = cfg.metric
    rows = [
        ("metric.power", m.power, "IDW 距离幂"),
        ("metric.lx", m.lx, "IDW 棚长方向尺度 / m"),
        ("metric.ly", m.ly, "固定 1.0 —— 从未进过搜索空间"),
        ("metric.lz", m.lz, "IDW 竖直方向尺度 / m"),
        ("cross_shed", cfg.cross_shed, "跨棚邻居是否参与"),
    ]
    for k, v in cfg.trend_params.items():
        if k in ("n_jobs", "tree_method", "verbosity", "random_state"):
            continue
        rows.append((f"trend.{k}", v, ""))
    return [{"param": p, "value": ported.fmt_value(v), "note": note}
            for p, v, note in rows]


def _lz_note(bundle) -> str | None:
    """lz 落在搜索下界 = 还没扫够，不能当已收敛。含义是「IDW 主要吃同层邻居」。

    与 `app/app.py:653` 的 `lz_boundary_note` 同源。本项目的包正好踩在这上面
    （lz = 0.005 = 下界），所以这一条在界面上会真的出现，不是理论上的分支。
    """
    lo = min(bundle.search.space["idw.lz"])
    if abs(bundle.metric.lz - lo) < 1e-12:
        return (f"⚠️ lz = {ported.fmt_value(bundle.metric.lz)} 落在搜索下界"
                f"（{ported.fmt_value(lo)}）—— 这**不是**已收敛，而是「还没扫够」。"
                f"可以解释为 IDW 主要吃同层邻居，但在外扩下界复测之前不要当成结论。")
    return None
