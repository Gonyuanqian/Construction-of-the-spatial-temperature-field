from __future__ import annotations
import pytest
from tfield.data.loader import load_dataset, test_data_path
from tfield.pipeline import FieldPipeline, PipelineConfig
from tfield.validation.folds import position_folds, section_folds
from tfield.validation.report import ABResult, EvalResult, evaluate, region_of

pytestmark = [pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根"),
              pytest.mark.slow]


@pytest.fixture(scope="module")
def ds():
    return load_dataset(test_data_path())


def _factory(ds):
    return lambda: FieldPipeline(PipelineConfig.fallback(), ds)


def test_区域标签由折族决定():
    """R4：证据强度按区域分列，标签必须来自折族而不是拍脑袋。"""
    assert region_of("position:x1.05_z0.4") == "切面内"
    assert region_of("section:p2") == "断面之间"
    assert region_of("region:left") == "region:left"


def test_evaluate收的是工厂函数(ds):
    """类型上就必须是工厂 —— 每折要用自己的排除集重新训练。"""
    with pytest.raises(TypeError, match="工厂函数"):
        evaluate(FieldPipeline(PipelineConfig.fallback(), ds), ds, position_folds(ds))


def test_留一测点评估覆盖全部三万一三九二行(ds):
    res = evaluate(_factory(ds), ds, position_folds(ds))
    assert isinstance(res, EvalResult)
    assert res.per_point["n"].sum() == 24 * 1308


def test_逐测点表每个传感器一行(ds):
    res = evaluate(_factory(ds), ds, position_folds(ds))
    assert len(res.per_point) == 24
    assert res.per_point["n"].eq(1308).all()
    assert sorted(res.per_point["sensor_id"]) == list(range(24))


def test_报告自带AB两组与差值(ds):
    res = evaluate(_factory(ds), ds, position_folds(ds))
    assert isinstance(res.ab, ABResult)
    assert res.ab.mae_a > 0 and res.ab.mae_b > 0
    assert res.ab.gap == pytest.approx(res.ab.mae_a - res.ab.mae_b)


def test_AB来自四折各自的均值(ds):
    res = evaluate(_factory(ds), ds, position_folds(ds))
    a = res.metrics[res.metrics["group"] == "A"]["mae"].mean()
    assert res.ab.mae_a == pytest.approx(a)


def test_分区指标表按折族与区域分列(ds):
    res = evaluate(_factory(ds), ds, position_folds(ds))
    assert {"fold_kind", "fold", "region", "group", "n", "mae", "rmse", "r2"} <= set(res.metrics.columns)
    assert set(res.metrics["fold_kind"]) == {"position"}
    assert set(res.metrics["region"]) == {"切面内"}
    assert len(res.metrics) == 8


def test_断面折没有AB分组(ds):
    res = evaluate(_factory(ds), ds, section_folds(ds))
    assert res.ab is None
    assert set(res.metrics["region"]) == {"断面之间"}
    assert set(res.metrics["fold_kind"]) == {"section"}


def test_留一断面折的中间棚误差等于规格书的数(ds):
    """留一断面把整个 p2 棚留出，那一折的训练集里就只剩 y ∈ {3, 15} —— y=9 上没有任何
    样本。规格书 §基线表把这个区域的证据写成
    「留一断面 MAE = 0.2654 = |T(y=9) − [T(y=3)+T(y=15)]/2|」，指的就是**R2 合规估计量**：
    先在各断面自己的 y 上算，再按 1/dy 混合。`predict_points` 现在就是这么做的（见
    test_pipeline.py 的 R2 一族用例），所以这个数由代码直接产出，无需手工对拍。

    曾经这里是 0.4777（每折重训后在 y=9 直接查趋势）—— 那 0.21 的差就是违反 R2 的代价。
    """
    res = evaluate(_factory(ds), ds, section_folds(ds))
    mid = res.per_point[res.per_point["shed"] == "p2"]["mae"].mean()
    assert mid == pytest.approx(0.2654, abs=2e-3), f"留一断面 p2 MAE = {mid:.4f}"


def test_指标表带tag(ds):
    res = evaluate(_factory(ds), ds, position_folds(ds), tag="unit-test")
    assert set(res.metrics["tag"]) == {"unit-test"}


def test_在训练段上评估不会形状对不上():
    """`ti` 写死 `C.EXPECTED_ROWS`（1308）时，训练段只有 1164 行。

    这不是崩溃 —— 是一条形状错位的静默错误，而它只会发生在「留出之后」这条路上。
    （实测的失败形态是 `IndexError`：`_design_matrix` 读 `self._bg_temp[t_index]`，
    而那一列只有 1164 个；无论它以哪一种方式红，红的地方都是这条写死的长度。）

    这个模块整体带 `pytest.mark.slow`（见文件头的 `pytestmark`），不必再逐条标。
    """
    from tfield import config as C
    from tfield.data.loader import HOLDOUT_CUTOFF, split_holdout

    ds = load_dataset(test_data_path())
    train = split_holdout(ds, HOLDOUT_CUTOFF).train
    folds = [f for f in position_folds(train) if f.group == "A"][:1]
    assert folds, "A 组一折都没有，这个测试什么也没验到"

    res = evaluate(_factory(train), train, folds,
                   groups=C.DEFAULT_FEATURE_GROUPS, tag="holdout")
    assert int(res.metrics["n"].iloc[0]) == len(train.wide) * len(folds[0].test_sensors)
    assert res.metrics["mae"].iloc[0] == res.metrics["mae"].iloc[0]  # 不是 NaN
