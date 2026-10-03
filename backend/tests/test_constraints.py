from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.data.loader import load_dataset, test_data_path
from tfield.features import build_features
from tfield.field.constraints import (MonotonicConfig, apply_monotonic, light_at,
                                      pava_nondecreasing)
from tfield.field.types import Field
from tfield.pipeline import FieldPipeline, PipelineConfig


def _field(values, mask=None):
    values = np.asarray(values, float)
    nz, nx = values.shape
    mask = np.ones_like(values, bool) if mask is None else np.asarray(mask, bool)
    return Field(values=np.where(mask, values, np.nan),
                 x=np.arange(nx) * 0.1, z=np.arange(nz) * 0.1,
                 mask=mask, outside_measured=np.zeros_like(mask),
                 meta={"test": True})


# ── PAVA 本身 ──

def test_pava把违反单调的段池化():
    out = pava_nondecreasing(np.array([1.0, 3.0, 2.0, 4.0]))
    assert np.allclose(out, [1.0, 2.5, 2.5, 4.0])


def test_pava对已单调的输入是恒等():
    v = np.array([1.0, 2.0, 3.0, 5.0])
    assert np.allclose(pava_nondecreasing(v), v)


def test_pava输出总是非降():
    rng = np.random.default_rng(0)
    v = rng.normal(size=50)
    out = pava_nondecreasing(v)
    assert np.all(np.diff(out) >= -1e-12)


def test_pava保持均值():
    rng = np.random.default_rng(1)
    v = rng.normal(size=30)
    assert pava_nondecreasing(v).mean() == pytest.approx(v.mean())


def test_pava支持权重():
    v = np.array([0.0, 10.0, 2.0])
    out = pava_nondecreasing(v, w=np.array([1.0, 9.0, 1.0]))
    # 违反单调的只有 (10, 2) 这一段 —— 0 ≤ 10 本来就没违例，所以第 0 位**不会被**拉高。
    # 后两个池化为加权均值 (10·9 + 2·1)/10 = 9.2；等权则只有 6.0。权重的作用在这里。
    assert np.allclose(out, [0.0, 9.2, 9.2])
    assert np.all(np.diff(out) >= -1e-12)
    assert not np.allclose(out, pava_nondecreasing(v)), "权重没起作用，等于没传 w"


# ── 门禁与强度 ──

def test_无光照时逐位不变():
    f = _field([[10.0, 10.0], [8.0, 8.0]])          # z 越大反而越冷
    out = apply_monotonic(f, light=0.0)
    assert np.array_equal(out.values, f.values, equal_nan=True)


def test_白天把逆温抹平():
    f = _field([[10.0, 10.0], [8.0, 8.0]])
    out = apply_monotonic(f, light=50000.0)
    assert np.all(np.diff(out.values[:, 0]) >= -1e-12)
    assert out.values[0, 0] == pytest.approx(9.0)


def test_已经单调的白天场不被改动():
    """PAVA 对单调输入是恒等，所以白天本来正常的场不会被这个约束动到。"""
    f = _field([[8.0, 8.0], [10.0, 10.0]])
    out = apply_monotonic(f, light=50000.0)
    assert np.allclose(out.values, f.values, equal_nan=True)


def test_strength为零时不变():
    f = _field([[10.0], [8.0]])
    out = apply_monotonic(f, light=50000.0, cfg=MonotonicConfig(strength=0.0))
    assert np.allclose(out.values, f.values, equal_nan=True)


def test_strength为半时走一半():
    f = _field([[10.0], [8.0]])
    out = apply_monotonic(f, light=50000.0, cfg=MonotonicConfig(strength=0.5))
    assert out.values[0, 0] == pytest.approx(9.5)
    assert out.values[1, 0] == pytest.approx(8.5)


def test_enabled为假时不变():
    f = _field([[10.0], [8.0]])
    out = apply_monotonic(f, light=50000.0, cfg=MonotonicConfig(enabled=False))
    assert np.allclose(out.values, f.values, equal_nan=True)


def test_direction为decreasing时反向投影():
    f = _field([[8.0], [10.0]])
    out = apply_monotonic(f, light=50000.0, cfg=MonotonicConfig(direction="decreasing"))
    assert out.values[0, 0] == pytest.approx(9.0)


def test_掩膜外仍是NaN():
    f = _field([[10.0, 99.0], [8.0, 99.0]], mask=[[True, False], [True, False]])
    out = apply_monotonic(f, light=50000.0)
    assert np.isnan(out.values[:, 1]).all()


def test_不改动输入对象():
    f = _field([[10.0], [8.0]])
    before = f.values.copy()
    apply_monotonic(f, light=50000.0)
    assert np.array_equal(f.values, before, equal_nan=True)


# ── 与真实数据接线 ──

@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_光照取自数据集():
    ds = load_dataset(test_data_path())
    fs = build_features(ds)
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    assert light_at(pipe, 700) == pytest.approx(float(ds.wide[C.BG_LIGHT].iloc[700]))
    assert light_at(pipe, 30) > 0, "第 30 个时刻（11:00 起 +150 min ≈ 13:30）是白天"


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
@pytest.mark.slow
def test_白天真实场投影后竖直非降():
    from tfield.field.build import section_field
    from tfield.field.grid import GridSpec

    ds = load_dataset(test_data_path())
    fs = build_features(ds)
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    g = GridSpec.from_preset("standard")
    f = section_field(pipe, "p2", 30, g, monotonic=MonotonicConfig())   # 30 是白天
    for j in range(f.nx):
        col = f.values[:, j]
        good = np.isfinite(col)
        if good.sum() >= 2:
            assert np.all(np.diff(col[good]) >= -1e-9), f"第 {j} 列在 z 上有下降"


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
@pytest.mark.slow
def test_夜间真实场不被投影():
    from tfield.field.build import section_field
    from tfield.field.grid import GridSpec

    ds = load_dataset(test_data_path())
    fs = build_features(ds)
    pipe = FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)
    g = GridSpec.from_preset("standard")
    assert light_at(pipe, 700) <= 0, "选的时刻不是夜里，换个索引"
    raw = section_field(pipe, "p2", 700, g)
    con = section_field(pipe, "p2", 700, g, monotonic=MonotonicConfig())
    assert np.array_equal(raw.values, con.values, equal_nan=True)
