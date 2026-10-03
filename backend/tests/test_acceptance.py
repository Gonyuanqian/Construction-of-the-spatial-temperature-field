from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.calibration import load_for
from tfield.data.loader import load_dataset, test_data_path
from tfield.features import build_features
from tfield.field.arch import arch_area, arch_mask
from tfield.field.build import field_at
from tfield.field.grid import GridSpec
from tfield.pipeline import FieldPipeline, PipelineConfig
from tfield.validation.metrics import mae, r2

pytestmark = pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


def test_数据事实(ds):
    assert ds.wide.shape == (1308, 52)
    assert ds.fix.fixed_indices == (60, 348, 636, 924, 1212)
    assert ds.fix.spacing_seconds == 300.0 and ds.fix.gaps == ()


def test_质量标记分布(ds):
    v = ds.quality.drop(columns=[C.COL_TIMESTAMP]).to_numpy().ravel().astype(int)
    u = np.bincount(v, minlength=10)
    assert (u[0], u[1], u[2], u[9]) == (454, 66106, 148, 0)


def test_几何():
    assert arch_area(C.SHED_X_MIN, C.SHED_X_MAX) == pytest.approx(2.2845, abs=2e-3)


def test_掩膜有效域占比():
    g = GridSpec.from_preset("export")
    X, Z = g.mesh()
    frac = arch_mask(X, Z).mean()
    assert 0.80 < frac < 0.88


def test_基准_R2(ds):
    """不作任何建模、直接拿背景温度当棚温即达 R² = 0.8896 ——
    这就是为什么 R² > 0.85 不能当门槛（96.6% 的方差是昼夜循环）。"""
    y = np.concatenate([ds.wide[f"{s}_{p}_temp_C"].to_numpy()
                        for s in C.SHED_ORDER for p in C.SENSOR_LAYOUT])
    bg = np.tile(ds.wide[C.BG_TEMP].to_numpy(), 24)
    assert r2(y, bg) == pytest.approx(0.8896, abs=2e-3)
    assert mae(y, bg) == pytest.approx(1.295, abs=5e-3)


def test_端到端三维场可生成(ds):
    fs = build_features(ds)
    b = load_for(ds, C.DEFAULT_FEATURE_GROUPS)
    cfg = b.config() if b is not None else PipelineConfig.fallback()
    pipe = FieldPipeline(cfg, ds).fit(fs, ds)
    g = GridSpec.from_preset("interactive")
    f = field_at(pipe, y=6.0, t_index=700, grid=g)
    assert np.isfinite(f.values[f.mask]).all()
    assert np.isnan(f.values[~f.mask]).all()
    assert f.outside_measured.any()


@pytest.mark.slow
def test_有标定包时精度达标(ds):
    """有标定包就断言精度；没有则跳过并提示先跑标定。"""
    b = load_for(ds, C.DEFAULT_FEATURE_GROUPS)
    if b is None:
        pytest.skip("尚未标定：先运行 python scripts/calibrate.py")
    pos = b.metrics[b.metrics["fold_kind"] == "position"]
    # 用 mean 而不是 min：8 个点位里只要有一个好点，`.min()` 就恒成立，
    # 其余七个全烂掉也照样通过 —— 那不是验收，是同义反复。
    assert pos["mae"].mean() <= 0.25, f"留一测点 MAE 未达 0.25：{pos['mae'].tolist()}"
    assert b.ab is not None and abs(b.ab["gap"]) < 0.10, "A/B 乐观偏差过大，选参有问题"


@pytest.mark.slow
def test_前端契约_标定包能直接喂给训练(ds):
    """前端只需要两件事：拿到最优参数，然后训练。这条测试把那条缝钉死。

    前端的实际调用是 `calibrate_or_load(ds, groups)`；这里刻意用 `load_for`
    读已有包，因为 `calibrate_or_load` 未命中时会真的去标定（几分钟），
    不该出现在测试里。**两者的返回值是同一个类型**，所以缝是一样的。
    """
    b = load_for(ds, C.DEFAULT_FEATURE_GROUPS)
    if b is None:
        pytest.skip("尚未标定：先运行 python scripts/calibrate.py")

    cfg = b.config()
    assert isinstance(cfg, PipelineConfig)
    assert cfg.feature_groups == C.DEFAULT_FEATURE_GROUPS

    fs = build_features(ds, cfg.feature_groups)
    pipe = FieldPipeline(cfg, ds).fit(fs, ds)
    assert pipe.fitted
    assert pipe.train_rows == 24 * C.EXPECTED_ROWS


def test_同一份数据两组特征不会互相顶替(ds):
    """「参数是特征组的函数」这条约束的端到端版本。

    只认数据集指纹的话，用户换个特征组就会静默拿到上一组的参数 ——
    那些参数对新的特征组不再是最优的，而且没有任何提示。
    """
    other = ("coord", "zbasis")
    got = load_for(ds, other)
    assert got is None or got.feature_groups == other
