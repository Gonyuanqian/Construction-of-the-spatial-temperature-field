"""评估指标。主指标是 MAE —— R² 在本数据上没有区分度。

基准：不作任何建模、直接拿背景温度当棚温即达 R² = 0.8896；逐测点一元线性回归达 0.9825。
96.6% 的方差是昼夜循环，所以 R² > 0.85 这类门槛挡不住任何东西。
"""
from __future__ import annotations

import numpy as np


def mae(y_true, y_pred) -> float:
    yt, yp = np.asarray(y_true, float), np.asarray(y_pred, float)
    return float(np.abs(yt - yp).mean())


def rmse(y_true, y_pred) -> float:
    yt, yp = np.asarray(y_true, float), np.asarray(y_pred, float)
    return float(np.sqrt(((yt - yp) ** 2).mean()))


def r2(y_true, y_pred) -> float:
    yt, yp = np.asarray(y_true, float), np.asarray(y_pred, float)
    ss_res = float(((yt - yp) ** 2).sum())
    ss_tot = float(((yt - yt.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def metrics_row(y_true, y_pred) -> dict[str, float]:
    return {"mae": mae(y_true, y_pred), "rmse": rmse(y_true, y_pred), "r2": r2(y_true, y_pred)}
