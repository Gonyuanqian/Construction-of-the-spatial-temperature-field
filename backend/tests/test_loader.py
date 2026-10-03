from __future__ import annotations
import pandas as pd
import pytest
from tfield import config as C
from tfield.data.loader import (check_sensor_columns, dataset_signature,
                                load_dataset, test_data_path)

pytestmark = pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


def test_宽表形状与无缺失(ds):
    assert ds.wide.shape == (C.EXPECTED_ROWS, C.EXPECTED_COLS)
    assert ds.wide.isna().sum().sum() == 0, "源数据无缺失值（R5：标记 + 保留，不做剔除）"


def test_时间轴修复五处(ds):
    assert ds.fix.fixed_indices == C.EXPECTED_FIXED_ROWS
    assert ds.fix.monotonic_after and not ds.fix.monotonic_before
    assert ds.fix.spacing_seconds == 300.0
    assert ds.fix.gaps == ()
    assert len(ds.wide) == 1308
    assert ds.wide.index.is_monotonic_increasing and ds.wide.index.is_unique


def test_质量标记分布(ds):
    flags = ds.quality.drop(columns=[C.COL_TIMESTAMP]).to_numpy().ravel()
    u = pd.Series(flags).value_counts()
    assert int(u.get(0, 0)) == 454
    assert int(u.get(1, 0)) == 66106
    assert int(u.get(2, 0)) == 148
    assert int(u.get(9, 0)) == 0
    assert int(u.sum()) == 1308 * 51


def test_测点布局与测点字典一致(ds):
    """config 里硬编码的坐标必须与数据自带的「测点字典」对得上，否则是漂移。"""
    from_dict = ds.dict_layout()
    assert set(from_dict) == set(C.SENSOR_LAYOUT)
    for name, pos in from_dict.items():
        cfg_x, cfg_z, cfg_layer = C.SENSOR_LAYOUT[name]
        assert pos.x == pytest.approx(cfg_x, abs=1e-9), name
        assert pos.z == pytest.approx(cfg_z, abs=0.03), name   # z 允许 3 cm 约定差
        assert pos.layer == cfg_layer, name


def test_传感器编号是棚主序(ds):
    ids = ds.sensor_ids()
    assert len(ids) == 24
    assert ids[0] == (0, "p1", "x0.15_z0.4")
    assert ids[7] == (7, "p1", "x1.95_z0.4")
    assert ids[8] == (8, "p2", "x0.15_z0.4")
    assert ids[23] == (23, "p3", "x1.95_z0.4")


def test_列缺失时明确报错():
    """Review Focus #3：传感器整列缺失必须明确报错，不能静默变 NaN。"""
    df = pd.DataFrame({C.COL_TIMESTAMP: pd.date_range("2026-07-23", periods=3, freq="5min")})
    with pytest.raises(KeyError, match="缺失列"):
        check_sensor_columns(df)


def test_列齐全时不报错(ds):
    check_sensor_columns(ds.wide)


def test_签名跟着文件走(tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"x")
    s1 = dataset_signature(f)
    f.write_bytes(b"xy")            # 大小变了
    assert dataset_signature(f) != s1


def test_签名对同一文件稳定(tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"x")
    assert dataset_signature(f) == dataset_signature(f)


def test_签名是十六位十六进制(tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"x")
    s = dataset_signature(f)
    assert len(s) == 16 and int(s, 16) >= 0
