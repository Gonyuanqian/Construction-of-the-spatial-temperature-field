from __future__ import annotations
import numpy as np
import pytest
from tfield import config as C
from tfield.data.loader import load_dataset, test_data_path
from tfield.features import (FEATURE_GROUPS, add_feature_groups, build_features,
                             to_long)

pytestmark = pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


@pytest.fixture(scope="module")
def fs(ds):
    return build_features(ds)


def test_长表行数与列(fs):
    assert len(fs.X) == 24 * 1308 == 31392
    assert fs.y.shape == (31392,)
    assert fs.coords.shape == (24, 3)
    assert fs.sensor_id.shape == (31392,)
    assert fs.t_index.shape == (31392,)


def test_传感器编号覆盖全部二十四点各一千三百零八次(fs):
    uniq, cnt = np.unique(fs.sensor_id, return_counts=True)
    assert list(uniq) == list(range(24))
    assert set(cnt.tolist()) == {1308}


def test_坐标与布局一致(fs):
    for si in range(24):
        shed_i, pos_k = divmod(si, 8)
        pos = list(C.SENSOR_LAYOUT)[pos_k]
        x, z, _ = C.SENSOR_LAYOUT[pos]
        assert fs.coords[si, 0] == pytest.approx(x)
        assert fs.coords[si, 1] == pytest.approx(C.SHED_Y[C.SHED_ORDER[shed_i]])
        assert fs.coords[si, 2] == pytest.approx(z)


def test_目标值与宽表对得上(ds, fs):
    """R5 的另一面：加载与特征化都不能剔除任何行。"""
    sel = fs.sensor_id == 0        # p1 + 第一个位置
    assert np.allclose(fs.y[sel], ds.wide["p1_x0.15_z0.4_temp_C"].to_numpy())


def test_不含测点湿度特征(fs):
    """测点湿度已整体移除：目标点的湿度同样是未知量，拿它当特征等于假设那里有传感器。"""
    assert not [c for c in fs.X.columns if "rh" in c.lower() and not c.startswith("bg_")]


def test_不含滞后特征(fs):
    assert not [c for c in fs.X.columns if "lag" in c.lower()]


def test_特征组逐组累加列数单调增(ds):
    cols = [len(build_features(ds, FEATURE_GROUPS[: i + 1]).X.columns)
            for i in range(len(FEATURE_GROUPS))]
    assert cols == sorted(cols) and len(set(cols)) == len(cols)


def test_交互项列存在(ds):
    """交互项是这一版新增的：留整层 z=0.7 时，旧口径实测带交互项 0.550 对比
    不带 1.056。这里只断言列定义存在；效果由 Task 8 的端到端测试体现。
    """
    fs = build_features(ds)
    assert "bg_temp_x_z" in fs.X.columns
    assert "bg_light_x_z" in fs.X.columns
    assert "bg_temp_x_light" in fs.X.columns


def test_add_feature_groups是公开且可复用的():
    """Task 8 的查询期特征矩阵必须走同一个函数，否则训练/查询特征定义会漂移。"""
    import inspect
    assert not inspect.getsource(add_feature_groups).startswith("def _")


def test_长表含气象与时间列(ds):
    long = to_long(ds)
    assert {"sensor_id", "t_index", "x", "y", "z", "layer", "temp",
            "bg_temp", "bg_rh", "bg_light", "hour", "frac_day"} <= set(long.columns)
    assert len(long) == 31392
