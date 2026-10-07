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


# ── 折外预测的长表出口（页② 的精度图表要的就是它）──

def test_折外预测摊平成逐点逐时刻的长表(ds):
    """T10 的另一半：行数、无重、时间下标齐全。

    行数是**硬数**：24 个测点 × 1308 个时刻。少一折、或多留一折，
    它都会变 —— 而「折外预测」这四个字全靠这张表说的是全部折。
    """
    from tfield.validation.report import OOF_COLUMNS, out_of_fold_predictions

    oof = out_of_fold_predictions(_factory(ds), ds, position_folds(ds))
    assert tuple(oof.columns) == OOF_COLUMNS
    assert len(oof) == 24 * len(ds.wide)
    # 同一个 (测点, 时刻) 只能出现一次 —— 出现两次就是某一折被数了两遍
    assert int(oof[["sensor_id", "t_index"]].duplicated().sum()) == 0
    assert sorted(oof["sensor_id"].unique()) == list(range(24))
    assert int(oof["t_index"].min()) == 0
    assert int(oof["t_index"].max()) == len(ds.wide) - 1


def test_折外预测的对数与逐折的_n_对得上(ds):
    """T10：两条路算出同一个「一共评估了多少对」。

    `evaluate` 的 `n` 是它自己数出来的，`out_of_fold_predictions` 的行数是
    另一种数法。两者相等，才说明长表没漏折也没重复。
    """
    from tfield.validation.report import out_of_fold_predictions

    folds = position_folds(ds)
    res = evaluate(_factory(ds), ds, folds)
    oof = out_of_fold_predictions(_factory(ds), ds, folds)
    assert len(oof) == int(res.metrics["n"].sum())


def test_折外预测里_pred_真的来自模型而不是抄了一遍_truth(ds):
    """防：循环里把 pred 写成 truth（或忘了赋值），表看起来齐全而图是一条直线。"""
    import numpy as np

    from tfield.validation.report import out_of_fold_predictions

    oof = out_of_fold_predictions(_factory(ds), ds, position_folds(ds))
    gap = np.abs(oof["pred"].to_numpy(float) - oof["truth"].to_numpy(float))
    assert gap.mean() > 0, "预测与实测逐点相同，这不是一个模型"
    assert np.isfinite(gap).all()


def test_没有折时返回空表而不是抛(ds):
    """Review Focus 5 的一半：零折不许崩。

    空表必须有**齐全的列** —— 调用方接着会读写这些列，列不齐会在
    离现场很远的地方炸（`oof["resid"]` 那种）。
    """
    from tfield.validation.report import OOF_COLUMNS, out_of_fold_predictions

    oof = out_of_fold_predictions(_factory(ds), ds, [])
    assert len(oof) == 0
    assert tuple(oof.columns) == OOF_COLUMNS


def test_折外预测收的也是工厂函数(ds):
    """与 `evaluate` 同一条契约：每折必须用那一折的排除集重新训练，
    给一个已经 fit 好的实例就是把折外变成折内。"""
    from tfield.validation.report import out_of_fold_predictions

    with pytest.raises(TypeError, match="工厂函数"):
        out_of_fold_predictions(FieldPipeline(PipelineConfig.fallback(), ds), ds,
                                position_folds(ds))
