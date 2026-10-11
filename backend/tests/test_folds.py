from __future__ import annotations
import pytest
from tfield import config as C
from tfield.data.loader import load_dataset, test_data_path
from tfield.validation.folds import (fold_kind, position_folds, region_folds,
                                     section_folds, sensor_index)

pytestmark = pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


def test_传感器编号是棚主序(ds):
    assert sensor_index(ds, "p1", "x0.15_z0.4") == 0
    assert sensor_index(ds, "p1", "x1.95_z0.4") == 7
    assert sensor_index(ds, "p2", "x0.15_z0.4") == 8
    assert sensor_index(ds, "p3", "x1.95_z0.4") == 23


def test_留一测点共八折每折三个传感器(ds):
    folds = position_folds(ds)
    assert len(folds) == 8
    assert all(len(f.test_sensors) == 3 for f in folds)


def test_留一测点覆盖全部二十四点且不重叠(ds):
    seen = [s for f in position_folds(ds) for s in f.test_sensors]
    assert sorted(seen) == list(range(24))


def test_折自带AB分组标签(ds):
    folds = position_folds(ds)
    assert sum(f.group == "A" for f in folds) == 4
    assert sum(f.group == "B" for f in folds) == 4
    assert all(f.group in ("A", "B") for f in folds)


def test_AB分组与config一致(ds):
    by_name = {f.name: f for f in position_folds(ds)}
    for pos in C.TUNING_POSITIONS:
        assert by_name[f"position:{pos}"].group == "A"
    for pos in C.REPORT_POSITIONS:
        assert by_name[f"position:{pos}"].group == "B"


def test_每折的三个传感器是同一位置的不同棚(ds):
    for f in position_folds(ds):
        positions = [ds.sensor_ids()[s][2] for s in f.test_sensors]
        assert len(set(positions)) == 1
        assert [ds.sensor_ids()[s][1] for s in f.test_sensors] == list(C.SHED_ORDER)


def test_总折外预测数等于二十四乘一千三百零八(ds):
    total = sum(len(f.test_sensors) for f in position_folds(ds)) * C.EXPECTED_ROWS
    assert total == 24 * 1308 == 31392


def test_留一断面共三折每折八点(ds):
    folds = section_folds(ds)
    assert len(folds) == 3
    assert all(len(f.test_sensors) == 8 for f in folds)
    assert sorted(s for f in folds for s in f.test_sensors) == list(range(24))


def test_留一断面每折是一整棚(ds):
    for f in section_folds(ds):
        sheds = {ds.sensor_ids()[s][1] for s in f.test_sensors}
        assert len(sheds) == 1


def test_留区域四折不重叠且覆盖全部(ds):
    folds = region_folds(ds)
    assert len(folds) == 4
    assert sorted(s for f in folds for s in f.test_sensors) == list(range(24))
    assert all(f.test_sensors for f in folds)


def test_折族由名字前缀解析():
    assert fold_kind("position:x1.05_z0.4") == "position"
    assert fold_kind("section:p2") == "section"
    assert fold_kind("region:left") == "region"
