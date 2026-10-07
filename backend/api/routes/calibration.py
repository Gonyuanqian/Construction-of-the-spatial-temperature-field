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

from fastapi import APIRouter, HTTPException

from tfield import config as C
from tfield.calibration import IDW_SPACE, TREND_SPACE, TUNED_KEYS, load_bundle, load_for
from tfield.pipeline import PipelineConfig

from .. import deps, diagnostics, jobs, paths, ported

router = APIRouter(tags=["calibration"])

#: 标定包读哪儿。做成模块级常量而不是直接写 `paths.CONFIGS`：
#: 这是「这个路由读哪儿」的**单一可替换点**（测试要能把它指到空目录上，
#: 才能验「没有包时」那条路径）。
CONFIGS_ROOT = paths.CONFIGS

#: 口径说明。缺了它，页② 上那几个数就会被读成「这个模型的最好水平」。
CALIBRATION_NOTE = (
    "「最优」最优的对象是这一份数据集 + 这一组特征组 + 留一测点这个准则，"
    "而且参数只在 A 组（调参组）上挑出来的；B 组（报告组）自始至终只报数。"
    "没有标定包时用的是兜底参数：那不是最优，只是不在坏角上。"
    "兜底参数与标定后的数同折族、不同参数，两个数不可直接比大小。"
)

NO_BUNDLE_REASON = (
    "这一份数据集还没有标定包。下面报的是兜底参数：它不是最优，"
    "只是不在坏角上；要拿到最优参数需要跑一次标定。"
)

_AB_NOTE = ("gap = A 组 MAE − B 组 MAE。负数是好消息：A 组是挑参数用的那一组，"
            "它比 B 组好是必然的；这个差有多大，才说明「调参调出来的是不是只对 A 组有效」。")


@router.get("/calibration")
def get_calibration() -> dict[str, Any]:
    ds = deps.get_train_dataset()     # 包是按训练段标的，这里必须问同一份
    bundle = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=CONFIGS_ROOT)

    if bundle is None:
        cfg = PipelineConfig.fallback()
        return {
            "present": False,
            "reason": NO_BUNDLE_REASON,
            "mismatch": _mismatch(ds.signature),
            "created_at": None, "tool_version": None,
            "groups_sig": None, "dataset_sig": ds.signature,
            "feature_groups": list(C.DEFAULT_FEATURE_GROUPS),
            "job": _job_summary(),
            "trend_kind": cfg.trend_kind,
            "panel": _panel(None, cfg),
            "plateau": [], "lz_note": None,
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
        "mismatch": None,
        "created_at": bundle.created_at,
        "tool_version": bundle.tool_version,
        "groups_sig": bundle.groups_sig,
        "dataset_sig": bundle.dataset_sig,
        "feature_groups": list(bundle.feature_groups),
        "job": _job_summary(),
        "trend_kind": bundle.trend_kind,
        "panel": _panel(bundle, None),
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


def _mismatch(ds_sig: str) -> dict[str, Any] | None:
    """`configs/` 下有没有**别的数据集**的标定包。

    有的话它是那份包的 `dataset_sig` / `created_at` / 文件名 —— 据此页② 能说出
    「参数与当前数据集不匹配，指标无效（上一次标定对应 <created_at>）」。

    ⚠️ 只在 `bundle is None` 这条路上被调用，所以「存在的包按定义都对不上」——
    不必再比一遍。真正要挑的是**报哪一个**：取 `created_at` 最新的那一个。
    `configs/` 里可能同时躺着好几代的包（本仓现在就有两个），挑第一个会让界面
    报出一份谁也不记得的旧包；挑最新的那个才是用户心里的「上一次」。

    读包用库的 `load_bundle()` 而不是自己 `json.loads`：包的结构（包括
    `dataset_sig` 在哪个键上）是库的知识，这里再解析一遍就是第二套口径。
    一次只在这条罕见路径上读，794 KB 的包读几个可以接受。

    不做 job API、不做「点一下就重标」的按钮（裁定 C）——
    `2026-10-01-后端架构-design.md` §6.4 逐字写着它是**离线发布流程**。
    """
    found: list[dict[str, Any]] = []
    for path in sorted(CONFIGS_ROOT.glob("bundle_*.json")):
        # ⚠️ 读不动的那一份**跳过，不是把接口打挂**。`configs/` 是离线发布流程
        # 的产出目录，人手动往里放过东西；一个写了一半的文件（磁盘满、复制中断、
        # 编辑器存到一半）在这里就是一个「半份 JSON」，而 `load_bundle` 会**抛**
        # ——`from_json` 是 `cls.from_dict(json.loads(s))`，`json.loads` 抛
        # `JSONDecodeError`，`from_dict` 缺键抛 `KeyError`。
        #
        # 这个 except 是有意写宽的：这一条路的全部意义是「页② 能不能说清上一次
        # 标定对的是谁」，它**不该**成为 200 的分支里唯一一个 500 的出口。窄捉
        # 某几种异常，等于把没列到的那一种留在原地 —— 而它的表现形式是整页崩掉。
        # 代价写在明面上：configs/ 里全是坏包时，页② 会说「这一份数据集还没有
        # 标定包」，也就是把「包坏了」说成「没标过」。两者要用户做的事是同一件
        # （跑一次标定），所以这个谎是软性的、可自愈的。
        try:
            bundle = load_bundle(path)
        except Exception:
            continue
        if bundle is None or bundle.dataset_sig == ds_sig:
            continue
        found.append({"dataset_sig": bundle.dataset_sig,
                      "created_at": bundle.created_at,
                      "file": path.name})
    if not found:
        return None
    # `created_at` 是 ISO 串，字典序就是时间序；缺失的排到最后。
    return max(found, key=lambda d: (d["created_at"] or "", d["file"]))


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


#: 面板上每一维的中文名。**只放显示名，不放候选值** ——
#: 候选值一律由 `IDW_SPACE` / `TREND_SPACE` 现取（见 `_candidates`），
#: 那是「要搜什么」的唯一定义处。
#: 键表必须与 `TUNED_KEYS` 逐字相同，有测试钉着
#: （`test_面板的标签表与调参键一一对应`）—— 库里加一个参数而这里没跟，
#: 接口当场 500，测试先红。
_LABELS = {
    "metric.power": "IDW 距离幂",
    "metric.lx": "IDW 棚长方向尺度 / m",
    "metric.lz": "IDW 竖直方向尺度 / m",
    "cross_shed": "跨棚邻居是否参与",
    "trend.objective": "目标函数",
    "trend.max_depth": "每棵树最深几层",
    "trend.learning_rate": "学习率",
    "trend.n_estimators": "树的数量",
    "trend.min_child_weight": "叶子最小样本权重和",
    "trend.subsample": "行采样比例",
    "trend.colsample_bytree": "列采样比例",
    "trend.reg_lambda": "L2 正则系数",
}

#: 不进搜索域、但面板上仍要有一行的参数（规格书 §2.3）。
#: **只给一句说明，不给控件** —— 一个拖不动的滑块比一句话更容易让人
#: 以为是自己没点对。这里是它唯一的定义处，两条路（有包 / 空态）共用。
_FIXED = {
    "metric.ly": ("IDW y 方向尺度 / m", "固定 1.0，从未进过搜索空间"),
}


def _candidates(key: str) -> list[Any]:
    """一个 `TUNED_KEYS` 键 → 它在搜索空间里的候选值。**原始类型，未印。**

    走 `_SPACE_KEY` 同一张映射 —— 面板与校验（`_validated_domain`）必须问同一处，
    否则「屏上能拖到的」与「发回去收得下的」会分成两个域。
    """
    space_key = _SPACE_KEY.get(key, key)
    head, _, tail = space_key.partition(".")
    if head == "idw":
        return list(IDW_SPACE[tail])
    if head == "trend":
        return list(TREND_SPACE[tail])
    return []


def _is_candidate(v: Any, cand: list[Any]) -> bool:
    """`v` 是不是 `cand` 里的某一个。

    ⚠️ **布尔要单独比**：Python 里 `True == 1`，而 `cross_shed` 的候选是
    `[True, False]` —— 光看 `==` 的话，客户端发来的 `1` 会被当成「开」收下，
    一个没人打算支持的输入静默生效。这里与 `_validated_domain` 共用这一个函数，
    免得只堵住一处。
    """
    return any(v == c and isinstance(v, bool) == isinstance(c, bool) for c in cand)


#: 兜底配置 `FALLBACK_TREND_PARAMS` 里没有、而搜索空间里有的那五维。
#: 取 XGBoost 自己在**没给这个键**时的默认值 —— 也就是「没包时真去训练，
#: 用的就是这个数」，面板因此说的是实话而不是一句「不知道」。
#: **放在这里而不是 `tfield/config.py`**：`tfield` 这次一个字都不许改，
#: 它还与兄弟项目共用同一份，改了就不再零差异。
#: 每一个都必须是 `TREND_SPACE` 的成员，有测试钉着。
_TREND_FALLBACK = {
    "min_child_weight": 1,
    "subsample": 1.0,
    "colsample_bytree": 1.0,
    "reg_lambda": 1,
    "objective": "reg:squarederror",
}


def _current(bundle, cfg, key: str) -> Any:
    """这一维现在取的是哪个值。有包读包，没包读兜底配置。

    ⚠️ 与 `_tuned_value` 分成两个函数是有意的：`_tuned_value` 只认包
    （`metric.power` → `bundle.metric.power`），而空态下没有包可读。

    ⚠️ **十二维一个都不许返回 `None`**。`fmt_value(None)` 会印成 `"None"`
    （一个英文单词落在中文面板上），而 `None` 又不在 `raw` 里 —— 前端的滑块
    是按下标定位的，那一格会一个档都不选中。兜底配置只带了七维，
    剩下五维去 `_TREND_FALLBACK` 取；键对不上就当场炸（与上面 `_LABELS[key]`
    同一套纪律：库动了而这里没跟，是测试该红，不是屏上该出现空白）。
    """
    if bundle is not None:
        return _tuned_value(bundle, key)
    if key == "cross_shed":
        return cfg.cross_shed
    head, _, tail = key.partition(".")
    if head == "metric":
        return getattr(cfg.metric, tail)
    if tail in cfg.trend_params:
        return cfg.trend_params[tail]
    return _TREND_FALLBACK[tail]


def _legal_values(bundle, cfg, key: str) -> list[Any]:
    """这一维**屏上能拖到的全部档位**：搜索空间的候选，加上（只有旧包才会有的）当前值。

    ⚠️ **面板与校验共用这一个函数**（`_panel` 与 `_validated_domain` 都调它）。
    抽出来不是为了少写三行，是为了让「能拖到的」与「能收下的」是**同一个对象**，
    而不是两份碰巧长得一样的代码 —— 后者只要有一处被改动，页② 就会在「拿旧版
    搜索空间训出来的包」上**第一次点开始训练就 422**，而发出去的那个值正是面板
    自己摆上去的，用户没有任何办法把它调对。
    """
    cand = _candidates(key)
    cur = _current(bundle, cfg, key)
    if cur is not None and not _is_candidate(cur, cand):
        return [*cand, cur]
    return cand


def _panel(bundle, cfg) -> dict[str, list[dict[str, Any]]]:
    """面板载荷（规格书 §3.1）：**一套值，两条来路**。

    `values` 是印在屏上的那一串（`fmt_value`），`raw` 是**要发回来的那个值**，
    两者同下标。分成两列而不是只发 `values`：否则前端要把「开」解析回 `True`、
    把 `"0.5"` 解析回 `0.5` —— 那是把**印法**当协议，`fmt_value` 一变协议就悄悄变了。

    ⚠️ 每一维的档位由 `_legal_values` 给：搜索空间的候选，加上（只有旧包才有的）
    当前值。**它与 `_validated_domain` 是同一处**，所以「屏上能选的就是后端收得
    下的」这条不变式成立，不靠两处代码碰巧一致。前端因此不必为这件事写任何分支
    （它的滑块是按下标定位的，`current` 不在 `raw` 里就会印出一片空白）。
    """
    rows: list[dict[str, Any]] = []
    for key in TUNED_KEYS:
        cur = _current(bundle, cfg, key)
        cand = _legal_values(bundle, cfg, key)
        rows.append({
            "key": key,
            "label": _LABELS[key],
            "values": [ported.fmt_value(v) for v in cand],
            "raw": cand,
            "current": cur,
        })
    fixed = [
        {"key": k, "label": label,
         "value": ported.fmt_value(_current(bundle, cfg, k)), "note": note}
        for k, (label, note) in _FIXED.items()
    ]
    return {
        "trend": [r for r in rows if r["key"].startswith("trend.")],
        "idw": [r for r in rows if not r["key"].startswith("trend.")],
        "fixed": fixed,
    }


def _job_summary() -> dict[str, Any] | None:
    """当前 / 最近一次标定任务。**读它是为了刷新之后还接得上**（规格书 §4.7）。

    标定要几分钟，而切页与刷新都会把组件连同它手上的 job id 一起丢掉
    （前端没有 KeepAlive）。页② `onMounted` 反正要调这一个接口 ——
    读到 `running` 就接着轮询那个 id，零额外请求。

    *为什么不用一条新路由 `GET /api/calibration/jobs/current`*：多一条路由
    就多一个要守的东西，而它答的是同一件事。
    """
    job = jobs.current()
    return None if job is None else job.to_dict()


@router.get("/calibration/diagnostics")
def get_diagnostics() -> dict[str, Any]:
    """页② 第三段那个「开始训练」按钮打的就是这一条（规格书 §二、§8.4）。

    它是一次**真实的训练**：八折各拟合一遍，只是不搜参数。有包就行 ——
    进程重启之后照样拿得到精度，不必重搜一次（验收 7）。

    诊断是**包的函数**（包 → 图），不是包的一部分：写进包会让老包没有图、
    要看图就得重标一次（裁定 C）。

    没包时报 409 而**不是** 200 + `present: false`：这一条没有「兜底精度」
    可以报 —— 兜底参数配上一堆图，只会让人以为那是一个可以用的模型。
    """
    ds = deps.get_train_dataset()
    groups = tuple(C.DEFAULT_FEATURE_GROUPS)
    bundle = load_for(ds, groups, root=CONFIGS_ROOT)
    if bundle is None:
        raise HTTPException(status_code=409,
                            detail="这一份数据集还没有标定包，先做一次参数优选")
    out = diagnostics.get_or_compute(ds, groups, bundle)
    return {
        "present": True,
        "created_at": bundle.created_at,
        "groups_sig": bundle.groups_sig,
        "dataset_sig": bundle.dataset_sig,
        **out,
    }


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


def _lz_note(bundle) -> str | None:
    """lz 落在搜索下界 = 还没扫够，不能当已收敛。含义是「IDW 主要吃同层邻居」。

    与 `app/app.py:653` 的 `lz_boundary_note` 同源。**本项目当前的包踩不到**：换成
    训练段重标之后 lz = 0.03，而下界是 0.005，所以这一条在界面上是 None。
    留着它是因为「踩在下界」是个会随标定回来的真实分支（换一折族、换一组特征组
    就可能踩上），而不是因为它现在会发生 —— 一个自称「本项目正好踩在上面」的
    注释，比没有注释更坏：它会让人以为界面上的警告是真看到了，而其实是没看到。
    """
    lo = min(bundle.search.space["idw.lz"])
    if abs(bundle.metric.lz - lo) < 1e-12:
        return (f"⚠️ lz = {ported.fmt_value(bundle.metric.lz)} 落在搜索下界"
                f"（{ported.fmt_value(lo)}），这不是已收敛，而是「还没扫够」。"
                f"可以解释为 IDW 主要吃同层邻居，但在外扩下界复测之前不要当成结论。")
    return None
