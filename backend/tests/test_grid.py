from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.field.grid import GRID_PRESETS, GridSpec


def test_档位由粗到细():
    d = [GRID_PRESETS[k] for k in ("interactive", "standard", "export")]
    assert d == sorted(d, reverse=True)


def test_未知档位报错():
    with pytest.raises(KeyError, match="未知网格档位"):
        GridSpec.from_preset("nope")


def test_网格覆盖棚体且步长精确():
    g = GridSpec.from_preset("export")
    assert g.dx == 0.02
    assert g.x()[0] == 0.0 and g.x()[-1] == pytest.approx(C.SHED_X_MAX)
    assert g.z()[0] == 0.0 and g.z()[-1] <= C.SHED_Z_MAX + 1e-9
    assert g.z()[-1] == pytest.approx(1.30, abs=1e-9), "arange 到 z_max 以下最后一个整步"


def test_测点坐标恰好落在格点上():
    """测点 z = 0.4 / 0.7 / 1.1 都是 0.01 的整数倍 ——
    这是网格用间距 arange 而不用 linspace 到拱顶的原因（后者会把它们夹在格点之间，
    导致「测点处复现实测」的断言失效）。"""
    g = GridSpec.from_spacing(0.01)
    for x, z, _ in C.SENSOR_LAYOUT.values():
        assert np.min(np.abs(g.x() - x)) < 1e-9, x
        assert np.min(np.abs(g.z() - z)) < 1e-9, z


def test_mesh形状一致():
    g = GridSpec.from_preset("interactive")
    X, Z = g.mesh()
    assert X.shape == Z.shape == g.shape
    assert X.shape == (g.nz, g.nx)


def test_nx与nz是派生属性():
    g = GridSpec.from_preset("standard")
    assert g.nx == len(g.x()) and g.nz == len(g.z())
