from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.data.loader import load_dataset, test_data_path
from tfield.features import build_features
from tfield.pipeline import FieldPipeline, PipelineConfig
from tfield.validation.folds import position_folds

pytestmark = pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
SLOW = pytest.mark.slow


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


@pytest.fixture(scope="module")
def fs(ds):
    return build_features(ds)


def test_兜底配置避开旧坏角():
    m = PipelineConfig.fallback().metric
    assert not (m.power == 1.0 and m.lx == 1.0 and m.lz == 0.12)
    assert PipelineConfig.fallback().cross_shed is True


def test_兜底配置每次返回独立对象():
    a, b = PipelineConfig.fallback(), PipelineConfig.fallback()
    assert a.trend_params is not b.trend_params, "可变默认值不能被共享"


def test_未fit时predict报错(ds):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds)
    with pytest.raises(RuntimeError, match="fit"):
        pipe.predict_points(np.zeros((1, 3)), np.array([0]))


def test_from_bundle是鸭子类型(ds):
    class FakeBundle:
        def config(self):
            return PipelineConfig.fallback()
    pipe = FieldPipeline.from_bundle(FakeBundle(), ds)
    assert isinstance(pipe, FieldPipeline)


def test_exclude把传感器从训练集里去掉(ds, fs):
    """R1：留出的传感器必须不参与训练，否则趋势模型已经「见过」它。"""
    full = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    held = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=(0, 8, 16))
    assert full.train_rows - held.train_rows == 3 * C.EXPECTED_ROWS


def test_exclude的传感器不是IDW源(ds, fs):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=(3, 11, 19))
    assert set(pipe.source_sensor_ids()).isdisjoint({3, 11, 19})
    assert len(pipe.source_sensor_ids()) == 21


def test_不exclude时全部24点都是源(ds, fs):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    assert list(pipe.source_sensor_ids()) == list(range(24))


def test_残差矩阵形状与行对齐(ds, fs):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=(0, 8, 16))
    r = pipe.residual_matrix()
    assert r.shape == (24, C.EXPECTED_ROWS)
    assert np.isfinite(r).all(), "被留出的行也要有真残差（它是评估的基准，不是源）"


def test_趋势与残差相加等于整体预测(ds, fs):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    ti = np.array([0, 500])
    c = fs.coords[[5]]
    a = pipe.trend_at_coords(c, ti) + pipe.residual_at_coords(c, ti)
    b = pipe.predict_points(c, ti)
    assert np.allclose(a, b)


def test_特征名与训练时一致(ds, fs):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    assert tuple(pipe.feature_names) == tuple(fs.X.columns)


@SLOW
def test_留一测点的纯趋势误差落在合理带内(ds, fs):
    """换用 XGBoost 后绝对值与旧 HistGB 基线不同，且标定会改参数 —— 用宽容带。"""
    errs = []
    for fold in position_folds(ds):
        pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=fold.test_sensors)
        pred = pipe.trend_only_prediction(fold.test_sensors)
        truth = np.stack([fs.y[fs.sensor_id == s] for s in fold.test_sensors])
        errs.append(np.abs(pred - truth).ravel())
    m = np.concatenate(errs).mean()
    assert 0.15 < m < 0.30, f"留一测点纯趋势 MAE = {m:.4f}，超出合理带"


def _spy_trend_y(pipe, monkeypatch) -> list[float]:
    """记录趋势模型每次被查询到的 y 值。"""
    seen: list[float] = []
    orig = pipe.trend_at_coords

    def spy(coords, t_index):
        seen.extend(np.atleast_2d(coords)[:, 1].tolist())
        return orig(coords, t_index)

    monkeypatch.setattr(pipe, "trend_at_coords", spy)
    return seen


def test_源集合覆盖到的y就是合法查询集(ds, fs):
    """R2 的合法 y 集**不是** C.SHED_Y，而是本次训练真的见过的 y。"""
    full = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    assert list(full.source_y_levels()) == [3.0, 9.0, 15.0]
    held = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=tuple(range(8, 16)))
    assert list(held.source_y_levels()) == [3.0, 15.0], "整个 p2 棚被留出，y=9 就该从合法集消失"


def test_留出整棚后不在那个y上查询趋势(ds, fs, monkeypatch):
    """留一断面折里 y=9 没有任何训练样本 —— 在那里查趋势正是 R2 禁止的事。"""
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=tuple(range(8, 16)))
    seen = _spy_trend_y(pipe, monkeypatch)
    pipe.predict_points(fs.coords[8:16], np.array([700]))
    assert seen, "趋势模型一次都没被调用，这个测试没起作用"
    assert 9.0 not in set(np.round(seen, 6)), f"在 y=9 上查了趋势：{sorted(set(seen))}"
    assert set(np.round(seen, 6)) <= {3.0, 15.0}


def test_留出整棚后预测等于两个邻棚的一维混合(ds, fs):
    """合规估计量：先在各断面自己的 y 上预测，再按 1/dy 混合。

    规格书 §基线表「留一断面 MAE 0.2654 = |T(y=9) − [T(y=3)+T(y=15)]/2|」
    描述的就是这个量。混合权重在 y=9 处各占一半。
    """
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=tuple(range(8, 16)))
    ti = np.array([700])
    mid = pipe.predict_points(fs.coords[8:16], ti)
    a = fs.coords[8:16].copy()
    a[:, 1] = 3.0
    b = fs.coords[8:16].copy()
    b[:, 1] = 15.0
    assert np.allclose(mid, 0.5 * (pipe.predict_points(a, ti) + pipe.predict_points(b, ti)))


def test_中间y也不查趋势(ds, fs, monkeypatch):
    """部署口径下 y=6 同样是「没见过的 y」（训练只有 3/9/15）。"""
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    seen = _spy_trend_y(pipe, monkeypatch)
    c = fs.coords[[0]].copy()
    c[0, 1] = 6.0
    pipe.predict_points(c, np.array([700]))
    assert set(np.round(seen, 6)) <= {3.0, 9.0}, f"查询到的 y：{sorted(set(seen))}"


def test_y超出源集合时钳制到最近断面(ds, fs, monkeypatch):
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    seen = _spy_trend_y(pipe, monkeypatch)
    c = fs.coords[[0]].copy()
    c[0, 1] = 99.0
    pipe.predict_points(c, np.array([700]))
    assert set(np.round(seen, 6)) == {15.0}, f"查询到的 y：{sorted(set(seen))}"


def test_合法y上的预测路径不变(ds, fs):
    """回归守卫：源集合覆盖到的 y 上，predict_points 仍是趋势 + 残差，逐位不变。

    这条在修复前后都通过 —— 它的价值是证明修复没有动到部署路径。
    """
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    ti = np.array([0, 500])
    c = fs.coords[[5, 13, 21]]
    assert np.allclose(pipe.predict_points(c, ti),
                       pipe.trend_at_coords(c, ti) + pipe.residual_at_coords(c, ti))
    assert set(np.round(c[:, 1], 6)) <= set(np.round(pipe.source_y_levels(), 6))


@SLOW
def test_IDW修正让留一测点误差显著变小(ds, fs):
    """方向性断言：修正是有用的，且幅度可观。"""
    cfg = PipelineConfig.fallback()
    ti = np.arange(C.EXPECTED_ROWS)
    base, fixed = [], []
    for fold in position_folds(ds):
        pipe = FieldPipeline(cfg, ds).fit(fs, ds, exclude=fold.test_sensors)
        truth = np.stack([fs.y[fs.sensor_id == s] for s in fold.test_sensors])
        coords = fs.coords[list(fold.test_sensors)]
        base.append(np.abs(pipe.trend_only_prediction(fold.test_sensors) - truth).ravel())
        fixed.append(np.abs(pipe.predict_points(coords, ti) - truth).ravel())
    mb, mf = np.concatenate(base).mean(), np.concatenate(fixed).mean()
    assert mf < mb * 0.85, f"IDW 只把 {mb:.4f} 降到 {mf:.4f}，改善不足"


@pytest.fixture(scope="module")
def pipe_unfitted(ds):
    return FieldPipeline(PipelineConfig.fallback(), ds)


@pytest.fixture(scope="module")
def pipe_fitted(ds, fs):
    return FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)


def test_未fit时特征重要性返回None(pipe_unfitted):
    assert pipe_unfitted.feature_importance() is None


def test_已fit时特征重要性索引等于特征名(pipe_fitted):
    s = pipe_fitted.feature_importance()
    assert s is not None and tuple(s.index) == pipe_fitted.feature_names
