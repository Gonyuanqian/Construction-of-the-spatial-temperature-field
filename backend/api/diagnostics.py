"""页② 第三段的精度面：折外预测 → 基线对照 / 密度矩阵 / 残差分箱。

**它算的每一个数都来自同一个折外长表**（`out_of_fold_predictions`）。
分成三块而不是一个大函数，是为了让每一块的「算在哪几折上」各自写在
函数上 —— 三块的口径**不一样**（密度与残差用全部八折，基线对照只用 B 组），
混在一起读不出来。

**为什么在 API 层而不在库里**：`baseline` / `hour` / `resid` / `z` / `x`
这五列是**页② 的概念**，不是库的概念。它们进库就得改库的公开形状，
而库的折外出口（`OOF_COLUMNS`）是一份契约，契约为一张页面变宽是要付利息的。
"""
from __future__ import annotations

import math
import threading
from typing import Any

import numpy as np
import pandas as pd

from tfield import config as C
from tfield.calibration import groups_signature
from tfield.data.types import Dataset
from tfield.pipeline import FieldPipeline
from tfield.validation.folds import position_folds
from tfield.validation.metrics import mae as _mae
from tfield.validation.metrics import r2 as _r2
from tfield.validation.metrics import rmse as _rmse
from tfield.validation.report import out_of_fold_predictions

from . import deps

#: 密度矩阵的边长。60×60 = 3600 格，画成热图还看得见对角线；再细就全白，
#: 再粗就把对角线上那条带子糊成一块砖。
BINS = 60

#: 基线的口径。**与 `metrics.py` 注释里那个 0.8896 不是一件事**：那个数是
#: **全量数据集**上的，这里是训练段 —— 两个数不可直接比大小（规格书 §6.2）。
BASELINE_LABEL = "拿背景温度当棚温（不作任何建模）"
MODEL_LABEL = "本模型（B 组，未参与选参）"

#: 这一整块的说明。**随数据一起从后端来** —— 让前端各自去写，迟早写成
#: 「模型精度 99.9%」而把「没有基线时那个数说明不了什么」丢了。
DIAGNOSTICS_NOTE = (
    "折外预测：每一折都用不含该测点的数据重新训练，再预测被留出的那些测点。"
    "密度图上每一点都是这样一对（预测，实测），对角线是「报得刚好」。"
    "基线拿背景温度直接当棚温，不作任何建模；它与本模型用同一批折、同一段数据，"
    "所以两个数可以并排比。倍数是算出来的，不是写死的。"
    "残差 = 预测 − 实测，正数表示报高了，误差棒是箱内平均残差的标准误。"
)

#: 三张残差图的横轴。次序即屏上的次序。
RESIDUAL_AXES = (
    ("diurnal", "残差 vs 昼夜", "hour", "时刻 / 时"),
    ("height", "残差 vs 高度", "z", "高度 z / m"),
    ("length", "残差 vs 棚长", "x", "棚长 x / m"),
)


def _finite(v: float | None) -> float | None:
    """把非有限浮点（NaN / ±Inf）翻成 None。

    与 `routes/dataset.py::_finite`、`routes/calibration.py::_finite` **同一手法**
    （本仓的既有做法是照抄，不另发明一种）。响应由 `JSONResponse` 序列化，
    它用 `json.dumps(..., allow_nan=False)` —— 任何 NaN 一旦进了响应体就是
    HTTP 500，而不是 null。

    ⚠️ 这一份**不能**从那边 import：`routes/calibration.py` 反过来要 import
    本模块（诊断出口住在它那儿），会成环。第三份是这里唯一走得通的做法。
    """
    if v is None:
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _row(truth: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    """三个指标 + 样本数。**顺序固定**：页上的列就是它。"""
    return {"mae": _finite(_mae(truth, pred)), "rmse": _finite(_rmse(truth, pred)),
            "r2": _finite(_r2(truth, pred)), "n": int(truth.size)}


def oof_table(ds: Dataset, bundle, cfg=None) -> pd.DataFrame:
    """跑一次折外预测（全 8 个 position 折），再补上诊断要用的五列。

    `cfg` 是**要跑的那套参数**；不给就用包自己那套（`bundle.config()`）。
    页② 的参数面板把用户手调的一套送进来，所以它必须是个参数而不是
    写死在函数体里 —— 那是这次改动唯一的作用点。

    补的列**不来自** `out_of_fold_predictions`（那九列是库的契约）：

    - `baseline` —— 背景温度。它是**时刻的函数**，按每一行自己的 `t_index`
      取，不广播：广播在时刻顺序没被打乱时看起来一样，只在顺序变了的时候
      静默错位。
    - `hour` —— 昼夜分箱用的时刻。定义与 `tfield.features.to_long` 的 `hour`
      相同（都取时间戳的小时）。
    - `resid` —— 折外残差 = 预测 − 实测，正 = 报高了。
    - `z` / `x` —— 点位几何。分箱要用，而库那九列里没有它们。
    """
    folds = position_folds(ds)
    # ⚠️ `cfg or bundle.config()` 让 `config()` 每折被调一次。**这是认下的**：
    # 把它提到 lambda 外面做不到（lambda 每折调一次），而它换来的是「闭包捕获的
    # 那个 `cfg` 与传进来的那个是同一个对象」这件事不必推理。重复构造的代价是
    # 一次纯 dataclass 构造，可以忽略。
    oof = out_of_fold_predictions(lambda: FieldPipeline(cfg or bundle.config(), ds),
                                  ds, folds, groups=tuple(bundle.feature_groups))
    t_index = oof["t_index"].to_numpy(int)
    oof["baseline"] = ds.wide[C.BG_TEMP].to_numpy(float)[t_index]
    oof["hour"] = pd.to_datetime(ds.wide[C.COL_TIMESTAMP]).dt.hour.to_numpy(int)[t_index]
    oof["resid"] = oof["pred"] - oof["truth"]
    oof["z"] = oof["position"].map(lambda p: float(ds.layout[p].z))
    oof["x"] = oof["position"].map(lambda p: float(ds.layout[p].x))
    return oof


def accuracy(oof: pd.DataFrame, bundle) -> dict[str, Any]:
    """基线 / 模型 / 倍数 —— **同折、同数据段、同一个人群**（规格书 §6.2）。

    ⚠️ 拿的是 **B 组那些折**，不是全部八折：旁边坐的是「本模型（B 组）」，
    而 B 组正是参数没碰过的那一组。拿八折的基线去比 B 组的模型，就是把
    一次调参优势混进基线里，让这个模型显得没那么好（或更好）—— 两个方向都是谎。

    ⚠️ 模型那一行**也从这张长表现算**（更正 3），不原样抄包的 `ab.mae_b`。
    抄的话两行就是两个不同的统计量（一个合起来算、一个按折算再平均）并排比大小，
    而这一节要的恰恰是可比。走同一个 `_row()`、同一张长表，「同折同段」就成了
    结构上的事实而不是约定。包里的 `ab.mae_b` 仍在被用 —— 用作**校验**：
    `test_模型的_mae_与包里的_ab_mae_b_一致` 钉着现算的这个数等于它。

    ⚠️ 只有 MAE 有那条等式。RMSE 平方之后不可按 n 加权平均，合并值与逐折
    均值本来就不是一个数 —— 对照表里的 RMSE 列只用来与基线比，不要与下面的
    逐折表交叉着读。
    """
    b_rows = bundle.metrics[bundle.metrics["group"] == "B"]
    names = sorted(str(f) for f in b_rows["fold"])
    part = oof[oof["fold"].isin(names)]
    truth = part["truth"].to_numpy(float)
    baseline = {**_row(truth, part["baseline"].to_numpy(float)), "label": BASELINE_LABEL}
    model = {**_row(truth, part["pred"].to_numpy(float)), "label": MODEL_LABEL}
    ratio = None
    if baseline["mae"] is not None and model["mae"]:
        ratio = _finite(baseline["mae"] / model["mae"])
    return {"folds": names, "baseline": baseline, "model": model, "ratio": ratio}


def density(oof: pd.DataFrame) -> dict[str, Any]:
    """折外预测 vs 实测的二维直方图 —— 60×60 的计数矩阵。

    **为什么不是散点**（规格书 §7.1 明确记了这一处偏离）：两万七千对点画成
    散点是一团墨，y = x 那条对角线会被糊掉 —— 而那条线是这张图唯一要回答的
    东西（报高了还是报低了）。计数矩阵让每个格子有确定的深浅。

    两个轴**共用同一个范围**：它是对角线图，轴范围不同的话 y = x 就不是 45 度。

    `counts[it][ip]`：实测落在第 it 格、预测落在第 ip 格的点数。
    """
    truth = oof["truth"].to_numpy(float)
    pred = oof["pred"].to_numpy(float)
    ok = np.isfinite(truth) & np.isfinite(pred)
    t, q = truth[ok], pred[ok]
    if t.size == 0:
        return {"bins": BINS, "lo": None, "hi": None, "n": 0, "counts": []}
    lo = float(min(t.min(), q.min()))
    hi = float(max(t.max(), q.max()))
    if hi <= lo:
        # 全部落在一个值上（某一段整段缺值被填成一个数就是这样）：
        # 零宽的 range 会让 `np.histogram2d` 的格子归属无定义。给一个 ±0.5 的方框。
        lo, hi = lo - 0.5, hi + 0.5
    counts, _, _ = np.histogram2d(t, q, bins=BINS, range=[[lo, hi], [lo, hi]])
    return {"bins": BINS, "lo": lo, "hi": hi, "n": int(t.size),
            "counts": counts.astype(int).tolist()}


def residuals(oof: pd.DataFrame) -> list[dict[str, Any]]:
    """三张残差图的分箱。纵轴一律是**折外残差**（正 = 报高了）。

    每个箱三个数：平均残差（主）、箱内样本数、平均残差的标准误。
    少了标准误，任何一根短柱子都会被读成「这里系统地偏高/偏低」——
    柱子的高矮本身没有尺度，标准误才是「这个偏离超过噪声了吗」的判据。

    ⚠️ 后两张的箱数由**这份数据的测点**决定，不由这里写死：z 只有 3 个取值、
    x 只有 7 个。它们不是曲线，是几根柱子（规格书 §7.2）。

    ⚠️ 箱内全是 NaN 时 `mean` 是 None，而**箱子留在表里** ——
    那一箱真实存在，藏起来就是漏报（与页② 不藏最差折同一条房规）。
    """
    panels: list[dict[str, Any]] = []
    for key, label, col, axis_name in RESIDUAL_AXES:
        bins: list[dict[str, Any]] = []
        for at, grp in oof.groupby(col, sort=True):
            r = grp["resid"].to_numpy(float)
            r = r[np.isfinite(r)]
            n = int(r.size)
            bins.append({
                "at": _finite(float(at)),
                "mean": _finite(float(r.mean())) if n else None,
                # ddof=1：样本标准误。n == 1 时算不出来，报 None 而不是 0 ——
                # 0 会被读成「一个点的样本，误差正好是零」。
                "se": _finite(float(r.std(ddof=1) / np.sqrt(n))) if n > 1 else None,
                "n": n,
            })
        panels.append({"key": key, "label": label, "axis": axis_name, "bins": bins})
    return panels


class DiagnosticsCache:
    """按管线身份缓存诊断结果。

    形状与 `deps.PipelineCache` / `deps.DatasetCache` **故意一致**：
    三个缓存的失效规则必须读起来一样，否则「为什么这次没生效」会在三个
    不同的心智模型之间来回甩。
    """

    def __init__(self, *, builder=None, capacity: int = 4) -> None:
        self._builder = builder or compute
        self._capacity = int(capacity)
        self._items: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.n_builds = 0            # 测试用它证明「真的只算了一次」

    @staticmethod
    def key_of(ds: Dataset, groups, bundle, params_sig: str) -> tuple[str, str, str, str]:
        """(数据集签名, 特征组签名, 包的 created_at, 这套参数的签名)。

        **前三格与 `deps.PipelineCache.key_of` 逐位相等；第四格是这里特有的。**

        ⚠️ 第四格为什么在：参数第一次进了诊断那条链（`oof_table` 的 `cfg`）。
        没有它，拖完滑块点「开始训练」会拿回**上一套参数**的图，而图上没有
        任何一个字会说这件事。

        ⚠️ 第三格为什么**不能**换成参数签名：`accuracy()` 读的是
        `bundle.metrics` 里哪几折属于 B 组 —— 那是包的数据，不是参数的函数。
        换掉它，两份 A/B 分组不同、参数相同的包会共用一份图。

        ⚠️ 这里不能写 `deps.PipelineCache.key_of`：`tests/test_routes_use_cache.py`
        规定 `api/**` 从 `deps` 取名字只许白名单里那几个，而 `PipelineCache`
        不在名单上（那条守卫防的正是「绕过 get_dataset 直接抓缓存设施」）。
        两份实现 + 一条守卫，比开一个口子好。
        """
        return (ds.signature, groups_signature(groups),
                getattr(bundle, "created_at", None) or "", params_sig)

    def get(self, ds: Dataset, groups, bundle, params_sig: str,
            cfg=None) -> dict[str, Any]:
        key = self.key_of(ds, groups, bundle, params_sig)
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items[key] = self._items.pop(key)   # 命中即提到队尾
                return hit
            # 构建放在锁里：并发时第二个线程等在这里，醒来就命中。
            # 这一次构建要十几秒，但**别的路由不受影响** —— 它们不碰这把锁。
            out = self._builder(ds, groups, bundle, cfg)
            self._items[key] = out
            while len(self._items) > self._capacity:
                self._items.pop(next(iter(self._items)))
            self.n_builds += 1
            return out


def compute(ds: Dataset, groups, bundle, cfg=None) -> dict[str, Any]:
    """跑一遍全部四块。**没有缓存层的那一半**，测试可以单独调它。"""
    oof = oof_table(ds, bundle, cfg)
    return {
        "n_points": int(len(oof)),
        "n_sensors": int(oof["sensor_id"].nunique()),
        "n_times": int(len(ds.wide)),
        "density": density(oof),
        "accuracy": accuracy(oof, bundle),
        "residual": residuals(oof),
        "note": DIAGNOSTICS_NOTE,
    }


_CACHE = DiagnosticsCache()


def get_or_compute(ds, groups, bundle, params_sig: str, cfg=None) -> dict[str, Any]:
    """出口用这一个。"""
    return _CACHE.get(ds, groups, bundle, params_sig, cfg)


def _reset() -> None:
    """换数据集时**重建**缓存对象，不是 `clear()`。

    `clear()` 会让 `n_builds` 留着上一个数据集的计数，而「换完之后又算了
    几遍」正是那条缓存测试要数的东西。理由与 `deps.reset_cache` 里那句一字不差。
    """
    global _CACHE
    _CACHE = DiagnosticsCache()


#: 在**模块导入时**登记自己（与 `api/live.py` 的实时源同一个手法）：
#: 显式调用要求每个未来的调用点都记得调，而那正是「换数据集忘了清」的成因。
#: 在结构上不可能漏，比「记得调」可靠。
deps.on_dataset_change(_reset)
