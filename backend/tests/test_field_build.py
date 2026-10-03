from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.data.loader import load_dataset, test_data_path
from tfield.features import build_features
from tfield.field.build import (blend_fields, bracketing_sheds, field_at,
                                section_field)
from tfield.field.grid import GridSpec
from tfield.field.types import Field
from tfield.pipeline import FieldPipeline, PipelineConfig

pytestmark = [pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根"),
              pytest.mark.slow]

T = 700


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


@pytest.fixture(scope="module")
def pipe(ds):
    """部署口径：不排除任何测点。"""
    fs = build_features(ds)
    return FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds)


def test_夹住y的两个棚():
    assert bracketing_sheds(3.0) == ("p1", "p2")
    assert bracketing_sheds(6.0) == ("p1", "p2")
    assert bracketing_sheds(9.0) == ("p2", "p3")
    assert bracketing_sheds(15.0) == ("p2", "p3")
    assert bracketing_sheds(0.0) is None
    assert bracketing_sheds(18.0) is None


def test_断面场形状与掩膜(pipe):
    g = GridSpec.from_preset("standard")
    f = section_field(pipe, "p2", T, g)
    assert isinstance(f, Field)
    assert f.values.shape == g.shape
    assert np.isnan(f.values[~f.mask]).all(), "掩膜外必须是 NaN（Review Focus #2）"
    assert np.isfinite(f.values[f.mask]).all()
    assert f.meta["shed"] == "p2" and f.meta["y"] == 9.0


def test_断面场在测点处复现实测(pipe, ds):
    """测点处 重建 vs 实测 应在 0.03 ~ 0.06 —— 比无测量带小一个量级。"""
    g = GridSpec.from_spacing(0.01)
    f = section_field(pipe, "p2", T, g)
    errs = []
    for pos, (x, z, _) in C.SENSOR_LAYOUT.items():
        col = int(np.argmin(np.abs(f.x - x)))
        row = int(np.argmin(np.abs(f.z - z)))
        truth = float(ds.wide[f"p2_{pos}_temp_C"].iloc[T])
        errs.append(abs(float(f.values[row, col]) - truth))
    assert np.mean(errs) < 0.10, f"测点处重建 MAE = {np.mean(errs):.4f}"


def test_混合在两端退化为端点(pipe):
    g = GridSpec.from_preset("standard")
    a, b = section_field(pipe, "p1", T, g), section_field(pipe, "p2", T, g)
    ya, yb = C.SHED_Y["p1"], C.SHED_Y["p2"]
    assert np.allclose(blend_fields(a, b, y=ya, ya=ya, yb=yb).values, a.values, equal_nan=True)
    assert np.allclose(blend_fields(a, b, y=yb, ya=ya, yb=yb).values, b.values, equal_nan=True)


def test_混合在中点是两端平均(pipe):
    g = GridSpec.from_preset("standard")
    a, b = section_field(pipe, "p1", T, g), section_field(pipe, "p2", T, g)
    ya, yb = C.SHED_Y["p1"], C.SHED_Y["p2"]
    m = blend_fields(a, b, y=0.5 * (ya + yb), ya=ya, yb=yb)
    assert np.allclose(m.values, 0.5 * (a.values + b.values), equal_nan=True)


def test_混合权重的两两分配之和为一(pipe):
    g = GridSpec.from_preset("interactive")
    a, b = section_field(pipe, "p1", T, g), section_field(pipe, "p2", T, g)
    ya, yb = C.SHED_Y["p1"], C.SHED_Y["p2"]
    m = blend_fields(a, b, y=4.0, ya=ya, yb=yb)
    assert sum(m.meta["weights"]) == pytest.approx(1.0)


def test_掩膜不一致时拒绝混合(pipe):
    a = section_field(pipe, "p1", T, GridSpec.from_preset("standard"))
    b = section_field(pipe, "p2", T, GridSpec.from_preset("interactive"))
    with pytest.raises(ValueError, match="掩膜"):
        blend_fields(a, b, y=6.0, ya=3.0, yb=9.0)


def test_R2_绝不在中间y上查询趋势模型(pipe, monkeypatch):
    """R2：y=6 处树会输出 2.44 °C 的阶梯断崖，field_at(6.0) 必须只查 y=3 与 y=9。"""
    g = GridSpec.from_preset("interactive")
    seen: list[float] = []
    orig = pipe.trend_at_coords

    def spy(coords, t_index):
        seen.extend(np.atleast_2d(coords)[:, 1].tolist())
        return orig(coords, t_index)

    monkeypatch.setattr(pipe, "trend_at_coords", spy)
    field_at(pipe, y=6.0, t_index=T, grid=g)
    assert seen, "趋势模型一次都没被调用，这个测试没起作用"
    assert set(np.round(seen, 6)) == {3.0, 9.0}, f"查询到的 y 值：{sorted(set(seen))}"


def test_R2_端部也只查最近的那个断面(pipe, monkeypatch):
    g = GridSpec.from_preset("interactive")
    seen: list[float] = []
    orig = pipe.trend_at_coords

    def spy(coords, t_index):
        seen.extend(np.atleast_2d(coords)[:, 1].tolist())
        return orig(coords, t_index)

    monkeypatch.setattr(pipe, "trend_at_coords", spy)
    field_at(pipe, y=17.0, t_index=T, grid=g)
    assert set(np.round(seen, 6)) == {15.0}


def test_任意y都能出场且有限(pipe):
    g = GridSpec.from_preset("interactive")
    for y in (0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0):
        f = field_at(pipe, y=y, t_index=T, grid=g)
        assert f.meta["y"] == y
        assert np.isfinite(f.values[f.mask]).all()


def test_两端之外按最近断面钳制(pipe):
    g = GridSpec.from_preset("interactive")
    assert np.allclose(field_at(pipe, y=0.0, t_index=T, grid=g).values,
                       section_field(pipe, "p1", T, g).values, equal_nan=True)
    assert np.allclose(field_at(pipe, y=18.0, t_index=T, grid=g).values,
                       section_field(pipe, "p3", T, g).values, equal_nan=True)


def test_无测量带标记一路传到出口(pipe):
    g = GridSpec.from_preset("standard")
    f = field_at(pipe, y=6.0, t_index=T, grid=g)
    assert f.outside_measured.any()
    assert not f.outside_measured[~f.mask].any(), "掩膜外不算无测量带，它是掩膜外"


# ── 留一断面（整棚被排除）时的 R2 合规性 ────────────────────────────────────
# 合法的 y 集是**本次 fit 的属性**，不是 C.SHED_Y 这个常数。整个 p2 棚被留出时
# y=9 就不在合法集里了，此时 field_at(9.0) 若还短路到 section_field(p2)，
# 就是在没有训练样本的 y 上查趋势 —— 正是 R2 禁止的那次查询。

P2_IDS = tuple(range(8, 16))          # to_long: sensor_id = shed_i*8 + pos_k


@pytest.fixture(scope="module")
def held_pipe(ds):
    """留出整个 p2 棚的管线（该折训练集里只剩 y = 3 / 15）。"""
    fs = build_features(ds)
    return FieldPipeline(PipelineConfig.fallback(), ds).fit(fs, ds, exclude=P2_IDS)


def test_留出整棚后field_at不在那个y上查趋势(held_pipe, monkeypatch):
    g = GridSpec.from_preset("standard")
    seen: list[float] = []
    orig = held_pipe.trend_at_coords

    def spy(coords, t_index):
        seen.extend(np.atleast_2d(coords)[:, 1].tolist())
        return orig(coords, t_index)

    monkeypatch.setattr(held_pipe, "trend_at_coords", spy)
    field_at(held_pipe, y=9.0, t_index=T, grid=g)
    assert seen, "趋势模型一次都没被调用，这个测试没起作用"
    assert set(np.round(seen, 6)) == {3.0, 15.0}, f"查询到的 y 值：{sorted(set(seen))}"


def test_留出整棚后field_at等于两个邻断面的一维混合(held_pipe):
    """合规估计量就是规格书 §基线表那个数的构造：两个邻断面按 1/dy 混合。"""
    g = GridSpec.from_preset("standard")
    got = field_at(held_pipe, y=9.0, t_index=T, grid=g)
    want = blend_fields(section_field(held_pipe, "p1", T, g),
                        section_field(held_pipe, "p3", T, g),
                        y=9.0, ya=3.0, yb=15.0)
    assert np.allclose(got.values, want.values, equal_nan=True)


def test_留出整棚后端点仍钳到最近的可用断面(held_pipe):
    """合法集是 {3, 15}，因此 y=0 钳到 p1、y=18 钳到 p3 —— 不会去碰 y=9。"""
    g = GridSpec.from_preset("standard")
    assert np.allclose(field_at(held_pipe, y=0.0, t_index=T, grid=g).values,
                       section_field(held_pipe, "p1", T, g).values, equal_nan=True)
    assert np.allclose(field_at(held_pipe, y=18.0, t_index=T, grid=g).values,
                       section_field(held_pipe, "p3", T, g).values, equal_nan=True)
