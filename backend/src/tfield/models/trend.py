"""趋势模型：学 T 与 (空间坐标, 时间, 背景气象, 交互项) 的关系。

用 Protocol 而不是基类，是为了标定阶段能换实现（XGBoost / HistGB / 以后别的），
③ 以上的代码一行都不用改。
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

import numpy as np
import pandas as pd

# 任何含目标信息或测点局部信息的列名，一律不得进入特征矩阵。
# `rh_pct` / `rh` 是**测点**湿度（与被预言的温度同址），归为泄漏；
# `bg_rh` 是棚外气象站的背景湿度，与 `bg_temp` 同源、每个时刻都有，**不是**泄漏列。
_LEAKY = frozenset({"temp", "temp_C", "rh", "rh_pct", "y_true", "target"})


@runtime_checkable
class TrendModel(Protocol):
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "TrendModel": ...
    def predict(self, X: pd.DataFrame) -> np.ndarray: ...


def leaky_columns() -> frozenset[str]:
    return _LEAKY


def _guard(X: pd.DataFrame) -> None:
    bad = sorted(set(map(str, X.columns)) & _LEAKY)
    if bad:
        raise ValueError(f"特征里出现泄漏列：{bad}。目标相关列不得进入 X。")


class XGBTrend:
    """XGBoost 趋势模型。

    刻意不暴露 early_stopping：早停会按验证集自动定树数，破坏可复现性，
    也让标定搜的 n_estimators 失去意义。
    """

    def __init__(self, **params: Any) -> None:
        from xgboost import XGBRegressor

        self.params = dict(params)
        self._model = XGBRegressor(**self.params)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "XGBTrend":
        _guard(X)
        self._model.fit(X, np.asarray(y, dtype=float))
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        _guard(X)
        return np.asarray(self._model.predict(X), dtype=float)

    def feature_importance(self, feature_names) -> pd.Series:
        """XGBoost 增益（gain）重要性，和为 1。

        口径就是 sklearn 包装器的默认 `importance_type="gain"`，**不是**置换重要性：
        零成本、现成；代价是对相关特征会偏心 —— 界面必须照实标注口径。
        """
        if not hasattr(self._model, "feature_importances_"):
            raise RuntimeError("底层模型还没 fit")
        return pd.Series(self._model.feature_importances_,
                         index=list(feature_names), name="gain")


_KINDS = {"xgboost": XGBTrend}


def make_trend(kind: str, params: Mapping[str, Any]) -> TrendModel:
    if kind not in _KINDS:
        raise KeyError(f"未知的趋势模型 {kind!r}；可选 {sorted(_KINDS)}")
    return _KINDS[kind](**dict(params))
