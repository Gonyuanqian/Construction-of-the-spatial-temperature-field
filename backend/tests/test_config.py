from __future__ import annotations
import math
from tfield import config as C


def test_拱形几何常数():
    assert C.ARCH_R == 1.0761
    assert C.ARCH_XC == 1.0517
    assert C.ARCH_K == 0.2256
    # 拱顶 = 圆心 z + R
    assert math.isclose(C.ARCH_K + C.ARCH_R, C.SHED_Z_MAX, abs_tol=1e-9)
    assert C.SHED_Z_MAX == 1.3017


def test_测点布局有八项且坐标在棚内():
    assert len(C.SENSOR_LAYOUT) == 8
    for name, (x, z, layer) in C.SENSOR_LAYOUT.items():
        assert C.SHED_X_MIN <= x <= C.SHED_X_MAX, name
        assert 0.0 <= z <= C.SHED_Z_MAX, name
        assert layer in ("z0.4", "z0.7", "ztop"), name


def test_位置二分互斥且覆盖全部八点():
    a, b = set(C.TUNING_POSITIONS), set(C.REPORT_POSITIONS)
    assert a & b == set(), "A/B 两组不能重叠"
    assert a | b == set(C.SENSOR_LAYOUT), "A/B 合起来必须覆盖全部测点"
    assert len(a) == len(b) == 4


def test_位置二分按层分层():
    """每一组都要覆盖到 z0.4 / z0.7 / ztop 三层，否则两组的难度不可比。"""
    layers = lambda ps: {C.SENSOR_LAYOUT[p][2] for p in ps}
    assert layers(C.TUNING_POSITIONS) == {"z0.4", "z0.7", "ztop"}
    assert layers(C.REPORT_POSITIONS) == {"z0.4", "z0.7", "ztop"}


def test_棚位坐标():
    assert C.SHED_ORDER == ("p1", "p2", "p3")
    assert C.SHED_Y == {"p1": 3.0, "p2": 9.0, "p3": 15.0}


def test_测点列名拼装():
    t, rh = C.sensor_columns("p1", "x0.15_z0.4")
    assert t == "p1_x0.15_z0.4_temp_C"
    assert rh == "p1_x0.15_z0.4_rh_pct"


def test_最高测点高度即无测量带下界():
    top = max(z for _, z, _ in C.SENSOR_LAYOUT.values())
    assert top == C.MAX_MEASURED_Z == 1.10
    assert C.MAX_MEASURED_Z < C.SHED_Z_MAX, "拱顶下确实有一带没有传感器"


def test_兜底参数不是旧的那个坏角():
    """旧口径 (p=1, lx=1.0, lz=0.12) 实测是整片扫描区最差的一角，兜底值不得沿用它。"""
    assert not (C.FALLBACK_POWER == 1.0 and C.FALLBACK_LX == 1.0 and C.FALLBACK_LZ == 0.12)
