from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.field.arch import arch_area, arch_height, arch_mask
from tfield.field.grid import GridSpec, outside_measured_mask


def test_拱顶与端部():
    assert arch_height(np.array([C.ARCH_XC]))[0] == pytest.approx(C.SHED_Z_MAX, abs=1e-9)
    assert C.ARCH_XC - C.ARCH_R < C.SHED_X_MIN
    assert arch_height(np.array([C.SHED_X_MIN]))[0] == pytest.approx(
        np.sqrt(C.ARCH_R ** 2 - (C.SHED_X_MIN - C.ARCH_XC) ** 2) + C.ARCH_K, abs=1e-9)


def test_截面面积():
    """拱形面积 2.2845 m²，比外接矩形（2.1 × 1.3017 = 2.7336）少 16.4%。"""
    a = arch_area(C.SHED_X_MIN, C.SHED_X_MAX)
    assert a == pytest.approx(2.2845, abs=2e-3), f"面积 = {a}"
    rect = C.SHED_X_MAX * C.SHED_Z_MAX
    assert (rect - a) / rect == pytest.approx(0.164, abs=0.005)


def test_拱脚在零点四五米():
    """拱脚 z ≈ 0.4535，此处以下全长 18 m 没有侧向围护 ——
    这解释了 z0.4 测点读数与背景相关 0.998。"""
    springing = arch_height(np.array([C.SHED_X_MIN]))[0]
    assert 0.44 < springing < 0.47, f"拱脚高度 = {springing}"


def test_掩膜与定义完全一致():
    """Review Focus #2：掩膜内必须满足 z ≤ z(x)，掩膜外必须不满足。"""
    g = GridSpec.from_preset("export")
    X, Z = g.mesh()
    m = arch_mask(X, Z)
    h = arch_height(g.x())[None, :]
    assert np.array_equal(m, Z <= h + 1e-12)


def test_掩膜外全部为假():
    X = np.array([[1.05]])
    Z = np.array([[C.SHED_Z_MAX + 0.001]])
    assert not arch_mask(X, Z)[0, 0]


def test_掩膜占比约百分之八十四():
    """旧实现在 2 cm 档给出 5775 个有效格点（占比 0.846）。本实现的格点约定
    （arange 到 x_max 与 z_max）给出一个相近但不相同的计数。

    这里断言的是**占比**，不是那个数 —— 5775 依赖旧实现的端点取法，
    不要为了让计数等于它去反推网格约定（那是对着数字调代码）。"""
    g = GridSpec.from_preset("export")
    X, Z = g.mesh()
    frac = arch_mask(X, Z).mean()
    assert 0.80 < frac < 0.88, f"有效占比 = {frac:.4f}"


def test_无测量带在最高测点之上():
    """Review Focus #5：拱顶下那一带没有传感器，必须能被程序识别。"""
    g = GridSpec.from_preset("standard")
    X, Z = g.mesh()
    m = outside_measured_mask(X, Z)
    assert m.any()
    assert not m[Z <= C.MAX_MEASURED_Z].any()
    assert m[Z > C.MAX_MEASURED_Z + 1e-9].all()


def test_无测量带确实落在拱内():
    """拱顶 z = 1.3017，所以 z ∈ (1.10, 1.3017] 全在拱内 —— 不是空集。

    standard 档 dx = 0.05，1.10 m 以上只剩 1.15 / 1.20 / 1.25 / 1.30 四个 z 层，
    所以「拱内 ∩ 无测量带」的格点数上限只有 4 × nx。实测 57 个 —— 门限取 50。
    （原稿写 > 100 是按更细的网格估的，本档达不到；数字是量出来的，不是估出来的。）
    """
    g = GridSpec.from_preset("standard")
    X, Z = g.mesh()
    inside = arch_mask(X, Z) & outside_measured_mask(X, Z)
    assert inside.sum() > 50
