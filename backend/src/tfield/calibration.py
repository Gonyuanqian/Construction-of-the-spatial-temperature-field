"""标定：找最优参数、把结果封成包、按 (数据集指纹, 特征组) 取回。

三件事都在这里，因为它们的接口咬在一起：

1. **搜索** —— `run_calibration`，位置二分 + 交替优化，A 组选参、B 组只报数。
2. **封包** —— `CalibrationBundle`。参数和指标必须配对出生：指标只在它所测的
   那对（参数，数据，特征组）上成立。
3. **取包** —— `calibrate_or_load`，**前端唯一入口**。有包就秒回，没有就跑一次再存。

参数是**特征组的函数**：换了特征组，旧参数就不再最优。所以包的身份是
`(数据集指纹, 特征组哈希)` 两段，缺一不可 —— 只认数据集指纹的话，
用户换个特征组就会静默用上一组调出来的参数。

`progress` 回调默认 `None`，即完全不产出中间输出 —— 前端的「最优参数」
功能不需要展示搜索过程。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from . import config as C
from .data.types import Dataset
from .features import build_features
from .models.idw import AnisoMetric, IDWCorrector
from .pipeline import FieldPipeline, PipelineConfig
from .validation.folds import position_folds
from .validation.report import evaluate

TOOL_VERSION = "0.1.0"
DEFAULT_ROOT = Path("configs")
SEED = 20261001


class CalibrationAborted(RuntimeError):
    """标定被 should_stop 主动中断。

    中断的语义是「什么都没发生」：磁盘上不留任何文件（不写灵敏度 CSV、
    不写标定包），调用方重新打开界面时看到的状态与中断前一致。
    """


IDW_SPACE: Mapping[str, list] = {
    "power": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
    "lx": [0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0],
    "lz": [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2, 0.3, 0.5],
    "cross_shed": [True, False],
}

TREND_SPACE: Mapping[str, list] = {
    "max_depth": [3, 4, 5, 6],              # 上限压到 6：深树更易在 y 上分裂，见 R2
    "learning_rate": [0.02, 0.05, 0.08, 0.15],
    "n_estimators": [200, 300, 500, 800],
    "min_child_weight": [1, 3, 5, 10],
    "subsample": [0.7, 0.85, 1.0],
    "colsample_bytree": [0.7, 0.85, 1.0],
    "reg_lambda": [0, 1, 5],
    "objective": ["reg:squarederror", "reg:absoluteerror", "reg:pseudohubererror"],
}
_FIXED_TREND = {"random_state": 0, "n_jobs": -1, "tree_method": "hist", "verbosity": 0}
_IDW_KEYS = ("power", "lx", "lz")

# 标定包声明「这些参数是搜出来的」。**必须是搜索真的变过的那些** ——
# 往里塞一个固定值（如 ly，它恒为 1.0）就是在包里谎报调参范围。
# 与搜索空间的一一对应由测试守；注意 metric.* 只能取 AnisoMetric 的字段，
# 而 IDW_SPACE 里的 cross_shed 是个独立开关、不是 metric 的字段。
TUNED_KEYS: tuple[str, ...] = tuple(
    [f"metric.{k}" for k in _IDW_KEYS] + ["cross_shed"]
    + [f"trend.{k}" for k in TREND_SPACE]
)


@dataclass(frozen=True)
class SearchRecord:
    seed: int
    n_trials: int
    space: Mapping[str, Sequence[Any]]
    trials: pd.DataFrame                        # 逐组参数与 A 组评分
    best: Mapping[str, Any]
    plateau: Mapping[str, tuple[Any, Any]]      # 每个维度的可接受区间


@dataclass(frozen=True)
class CalibrationBundle:
    dataset_sig: str
    groups_sig: str                             # 特征组的短哈希，与文件名一致
    created_at: str
    tool_version: str
    feature_groups: tuple[str, ...]
    trend_kind: str
    trend_params: Mapping[str, Any]
    metric: AnisoMetric
    cross_shed: bool
    tuned_keys: tuple[str, ...]
    search: SearchRecord
    folds: tuple[str, ...]
    metrics: pd.DataFrame
    per_point: pd.DataFrame
    ab: Mapping[str, float] | None = None

    # ── 派生 ──
    def config(self) -> PipelineConfig:
        return PipelineConfig(
            feature_groups=tuple(self.feature_groups),
            trend_kind=self.trend_kind,
            trend_params=dict(self.trend_params),
            metric=self.metric,
            cross_shed=self.cross_shed,
        )

    def matches(self, ds: Dataset) -> bool:
        return self.dataset_sig == ds.signature

    # ── 序列化 ──
    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_sig": self.dataset_sig,
            "groups_sig": self.groups_sig,
            "created_at": self.created_at,
            "tool_version": self.tool_version,
            "feature_groups": list(self.feature_groups),
            "trend_kind": self.trend_kind,
            "trend_params": dict(self.trend_params),
            "metric": {"lx": self.metric.lx, "ly": self.metric.ly,
                       "lz": self.metric.lz, "power": self.metric.power},
            "cross_shed": bool(self.cross_shed),
            "tuned_keys": list(self.tuned_keys),
            "search": {
                "seed": self.search.seed,
                "n_trials": self.search.n_trials,
                "space": {k: list(v) for k, v in self.search.space.items()},
                "trials": self.search.trials.to_dict(orient="records"),
                "best": dict(self.search.best),
                "plateau": {k: list(v) for k, v in self.search.plateau.items()},
            },
            "folds": list(self.folds),
            "metrics": self.metrics.to_dict(orient="records"),
            "per_point": self.per_point.to_dict(orient="records"),
            "ab": dict(self.ab) if self.ab is not None else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "CalibrationBundle":
        s = d["search"]
        return cls(
            dataset_sig=d["dataset_sig"],
            # 老包没有这个字段就现算，不因为缺一个诊断字段而拒绝加载
            groups_sig=d.get("groups_sig", groups_signature(d["feature_groups"])),
            created_at=d["created_at"],
            tool_version=d["tool_version"],
            feature_groups=tuple(d["feature_groups"]),
            trend_kind=d["trend_kind"],
            trend_params=dict(d["trend_params"]),
            metric=AnisoMetric(**d["metric"]),
            cross_shed=bool(d["cross_shed"]),
            tuned_keys=tuple(d["tuned_keys"]),
            search=SearchRecord(
                seed=int(s["seed"]),
                n_trials=int(s["n_trials"]),
                space=s["space"],
                trials=pd.DataFrame(s["trials"]),
                best=s["best"],
                plateau={k: tuple(v) for k, v in s["plateau"].items()},
            ),
            folds=tuple(d["folds"]),
            metrics=pd.DataFrame(d["metrics"]),
            per_point=pd.DataFrame(d["per_point"]),
            ab=d.get("ab"),
        )

    @classmethod
    def from_json(cls, s: str) -> "CalibrationBundle":
        return cls.from_dict(json.loads(s))


def groups_signature(groups: Sequence[str]) -> str:
    """特征组的短哈希。用于文件名，也是「参数是特征组的函数」这条约束的落点。"""
    raw = "|".join(str(g) for g in groups).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8]


def bundle_path(ds_sig: str, groups: Sequence[str],
                root: Path | str = DEFAULT_ROOT) -> Path:
    """文件名同时编码数据集指纹与特征组 —— 两者任一变了都算另一份标定。"""
    return Path(root) / f"bundle_{ds_sig}_{groups_signature(groups)}.json"


def save_bundle(b: CalibrationBundle, root: Path | str = DEFAULT_ROOT) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = bundle_path(b.dataset_sig, b.feature_groups, root)
    p.write_text(b.to_json(), encoding="utf-8")
    return p


def load_bundle(path: Path | str) -> CalibrationBundle | None:
    p = Path(path)
    if not p.exists():
        return None
    return CalibrationBundle.from_json(p.read_text(encoding="utf-8"))


def load_for(ds: Dataset, groups: Sequence[str] = C.DEFAULT_FEATURE_GROUPS,
             root: Path | str = DEFAULT_ROOT) -> CalibrationBundle | None:
    """按 (数据集指纹, 特征组) 取标定包。

    **不匹配就返回 None** —— 既不静默回退到别的数据集，也不静默用别的特征组
    调出来的参数。
    """
    b = load_bundle(bundle_path(ds.signature, groups, root))
    if b is None or not b.matches(ds):
        return None
    return b if b.feature_groups == tuple(groups) else None


def new_bundle(ds: Dataset, cfg: PipelineConfig, *, tuned_keys: Sequence[str],
               search: SearchRecord, folds: Sequence[str],
               metrics: pd.DataFrame, per_point: pd.DataFrame,
               ab: Mapping[str, float] | None = None,
               now: datetime | None = None) -> CalibrationBundle:
    return CalibrationBundle(
        dataset_sig=ds.signature,
        groups_sig=groups_signature(cfg.feature_groups),
        created_at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        tool_version=TOOL_VERSION,
        feature_groups=tuple(cfg.feature_groups),
        trend_kind=cfg.trend_kind,
        trend_params=dict(cfg.trend_params),
        metric=cfg.metric,
        cross_shed=cfg.cross_shed,
        tuned_keys=tuple(tuned_keys),
        search=search,
        folds=tuple(folds),
        metrics=metrics,
        per_point=per_point,
        ab=ab,
    )


# ──────────────────────────── 搜索 ────────────────────────────

def cache_folds(ds: Dataset, fs, folds, cfg: PipelineConfig,
                progress: Callable[[str], None] | None = None) -> list:
    """对每个折训练一次趋势并缓存整条管线。

    这是整台标定机器能跑得动的原因：**残差不依赖 IDW 参数**。
    每折的趋势只训练一次，之后每组 IDW 参数只是一次加权求和（`score_idw`）。
    """
    say = progress or (lambda _m: None)
    out = []
    for fold in folds:
        say(f"  训练折 {fold.name}")
        out.append((fold, FieldPipeline(cfg, ds).fit(fs, ds, exclude=fold.test_sensors)))
    return out


def score_idw(cached, metric: AnisoMetric, cross_shed: bool) -> float:
    """用缓存重算被留出传感器的折外误差。不训练，纯加权求和。

    被留出传感器的真残差由 `pipe.residual_matrix()` 给出（它是全部 24 行的
    y − trend，对留出者而言正是折外残差）；修正值由只在源集上 fit 的 IDW 给出。
    """
    coords = cached[0][1].coords
    errs = []
    for fold, pipe in cached:
        si = np.asarray(fold.test_sensors)
        src = pipe.source_sensor_ids()
        resid = pipe.residual_matrix()
        corr = IDWCorrector(metric, cross_shed).fit(coords[src], resid[src]).predict(coords[si])
        errs.append(np.abs(corr - resid[si]).ravel())
    return float(np.concatenate(errs).mean())


def sweep_idw(cached, *, idw_space=None, cross_shed_values=None,
              progress: Callable[[str], None] | None = None,
              should_stop: Callable[[], bool] | None = None) -> pd.DataFrame:
    """扫遍 IDW 空间，返回按 mae 升序的参数曲面。

    阶段 1 与阶段 3 共用这一台机器，区别只在 `cross_shed_values`。
    `idw_space` 不传就是模块常量 `IDW_SPACE`（前端「快速扫」用它换一个小空间，秒级出图）。
    `should_stop` 每扫一组问一次；返回 True 就抛 `CalibrationAborted`。
    """
    space = IDW_SPACE if idw_space is None else idw_space
    cs_values = list(space["cross_shed"] if cross_shed_values is None else cross_shed_values)
    say = progress or (lambda _m: None)
    rows = []
    for power in space["power"]:
        for lx in space["lx"]:
            for lz in space["lz"]:
                for cs in cs_values:
                    if should_stop is not None and should_stop():
                        raise CalibrationAborted("阶段 1 扫描被中断")
                    rows.append({
                        "power": power, "lx": lx, "lz": lz, "cross_shed": cs,
                        "mae": score_idw(cached,
                                         AnisoMetric(lx=lx, ly=1.0, lz=lz, power=power), cs),
                    })
    say(f"  扫过 {len(rows)} 组 IDW 参数")
    return pd.DataFrame(rows).sort_values("mae").reset_index(drop=True)


def plateau_of(trials: pd.DataFrame, keys, rel: float = 0.01) -> dict:
    """评分在最优 +rel 以内的所有组合，给出每个维度的区间。

    这是「参数落在平台上而不是尖峰上」的量化说法 —— 验收时用来解释
    「这些值不是碰巧挑中的」。
    """
    cutoff = trials["mae"].min() * (1.0 + rel)
    ok = trials[trials["mae"] <= cutoff]
    return {k: (float(ok[k].min()), float(ok[k].max())) for k in keys}


def run_calibration(ds: Dataset,
                    groups: Sequence[str] = C.DEFAULT_FEATURE_GROUPS,
                    *, n_trials: int = 40, seed: int = SEED,
                    root: Path | str = DEFAULT_ROOT,
                    progress: Callable[[str], None] | None = None,
                    should_stop: Callable[[], bool] | None = None,
                    idw_space=None, trend_space=None) -> CalibrationBundle:
    """位置二分 + 交替优化，返回标定包（并写出参数曲面 CSV）。

    全程只用 **A 组**的分数选参；B 组直到最后一次 `evaluate` 才被触碰，
    且只用来报数。`progress=None` 时零输出。

    `should_stop` 返回 True 时抛 `CalibrationAborted`。**中断不写任何文件** ——
    灵敏度 CSV 与标定包都只在搜索全部成功之后才落盘，所以半路退出时磁盘是干净的。

    阶段 1（秒级）：冻结趋势（兜底），把 IDW 扫透。
    阶段 2（分钟级）：冻结 IDW，随机搜趋势参数。每次试验重训 4 折。
    阶段 3（秒级）：在新趋势参数下回头再扫一次 IDW，确认最优没移动。
    """
    say = progress or (lambda _m: None)

    def _check(where: str) -> None:
        if should_stop is not None and should_stop():
            raise CalibrationAborted(where)

    idw = IDW_SPACE if idw_space is None else idw_space
    trend = TREND_SPACE if trend_space is None else trend_space
    groups = tuple(groups)
    fs = build_features(ds, groups)
    folds = position_folds(ds)
    a_folds = [f for f in folds if f.group == "A"]
    say(f"数据集指纹 {ds.signature}；特征组 {groups}（{groups_signature(groups)}）")
    say(f"A 组 {len(a_folds)} 折（选参）/ B 组 {len(folds) - len(a_folds)} 折（报数）")

    # ── 阶段 1 ──
    surface = sweep_idw(cache_folds(ds, fs, a_folds, PipelineConfig.fallback(), say),
                        idw_space=idw, progress=say, should_stop=should_stop)
    best1 = surface.iloc[0].to_dict()
    plateau = plateau_of(surface, _IDW_KEYS)
    say(f"阶段 1 最优 MAE {best1['mae']:.4f} @ power={best1['power']} lx={best1['lx']} "
        f"lz={best1['lz']} cross_shed={best1['cross_shed']}")
    say(f"平台（最优 +1% 以内）：{plateau}")
    if best1["lx"] == max(idw["lx"]):
        say("⚠️  lx 落在搜索上界。lx → ∞ 时距离度量退化为只含 (y, z)。"
            "按设计文档 §7.4，这应当成一条**发现**去解释验证，"
            "而不是让搜索悄悄推到顶格 —— 请外扩上界复测。")
    if best1["lz"] == min(idw["lz"]):
        say("⚠️  lz 落在搜索下界，说明还没扫够，请往下扩。")

    # ── 阶段 2：冻结 IDW，随机搜趋势 ──
    rng = np.random.default_rng(seed)
    fixed = AnisoMetric(lx=best1["lx"], ly=1.0, lz=best1["lz"], power=best1["power"])
    cs = bool(best1["cross_shed"])
    rows2 = []
    for i in range(n_trials):
        _check("阶段 2 试验之间被中断")
        tp = {k: v[int(rng.integers(len(v)))] for k, v in trend.items()}
        tp.update(_FIXED_TREND)
        cfg_i = PipelineConfig(feature_groups=groups, trend_params=tp,
                               metric=fixed, cross_shed=cs)
        m = score_idw(cache_folds(ds, fs, a_folds, cfg_i, None), fixed, cs)
        rows2.append({"stage": 2, **tp, "mae": m})
        say(f"  [{i + 1}/{n_trials}] MAE {m:.4f}  {tp['objective']} "
            f"d{tp['max_depth']} lr{tp['learning_rate']} n{tp['n_estimators']}")
    stage2 = pd.DataFrame(rows2).sort_values("mae").reset_index(drop=True)
    best2 = stage2.iloc[0].to_dict()
    say(f"阶段 2 最优 MAE {best2['mae']:.4f} @ {best2['objective']} "
        f"d{best2['max_depth']} lr{best2['learning_rate']} n{best2['n_estimators']}")

    # ── 阶段 3：回头再扫一次 IDW，确认没移动 ──
    final_params = {k: best2[k] for k in trend}
    final_params.update(_FIXED_TREND)
    final_cfg = PipelineConfig(feature_groups=groups, trend_params=final_params,
                               metric=fixed, cross_shed=cs)
    surface3 = sweep_idw(cache_folds(ds, fs, a_folds, final_cfg, None),
                         idw_space=idw, cross_shed_values=[cs],
                         progress=say, should_stop=should_stop)
    best3 = surface3.iloc[0].to_dict()
    say(f"阶段 3 最优 MAE {best3['mae']:.4f} @ power={best3['power']} "
        f"lx={best3['lx']} lz={best3['lz']}")
    if (best3["power"], best3["lx"], best3["lz"]) != (best1["power"], best1["lx"], best1["lz"]):
        say("⚠️  IDW 最优随趋势参数移动了 —— 交替优化未收敛，以阶段 3 为准并再跑一轮。")
        fixed = AnisoMetric(lx=best3["lx"], ly=1.0, lz=best3["lz"], power=best3["power"])
        final_cfg = PipelineConfig(feature_groups=groups, trend_params=final_params,
                                   metric=fixed, cross_shed=cs)

    # ── 冻结 + 全折验证（A 组选参、B 组只报数）──
    # 必须把 groups 传下去：evaluate 内部自己 build_features，若不传就会用默认
    # 特征组建特征，而 final_cfg 声明的是 groups —— 搜索在 A 组特征上选参、
    # 指标却在另一组特征上量，B 组的「未参与选参」就名不副实了。
    res = evaluate(lambda: FieldPipeline(final_cfg, ds), ds, folds,
                   groups=groups, tag="calibration")
    assert res.ab is not None, "position 折必须产出 A/B 两组，否则位置二分没生效"
    say(f"\nA 组（参与选参）MAE {res.ab.mae_a:.4f}")
    say(f"B 组（未参与选参）MAE {res.ab.mae_b:.4f}")
    say(f"→ 调参乐观偏差 {res.ab.gap:+.4f} °C")

    search = SearchRecord(
        seed=seed, n_trials=n_trials,
        space={**{f"idw.{k}": list(v) for k, v in idw.items()},
               **{f"trend.{k}": list(v) for k, v in trend.items()}},
        trials=pd.concat([surface.assign(stage=1), stage2, surface3.assign(stage=3)],
                         ignore_index=True),
        best={"metric": {"lx": fixed.lx, "ly": fixed.ly, "lz": fixed.lz, "power": fixed.power},
              "trend": final_params, "cross_shed": cs},
        plateau=plateau,
    )

    # 写点刻意放在**搜索全部成功之后**：任何一个 should_stop 命中点退出时，
    # 磁盘上都不会留下半成品（旧写法在阶段 1 一结束就写 CSV，阶段 2 中断会留残迹）。
    out = Path(root)
    out.mkdir(parents=True, exist_ok=True)
    csv = out / f"sensitivity_{ds.signature}_{groups_signature(groups)}.csv"
    _check("写出结果前被中断")
    surface.assign(stage=1).to_csv(csv, index=False, encoding="utf-8-sig")
    say(f"参数曲面已写入 {csv}")

    return new_bundle(ds, final_cfg,
                      tuned_keys=TUNED_KEYS,
                      search=search, folds=[f.name for f in folds],
                      metrics=res.metrics, per_point=res.per_point,
                      ab={"mae_a": res.ab.mae_a, "mae_b": res.ab.mae_b, "gap": res.ab.gap})


def calibrate_or_load(ds: Dataset,
                      groups: Sequence[str] = C.DEFAULT_FEATURE_GROUPS,
                      *, n_trials: int = 40, root: Path | str = DEFAULT_ROOT,
                      force: bool = False, seed: int = SEED,
                      progress: Callable[[str], None] | None = None,
                      should_stop: Callable[[], bool] | None = None,
                      idw_space=None, trend_space=None) -> CalibrationBundle:
    """**前端唯一入口**：给我这份数据 + 这组特征的最优参数。

    有标定包就秒回；没有才跑一次（分钟级）再存。`progress=None`（默认）
    表示完全不展示中间过程 —— 前端只需要一个转圈。

    重复调用是安全的：搜索是确定性的（固定种子、残差缓存、不做早停），
    同一个 `(数据集指纹, 特征组)` 点多少次都得到同一个包，
    用户手上没有可以用来反复试探的信号。

    **例外**：带自定义 `idw_space` / `trend_space` 时一律绕过缓存。缓存键只有
    `(数据集指纹, 特征组哈希)`，而搜索范围是入参 —— 双键没变、搜的范围变了，
    命中的旧包就不再代表这次要搜的东西（规格书 §三 用 `created_at` 覆盖的正是这一类）。
    """
    if not force and idw_space is None and trend_space is None:
        cached = load_for(ds, groups, root)
        if cached is not None:
            return cached
    bundle = run_calibration(ds, groups, n_trials=n_trials, seed=seed,
                             root=root, progress=progress, should_stop=should_stop,
                             idw_space=idw_space, trend_space=trend_space)
    save_bundle(bundle, root)
    return bundle
