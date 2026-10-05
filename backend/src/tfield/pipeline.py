"""把 ①~④ 装配成一个可训练、可查询的对象。

R1（被留出的传感器必须从 IDW 源集排除）在这条链上只有一个落点：fit(exclude=...)。
训练、标定、验证、部署全走它 —— 不可能出现「验证时排除了、标定里忘了」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from . import config as C
from .data.types import Dataset
from .features import FeatureSet, add_feature_groups
from .models.idw import AnisoMetric, IDWCorrector
from .models.trend import TrendModel, make_trend


def _fallback_metric() -> AnisoMetric:
    return AnisoMetric(lx=C.FALLBACK_LX, ly=C.FALLBACK_LY,
                       lz=C.FALLBACK_LZ, power=C.FALLBACK_POWER)


@dataclass(frozen=True)
class PipelineConfig:
    feature_groups: tuple[str, ...] = C.DEFAULT_FEATURE_GROUPS
    trend_kind: str = C.FALLBACK_TREND_KIND
    trend_params: Mapping[str, Any] = field(default_factory=lambda: dict(C.FALLBACK_TREND_PARAMS))
    metric: AnisoMetric = field(default_factory=_fallback_metric)
    cross_shed: bool = C.FALLBACK_CROSS_SHED

    @classmethod
    def fallback(cls) -> "PipelineConfig":
        """未标定时的兜底配置。界面上必须标注「未标定」。"""
        return cls()


class FieldPipeline:
    def __init__(self, cfg: PipelineConfig, ds: Dataset) -> None:
        self.cfg = cfg
        self.ds = ds
        self.fitted = False
        self._fs: FeatureSet | None = None
        self._trend: TrendModel | None = None
        self._idw: IDWCorrector | None = None
        self._trend_all: np.ndarray | None = None      # 与 fs 行对齐的趋势预测
        self._train_mask: np.ndarray | None = None
        self._feature_names: tuple[str, ...] = ()
        # 逐时刻的气象与时间，供查询期拼特征矩阵
        w = ds.wide
        self._bg_temp = w[C.BG_TEMP].to_numpy(float)
        self._bg_rh = w[C.BG_RH].to_numpy(float)
        self._bg_light = w[C.BG_LIGHT].to_numpy(float)
        ts = pd.to_datetime(w[C.COL_TIMESTAMP])
        self._hour = ts.dt.hour.to_numpy(int)
        self._frac_day = (ts.dt.hour + ts.dt.minute / 60.0).to_numpy(float)
        # 实时帧：接在时间轴尾部的那一段。空的时候下面每条路径都与旧实现逐位相同。
        self._live_ts: list[pd.Timestamp] = []
        self._live_resid: np.ndarray | None = None      # (24, n_live)

    @classmethod
    def from_bundle(cls, bundle, ds: Dataset) -> "FieldPipeline":
        """bundle 只需提供 config() -> PipelineConfig（鸭子类型，避免反向依赖）。"""
        return cls(bundle.config(), ds)

    # ── 训练 ──
    def fit(self, fs: FeatureSet, ds: Dataset, *, exclude: Sequence[int] = ()) -> "FieldPipeline":
        self.ds = ds
        self._fs = fs
        exclude = tuple(int(s) for s in exclude)
        mask = ~np.isin(fs.sensor_id, exclude)
        self._train_mask = mask

        X = fs.X.loc[mask]
        self._feature_names = tuple(X.columns)
        self._trend = make_trend(self.cfg.trend_kind, self.cfg.trend_params).fit(X, fs.y[mask])
        self._trend_all = self._trend.predict(fs.X)

        # 用内部版本而不是 self.residual_matrix()：后者带 _require_fitted() 门，
        # 而此刻 fitted 还是 False（趋势已就位、IDW 尚未装配）。在 fit 中途调用
        # 公开访问器会自己把自己挡住。
        src_ids = np.unique(fs.sensor_id[mask])
        self._idw = IDWCorrector(self.cfg.metric, self.cfg.cross_shed).fit(
            fs.coords[src_ids], self._resid_matrix()[src_ids])
        self.fitted = True
        return self

    def _require_fitted(self) -> None:
        if not self.fitted:
            raise RuntimeError("必须先调用 fit() 才能预测")

    @property
    def train_rows(self) -> int:
        return 0 if self._train_mask is None else int(self._train_mask.sum())

    # ── 时间轴（含接进来的实时帧）──
    @property
    def n_live(self) -> int:
        """已经接进来的实时帧数。"""
        return 0 if self._live_resid is None else int(self._live_resid.shape[1])

    @property
    def n_times(self) -> int:
        """时间轴长度。

        **实时帧会使它大于 `len(self.ds.wide)`。** 所以凡是要问「这个时刻在不在
        时间轴上」，都该走这里 —— 直接读 `ds.wide.shape[0]` 在实时帧接进来之后
        就是个越界判定，而且它不会报错，只会拒掉合法的帧。
        """
        return int(len(self._bg_temp))

    def timestamps(self) -> list[pd.Timestamp]:
        """整条时间轴的时间戳（数据集的 + 已接进来的实时帧）。"""
        out = list(pd.to_datetime(self.ds.wide[C.COL_TIMESTAMP]))
        out.extend(self._live_ts)
        return out

    def time_at(self, t_index: int) -> pd.Timestamp:
        """第 t_index 帧的时间戳。越界抛 `IndexError` —— **不返回 None**：
        这一条是给「时间轴只追加、不插队」那个判定用的，静默的 None 会让它失效。
        """
        n = self.n_times
        if not 0 <= t_index < n:
            raise IndexError(f"t_index 越界：{t_index}（时间轴共 {n} 帧）")
        n_ds = len(self.ds.wide)
        if t_index < n_ds:
            return pd.Timestamp(self.ds.wide[C.COL_TIMESTAMP].iloc[t_index])
        return self._live_ts[t_index - n_ds]

    @property
    def coords(self) -> np.ndarray:
        assert self._fs is not None
        return self._fs.coords

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self._feature_names

    def source_sensor_ids(self) -> np.ndarray:
        """本次训练用作 IDW 源的传感器编号（已排序）。"""
        self._require_fitted()
        assert self._fs is not None and self._train_mask is not None
        return np.unique(self._fs.sensor_id[self._train_mask])

    def source_y_levels(self) -> np.ndarray:
        """本次训练的源传感器覆盖到的 y 值（升序去重）—— R2 的合法查询集。

        **不是** `C.SHED_Y`：合法集取决于本次 fit 见过什么。留一断面时整个棚被
        排除，它的 y 就从合法集里消失，此后在该 y 上查询趋势正是 R2 禁止的事。
        """
        return np.unique(self.coords[self.source_sensor_ids(), 1])

    def _resid_matrix(self) -> np.ndarray:
        """→ (24, n_t)，第 s 行 = 传感器 s 的 y − trend。无 fitted 前置条件。"""
        assert self._fs is not None and self._trend_all is not None
        out = np.empty((C.EXPECTED_N_SENSORS, len(self.ds.wide)))
        resid = self._fs.y - self._trend_all
        for s in range(C.EXPECTED_N_SENSORS):
            out[s] = resid[self._fs.sensor_id == s]
        return out

    def residual_matrix(self) -> np.ndarray:
        """→ (24, n_t)，第 s 行 = 传感器 s 的 y − trend。

        **包含被留出的传感器** —— 对被留出者而言这正是折外真残差，
        是评估时的基准，不是 IDW 的源。
        """
        self._require_fitted()
        return self._resid_matrix()

    def trend_only_prediction(self, sensors: Sequence[int]) -> np.ndarray:
        """→ (n_sensors, n_t)，不加 IDW 修正。"""
        self._require_fitted()
        assert self._fs is not None and self._trend_all is not None
        return np.stack([self._trend_all[self._fs.sensor_id == s] for s in sensors])

    # ── 任意空间点查询 ──
    def _design_matrix(self, coords: np.ndarray, t_index: np.ndarray) -> pd.DataFrame:
        """按 features.add_feature_groups 的同一套列定义拼出 (n_pts × n_t) 行特征。

        行序为「时刻优先」：第 k 行对应 (t = t_index[k // n_pts], 点 = k % n_pts)，
        预测结果 reshape(n_t, n_pts).T 即得 (n_pts, n_t)。
        """
        coords = np.atleast_2d(np.asarray(coords, dtype=float))
        t_index = np.asarray(t_index, dtype=int)
        n_p, n_t = len(coords), len(t_index)
        long = pd.DataFrame({
            "x": np.tile(coords[:, 0], n_t),
            "y": np.tile(coords[:, 1], n_t),
            "z": np.tile(coords[:, 2], n_t),
            "bg_temp": np.repeat(self._bg_temp[t_index], n_p),
            "bg_rh": np.repeat(self._bg_rh[t_index], n_p),
            "bg_light": np.repeat(self._bg_light[t_index], n_p),
            "hour": np.repeat(self._hour[t_index], n_p),
            "frac_day": np.repeat(self._frac_day[t_index], n_p),
        })
        X = add_feature_groups(long, self.cfg.feature_groups)
        return X[list(self._feature_names)]

    def trend_at_coords(self, coords: np.ndarray, t_index: np.ndarray) -> np.ndarray:
        """任意空间点 × 指定时刻的趋势预测。→ (n_pts, n_t)。

        ⚠️ 调用方有责任只用 y ∈ `self.source_y_levels()`（R2）。本方法不检查 ——
        合法的 y 集取决于本次 fit，是 fit 的属性而不是常数。两个出口都自己把关：
        `predict_points`（任意点预测）按 1/dy 混合，field/build.py 的 `field_at`
        （网格场）按同样的规则混合。**不要在这个方法之上新开一个不过关的出口。**
        """
        self._require_fitted()
        assert self._trend is not None
        coords = np.atleast_2d(np.asarray(coords, dtype=float))
        t_index = np.asarray(t_index, dtype=int)
        X = self._design_matrix(coords, t_index)
        pred = self._trend.predict(X)
        return pred.reshape(len(t_index), len(coords)).T

    def residual_at_coords(self, coords: np.ndarray, t_index: np.ndarray) -> np.ndarray:
        self._require_fitted()
        assert self._idw is not None
        coords = np.atleast_2d(np.asarray(coords, dtype=float))
        t_index = np.asarray(t_index, dtype=int)
        return self._idw.predict(coords)[:, t_index]

    def feature_importance(self) -> pd.Series | None:
        """趋势模型的增益重要性（索引 = 特征名）。

        未 fit、或底层趋势模型没有这个能力时返回 `None`（**不抛**）——
        界面据此显示「本模型不提供特征重要性」，而不是崩掉。
        """
        if self._trend is None or not hasattr(self._trend, "feature_importance"):
            return None
        return self._trend.feature_importance(self._feature_names)

    def predict_points(self, coords: np.ndarray, t_index: np.ndarray) -> np.ndarray:
        """任意空间点 × 指定时刻的温度预测。→ (n_pts, n_t)。

        **R2 合规**：只在本次训练真的见过 y 的断面上查趋势。查询点的 y 不在合法集里
        时，改在夹住它的两个合法断面上各算一次，再按 1/dy 混合 —— 与 `field_at` 同一
        套语义（含出界钳制）。留一断面折里 y=9 没有任何训练样本，此前这里会直接查
        趋势（实测把留一断面 MAE 从 0.2654 抬到 0.4777）。
        """
        self._require_fitted()
        coords = np.atleast_2d(np.asarray(coords, dtype=float))
        t_index = np.asarray(t_index, dtype=int)
        legal = self.source_y_levels()
        ys = coords[:, 1]
        out = np.empty((len(coords), len(t_index)), dtype=float)
        for y in np.unique(ys):
            sel = ys == y
            out[sel] = self._predict_on_levels(coords[sel], t_index, float(y), legal)
        return out

    def _predict_on_levels(self, coords: np.ndarray, t_index: np.ndarray,
                           y: float, legal: np.ndarray) -> np.ndarray:
        """把查询点落到合法 y 集上：命中 → 直接；夹住 → 1/dy 混合；出界 → 最近断面。"""
        if np.any(np.isclose(legal, y)):
            return (self.trend_at_coords(coords, t_index)
                    + self.residual_at_coords(coords, t_index))
        below, above = legal[legal < y], legal[legal > y]
        if below.size == 0 or above.size == 0:
            edge = float(legal[0] if below.size == 0 else legal[-1])
            pts = coords.copy()
            pts[:, 1] = edge
            return self._predict_on_levels(pts, t_index, edge, legal)
        y_lo, y_hi = float(below[-1]), float(above[0])
        lo_pts, hi_pts = coords.copy(), coords.copy()
        lo_pts[:, 1], hi_pts[:, 1] = y_lo, y_hi
        w_lo, w_hi = 1.0 / (y - y_lo), 1.0 / (y_hi - y)
        return (w_lo * self._predict_on_levels(lo_pts, t_index, y_lo, legal)
                + w_hi * self._predict_on_levels(hi_pts, t_index, y_hi, legal)) / (w_lo + w_hi)
