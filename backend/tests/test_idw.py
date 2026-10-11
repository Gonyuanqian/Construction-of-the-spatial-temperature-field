from __future__ import annotations
import numpy as np
import pytest
from tfield.models.idw import AnisoMetric, IDWCorrector


def test_各向异性距离按尺度归一():
    m = AnisoMetric(lx=1.0, ly=1.0, lz=0.5, power=2.0)
    org = np.array([[0.0, 0.0, 0.0]])
    # dz = 0.5 在 lz = 0.5 下与 dx = 1.0 等价：各自的「归一化分量」都是 1.0
    assert m.distances(np.array([[0.0, 0.0, 0.5]]), org)[0, 0] == pytest.approx(1.0)
    assert m.distances(np.array([[1.0, 0.0, 0.0]]), org)[0, 0] == pytest.approx(1.0)
    # 两个分量同时为 1.0 时，欧氏合成是 sqrt(1² + 1²) = √2（不是 1.0）
    d = m.distances(np.array([[1.0, 0.0, 0.5]]), org)
    assert d[0, 0] == pytest.approx(np.sqrt(2.0))


def test_在源点处精确复现():
    """IDW 是精确插值器 —— 这正是 R1 存在的根本原因。"""
    coords = np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0], [0.0, 0, 1]])
    resid = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
    pred = IDWCorrector(AnisoMetric()).fit(coords, resid).predict(coords)
    assert np.allclose(pred, resid)


def test_等距源点给出等权平均():
    """权重归一化的可观测后果：两个等距源点、残差 0 与 10，中点必得 5。"""
    src = np.array([[0.0, 0, 0], [1.0, 0, 0]])
    resid = np.array([[0.0], [10.0]])
    tgt = np.array([[0.5, 0, 0]])
    assert IDWCorrector(AnisoMetric(power=2.0)).fit(src, resid).predict(tgt)[0, 0] == pytest.approx(5.0)


def test_幂次越大越靠近最近邻():
    src = np.array([[0.0, 0, 0], [1.0, 0, 0]])
    resid = np.array([[10.0], [0.0]])
    tgt = np.array([[0.1, 0, 0]])
    p1 = IDWCorrector(AnisoMetric(power=1.0)).fit(src, resid).predict(tgt)[0, 0]
    p4 = IDWCorrector(AnisoMetric(power=4.0)).fit(src, resid).predict(tgt)[0, 0]
    assert p4 > p1, "幂次越大越偏向最近的那个源点"


def test_predict输出形状():
    src = np.array([[0.0, 0, 0], [1.0, 0, 0]])
    resid = np.zeros((2, 1308))
    pred = IDWCorrector(AnisoMetric()).fit(src, resid).predict(np.array([[0.5, 0, 0]]))
    assert pred.shape == (1, 1308)


def test_重合点不产生inf或nan():
    coords = np.array([[0.0, 0, 0], [1.0, 0, 0]])
    resid = np.array([[1.0], [2.0]])
    pred = IDWCorrector(AnisoMetric()).fit(coords, resid).predict(coords)
    assert np.isfinite(pred).all()


def test_fit只接受源点残差():
    """R1 的类型体现：fit 收的就是源集，行数必须与 coords 对齐。"""
    with pytest.raises(ValueError, match="源点"):
        IDWCorrector(AnisoMetric()).fit(np.zeros((3, 3)), np.zeros((2, 5)))


def test_坐标形状不对时报错():
    with pytest.raises(ValueError, match=r"\(n, 3\)"):
        IDWCorrector(AnisoMetric()).fit(np.zeros((3, 2)), np.zeros((3, 5)))


def test_未fit就predict报错():
    with pytest.raises(RuntimeError, match="fit"):
        IDWCorrector(AnisoMetric()).predict(np.zeros((1, 3)))


def test_不跨棚时只用一个棚的源点():
    # 棚 1 (y=0) 两个源点残差 10；棚 2 (y=10) 两个源点残差 0
    src = np.array([[0.0, 0.0, 0], [1.0, 0.0, 0], [0.0, 10.0, 0], [1.0, 10.0, 0]])
    resid = np.array([[10.0], [10.0], [0.0], [0.0]])
    tgt = np.array([[0.5, 0.0, 0]])
    cross = IDWCorrector(AnisoMetric(), cross_shed=True).fit(src, resid).predict(tgt)[0, 0]
    same = IDWCorrector(AnisoMetric(), cross_shed=False).fit(src, resid).predict(tgt)[0, 0]
    assert same == pytest.approx(10.0, abs=1e-6)    # 只用 y 最近的那一棚
    # 跨棚把 y=10 那一棚的 0 也拉进来，但 ly = 1 m 让 10 m 外的权重大约只有同棚的
    # 0.25%：结果严格低于 10，却远高于两棚的算术平均 5。四个源点**不是**平权的 ——
    # 距离决定权重。这正是「邻近棚信息可用、但权重很小」的数值体现。
    assert 5.0 < cross < same
