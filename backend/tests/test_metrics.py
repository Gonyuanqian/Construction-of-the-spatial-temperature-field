from __future__ import annotations
import numpy as np
import pytest
from tfield.validation.metrics import mae, metrics_row, r2, rmse


def test_完全命中():
    y = np.array([1.0, 2.0, 3.0])
    assert mae(y, y) == 0.0
    assert rmse(y, y) == 0.0
    assert r2(y, y) == 1.0


def test_偏一度的常数误差():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert mae(y, y + 1.0) == pytest.approx(1.0)
    assert rmse(y, y + 1.0) == pytest.approx(1.0)


def test_r2可以很负():
    """R² 没有下界 —— 用作守卫时要小心，主指标是 MAE。"""
    y = np.array([1.0, 2.0, 3.0, 4.0])
    assert r2(y, np.full_like(y, 100.0)) < -10


def test_指标行含三个指标():
    y = np.arange(10.0)
    row = metrics_row(y, y + 0.5)
    assert set(row) == {"mae", "rmse", "r2"}
    assert row["mae"] == pytest.approx(0.5)


def test_接受列表与一维数组():
    assert mae([1.0, 2.0], [2.0, 3.0]) == pytest.approx(1.0)
