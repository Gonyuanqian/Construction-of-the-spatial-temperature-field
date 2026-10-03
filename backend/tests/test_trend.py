from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from tfield.models.trend import TrendModel, XGBTrend, make_trend


@pytest.fixture
def toy():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
    y = 3.0 * X["a"].to_numpy() - 1.5 * X["b"].to_numpy() + 10.0
    return X, y


def test_协议可被结构化匹配(toy):
    X, y = toy
    m = XGBTrend(n_estimators=30, max_depth=3)
    assert isinstance(m, TrendModel)
    assert m.fit(X, y) is m


def test_能学会线性关系(toy):
    X, y = toy
    pred = XGBTrend(n_estimators=200, max_depth=4, random_state=0).fit(X, y).predict(X)
    assert np.abs(pred - y).mean() < 0.2


def test_可复现(toy):
    X, y = toy
    a = XGBTrend(n_estimators=50, random_state=0).fit(X, y).predict(X)
    b = XGBTrend(n_estimators=50, random_state=0).fit(X, y).predict(X)
    assert np.array_equal(a, b), "固定 random_state 后必须逐位可复现"


def test_预测形状是一维(toy):
    X, y = toy
    assert XGBTrend(n_estimators=10).fit(X, y).predict(X).shape == (len(X),)


def test_工厂按名字造模型():
    assert isinstance(make_trend("xgboost", {"n_estimators": 10}), XGBTrend)
    with pytest.raises(KeyError, match="未知的趋势模型"):
        make_trend("nope", {})


def test_工厂拒绝泄漏列(toy):
    X, y = toy
    X = X.assign(temp=y)        # 目标列混进来了
    with pytest.raises(ValueError, match="泄漏"):
        make_trend("xgboost", {}).fit(X, y)


def test_泄漏列清单覆盖目标与湿度():
    from tfield.models.trend import leaky_columns
    assert {"temp", "rh_pct"} <= set(leaky_columns())


def test_不传early_stopping也不报错():
    """新版 XGBoost 移除了该构造参数；默认不做早停正是我们要的可复现性。"""
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]})
    y = np.array([1.0, 2.0, 3.0, 4.0])
    XGBTrend(n_estimators=5, max_depth=2, random_state=0).fit(X, y)


def test_特征重要性读的是gain且与显式gain同序():
    """不写死数值，只锁口径：与 get_booster().get_score(importance_type="gain") 同序。"""
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=200), "b": rng.normal(size=200)})
    y = 3.0 * X["a"].to_numpy() + 0.1 * rng.normal(size=200)
    t = XGBTrend(objective="reg:squarederror", n_estimators=20, max_depth=2).fit(X, y)
    s = t.feature_importance(list(X.columns))
    assert list(s.index) == ["a", "b"]
    assert s.name == "gain" and abs(float(s.sum()) - 1.0) < 1e-9
    assert s["a"] > s["b"]
    # XGBoost 3.x 传 DataFrame 时，booster 的 score 字典用**列名**做键（不是 f0/f1）
    raw = t._model.get_booster().get_score(importance_type="gain")
    assert set(raw) == {"a", "b"}
    assert raw["a"] / raw["b"] == pytest.approx(s["a"] / s["b"], rel=1e-6)
