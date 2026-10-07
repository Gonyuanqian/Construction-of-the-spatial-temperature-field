"""页② 第三段的精度面：基线、密度矩阵、残差分箱。

这一份**不建 TestClient**：Task 4 要验的是纯计算，把它放进 HTTP 里
会让失败信息从「哪一个箱算错了」变成「哪一条路由 500 了」。
出口那几条在 Task 5 里接着写。
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, paths                                    # noqa: E402
from tfield.calibration import load_for                        # noqa: E402
from tfield import config as C                                  # noqa: E402

pytestmark = pytest.mark.slow      # 一次 oof_table 要 8 折各 fit 一遍，十秒上下


@pytest.fixture(scope="module")
def bundle():
    """训练段那一份包 —— 页② 报的就是它。

    ⚠️ **用 `deps.get_train_dataset()` 拿数据集，不自己 `split_holdout`。**
    页② 报的是训练段，而「训练段是哪一段」由 `deps` 说了算（它还要把留出段
    的开销算进去）。这里自己切一遍就等于把那条规则实现了第二遍 ——
    与 `test_api_train.py` 的 `_current_dataset` 夹具是同一套做法。
    盘上那两份包按数据集签名分：`bundle_6145fa9261e89f1b_d6294c09.json`
    是全量的，`bundle_6145fa9261e89f1b-h20260727T1200_d6294c09.json`
    是训练段的（`-h` 后面就是留出切点）。`load_for` 只会捡到后者。
    """
    deps.set_current_dataset(paths.dataset_path())
    ds = deps.get_train_dataset()
    b = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=BACKEND / "configs")
    assert b is not None, "本项目 configs/ 下应当有训练段那一份包"
    return b


@pytest.fixture(scope="module")
def oof(bundle):
    """**整个模块共用一次折外预测** —— 它是最贵的那一步（十几秒）。"""
    from api import diagnostics
    ds = deps.get_train_dataset()
    return ds, diagnostics.oof_table(ds, bundle)


# ── 折外长表 ──

def test_折外表用的就是库那九列再加五列(oof):
    from tfield.validation.report import OOF_COLUMNS
    _ds, table = oof
    assert tuple(OOF_COLUMNS) == tuple(table.columns[:len(OOF_COLUMNS)])
    assert {"baseline", "hour", "resid", "z", "x"} <= set(table.columns)
    assert len(table) == 24 * len(_ds.wide)


def test_基线逐行按自己的时刻取_不是广播(oof):
    """`bg_temp` 是时刻的函数，与测点无关 —— 但取法必须**逐行**。

    广播（`bg[0]` 或 `bg[:n]`）在时刻顺序没被打乱时看起来完全一样，
    只在顺序变了的时候静默错位。这条用一个容易区分的性质钉住：
    同一个时刻上，24 个测点拿到的基线必须**完全相等**；而相邻两个时刻的
    基线必须**不相等**（这份数据 5 分钟一帧，背景温度不会五点全一样）。
    """
    _ds, table = oof
    by_t = table.groupby("t_index")["baseline"].nunique()
    assert int(by_t.max()) == 1, "同一个时刻上不同测点的基线不一样 —— 取错了列"
    first_two = table[table["t_index"].isin([0, 1])].groupby("t_index")["baseline"].first()
    assert first_two.iloc[0] != first_two.iloc[1], "相邻两刻的基线相同，这个断言证不了任何事"


def test_残差是预测减实测(oof):
    _ds, table = oof
    gap = (table["resid"] - (table["pred"] - table["truth"])).abs().max()
    assert float(gap) == 0.0, "resid 的定义是 预测 − 实测（正 = 报高了）"


# ── 基线对照（T9）──

def test_基线与模型同折同段(bundle, oof):
    """**本文件最贵的一条**（规格书 §6.2）。

    `metrics.py` 注释里那个 0.8896 是**全量数据集**上的基线，而页② 报的是
    **训练段**。两个数并排放上屏，就是本页自己一直在警告的那种谎
    （「同折族、不同参数，两个数不可直接比大小」）。

    所以这里两头都钉：折名集合必须来自模型的 `metrics`，且都在 B 组。
    """
    from api import diagnostics
    _ds, table = oof
    acc = diagnostics.accuracy(table, bundle)

    model_folds = {str(f) for f in bundle.metrics["fold"]}
    assert set(acc["folds"]) <= model_folds, "基线算在了模型没算过的折上"
    assert set(acc["folds"]) == {str(f) for f in
                                 bundle.metrics.loc[bundle.metrics["group"] == "B", "fold"]}, (
        "基线必须算在 **B 组**那些折上 —— 旁边坐的是未参与选参的那一组")
    assert acc["folds"] == sorted(acc["folds"])
    # 模型那一行的 n 与逐折表里 B 组的 n 之和一致
    b_n = int(bundle.metrics.loc[bundle.metrics["group"] == "B", "n"].sum())
    assert acc["model"]["n"] == b_n
    assert int(table[table["fold"].isin(acc["folds"])].shape[0]) == b_n


def test_基线那一行的_mae_等于拿背景温度直接当预测(bundle, oof):
    """基线的定义就一句话：不作任何建模，背景温度就是棚温。"""
    from api import diagnostics
    from tfield.validation.metrics import mae
    _ds, table = oof
    acc = diagnostics.accuracy(table, bundle)
    part = table[table["fold"].isin(acc["folds"])]
    expect = float(mae(part["truth"].to_numpy(float), part["baseline"].to_numpy(float)))
    assert acc["baseline"]["mae"] == pytest.approx(expect, abs=1e-12)
    assert acc["baseline"]["label"] == diagnostics.BASELINE_LABEL


def test_倍数是算出来的(bundle, oof):
    """§6.3：倍数是 `基线的 MAE / 模型的 MAE`。写死在界面上迟早对不上。"""
    from api import diagnostics
    _ds, table = oof
    acc = diagnostics.accuracy(table, bundle)
    assert acc["ratio"] == pytest.approx(acc["baseline"]["mae"] / acc["model"]["mae"], rel=1e-9)
    assert acc["ratio"] > 1, "本项目上模型应当比「拿背景温度当棚温」准"


def test_模型的_mae_与包里的_ab_mae_b_一致(bundle, oof):
    """两条路算同一个数：一条从这里的长表合并算，一条从包里的 `ab`。

    **这条测试不是重复声明**（更正 3）：`accuracy` 里模型那一行是拿长表
    现算的，不是抄包。两者相等**不是巧合** —— position 折每个折的 n 完全相同
    （3 测点 × 全部时刻），所以「先按折求 MAE 再平均」与「合起来求一个 MAE」
    恰好是同一个数。**它是那个前提的守卫**：哪一天折的 n 不齐了，它会红，
    而红的地方正是「基线那一行与模型那一行比的其实不是同一个统计量」。

    ⚠️ 只有 MAE 有这条等式。RMSE 平方之后不可按 n 加权平均，合并值与
    逐折均值本来就不是一个数，所以这里**不许**顺手把 rmse 也断言上。
    """
    from api import diagnostics
    _ds, table = oof
    acc = diagnostics.accuracy(table, bundle)
    assert acc["model"]["mae"] == pytest.approx(bundle.ab["mae_b"], abs=1e-12)


# ── 密度矩阵（T10 的一半，§7.1）──

def test_密度矩阵是方阵且两个轴同一个范围(oof):
    """对角图：两个轴量纲相同、范围必须相同，否则 y = x 不是 45 度。"""
    from api import diagnostics
    _ds, table = oof
    den = diagnostics.density(table)
    assert den["bins"] == 60
    counts = np.asarray(den["counts"])
    assert counts.shape == (60, 60)
    assert den["lo"] < den["hi"]
    assert den["n"] == len(table)
    assert int(counts.sum()) == den["n"], "有格子丢了点 —— 范围没盖住全部数据"


def test_密度矩阵的对角线上点最多(oof):
    """模型比「一直报均值」强，这条才成立。对角线以外全白就说明选错了轴。"""
    from api import diagnostics
    _ds, table = oof
    counts = np.asarray(diagnostics.density(table)["counts"])
    diag = sum(int(counts[i, i]) for i in range(counts.shape[0]))
    assert diag > int(counts.sum()) * 0.5


def test_实测与预测都只有一个取值时密度矩阵仍然是一个合法方框(oof):
    """**Review Focus 5**：`lo == hi` 时 `np.histogram2d` 的范围是零宽。

    人造一份常数表 —— 这种事真会发生（某一折整段缺值被填成一个数）。
    期望：不崩，且给出一个非零宽度的方框。
    """
    from api import diagnostics
    flat = pd.DataFrame({"truth": [5.0] * 10, "pred": [5.0] * 10})
    den = diagnostics.density(flat)
    assert den["lo"] < den["hi"]
    assert int(np.asarray(den["counts"]).sum()) == 10


def test_密度矩阵里_NaN_的点被丢掉而不是把矩阵打成_NaN(oof):
    """`allow_nan=False` 不吃 NaN：一个 NaN 混进计数矩阵就是整页 500。"""
    from api import diagnostics
    part = pd.DataFrame({"truth": [1.0, 2.0, float("nan")],
                         "pred": [1.0, 2.0, 3.0]})
    den = diagnostics.density(part)
    assert den["n"] == 2
    assert int(np.asarray(den["counts"]).sum()) == 2


# ── 残差三连（§7.2）──

def test_残差三连的箱数是这份数据的性质(bundle, oof):
    """⚠️ 后两张**不是曲线**：高度只有 3 个取值、棚长只有 7 个。

    写「三连」听着像三条连续曲线，实际不是 —— 这条测试把真实的箱数写死在
    这里，免得验收时以为图上少了东西。
    """
    from api import diagnostics
    _ds, table = oof
    panels = {p["key"]: p for p in diagnostics.residuals(table)}
    assert set(panels) == {"diurnal", "height", "length"}
    assert len(panels["diurnal"]["bins"]) == 24
    assert len(panels["height"]["bins"]) == 3
    assert len(panels["length"]["bins"]) == 7
    assert panels["height"]["bins"][0]["at"] == pytest.approx(0.4)
    assert panels["length"]["bins"][0]["at"] == pytest.approx(0.15)


def test_每个箱报三个数且标准误只在_n_大于_1_时才有(oof):
    from api import diagnostics
    _ds, table = oof
    for panel in diagnostics.residuals(table):
        for b in panel["bins"]:
            assert set(b) == {"at", "mean", "n", "se"}
            assert b["n"] > 0
            if b["n"] > 1:
                assert b["se"] is not None and b["se"] > 0
            else:
                assert b["se"] is None, "一个点的样本算不出标准误 —— 报 0 是在假装精确"


def test_箱内的平均残差与逐点重算一致(oof):
    """箱均值必须真的来自 `resid`，而不是某一个别的列。"""
    from api import diagnostics
    _ds, table = oof
    panel = {p["key"]: p for p in diagnostics.residuals(table)}["height"]
    for b in panel["bins"]:
        part = table.loc[table["z"] == b["at"], "resid"]
        assert b["mean"] == pytest.approx(float(part.mean()), abs=1e-12)
        assert b["n"] == int(part.size)


def test_整列残差是_NaN_时那一箱是_null_而不是_500():
    """**Review Focus 4**：整段时间轴缺值 → 箱内全是 NaN。

    `meand` 给 NaN，而 `allow_nan=False` 会把整页打成 500。
    期望：`mean` 翻成 None，箱本身**留在表里**（那一箱真实存在，藏就是漏报）。
    """
    from api import diagnostics
    table = pd.DataFrame({
        "hour": [0, 0, 1, 1], "resid": [float("nan"), float("nan"), 0.5, -0.5],
        "z": [0.4] * 4, "x": [0.15] * 4,
    })
    panel = {p["key"]: p for p in diagnostics.residuals(table)}["diurnal"]
    assert len(panel["bins"]) == 2
    zero = next(b for b in panel["bins"] if b["at"] == 0)
    assert zero["mean"] is None
    assert zero["n"] == 0, "NaN 不是样本 —— 数进去会让「箱内样本数」撒谎"
    assert zero["se"] is None
    import json
    json.dumps(panel, allow_nan=False)      # 不许有 NaN 混出去


# ── 出口与缓存（T12）──

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import create_app
    from api import deps, paths
    deps.set_current_dataset(paths.dataset_path())
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    """每个用例从空缓存开始。缓存是**模块级**的，不清就让「算了几遍」数不准。"""
    from api import diagnostics
    diagnostics._CACHE = diagnostics.DiagnosticsCache()
    yield


def test_诊断出口给出基线密度与残差(client):
    b = client.get("/api/calibration/diagnostics").json()
    assert b["present"] is True
    assert b["created_at"] and b["groups_sig"] and b["dataset_sig"]
    assert b["n_sensors"] == 24 and b["n_times"] == 1164
    assert b["n_points"] == 24 * 1164
    assert len(b["density"]["counts"]) == 60
    assert b["accuracy"]["baseline"]["label"]
    assert [p["key"] for p in b["residual"]] == ["diurnal", "height", "length"]
    # allow_nan=False 不吃 NaN：整份载荷必须能原样序列化出去
    import json
    json.dumps(b, allow_nan=False)


def test_诊断按包缓存_连调两次只拟合一遍(client):
    """T12：不缓存的话，每开一次页② 都白跑一遍八折（十几秒）。"""
    from api import diagnostics
    client.get("/api/calibration/diagnostics").json()
    first = diagnostics._CACHE.n_builds
    client.get("/api/calibration/diagnostics").json()
    assert first == 1, "第一次就应当算了一遍"
    assert diagnostics._CACHE.n_builds == 1, "第二次没命中缓存，又跑了一遍八折"


def test_换数据集之后诊断缓存被清掉(client, tmp_path, monkeypatch):
    """§8.4：诊断要登记进 `reset_cache()`。

    不清的后果是**新人拿到旧数据集的图** —— 而图上没有任何一个字会说这件事。
    """
    from api import deps, diagnostics, paths
    client.get("/api/calibration/diagnostics").json()
    assert diagnostics._CACHE.n_builds == 1
    deps.reset_cache()
    assert diagnostics._CACHE.n_builds == 0, "换数据集没有清诊断缓存"
    # 收尾：把交付数据集装回去，别留给后面的模块
    deps.install_dataset(paths.dataset_path())


def test_诊断的缓存键与管线缓存同一个形状():
    """键里三个东西一个都不能少。

    少了 `created_at`：重标一次之后界面还在给你上一次的图。
    少了 `groups_sig`：换了特征组还在用旧图。
    少了数据集签名：换了数据还在用旧图。

    ⚠️ 这里不能直接调 `deps.PipelineCache.key_of`（`tests/test_routes_use_cache.py`
    规定 `api/**` 从 `deps` 取名字只许白名单里那几个），所以两个实现各写一份 ——
    这条测试就是钉住它们**相等**的那根钉子。
    """
    from api import deps, diagnostics
    from dataclasses import replace
    deps.set_current_dataset(paths.dataset_path())
    ds = deps.get_train_dataset()
    b = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=BACKEND / "configs")
    assert diagnostics.DiagnosticsCache.key_of(ds, C.DEFAULT_FEATURE_GROUPS, b) == \
        deps.PipelineCache.key_of(ds, C.DEFAULT_FEATURE_GROUPS, b)
    # 少任何一位都会变
    assert diagnostics.DiagnosticsCache.key_of(
        ds, C.DEFAULT_FEATURE_GROUPS, replace(b, created_at="别的时刻")) != \
        deps.PipelineCache.key_of(ds, C.DEFAULT_FEATURE_GROUPS, b)


def test_没有包时诊断出口报_409_并说清下一步(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from api import deps, paths
    from api.main import create_app
    from api.routes import calibration as cal_routes
    deps.set_current_dataset(paths.dataset_path())
    monkeypatch.setattr(cal_routes, "CONFIGS_ROOT", tmp_path)
    r = TestClient(create_app()).get("/api/calibration/diagnostics")
    assert r.status_code == 409
    assert "参数优选" in r.json()["detail"]


def test_诊断的上屏文案过了字形守卫(client):
    """随响应体上屏的纯文本不许夹带被禁的连接符与 markdown 标记（硬约束 4）。"""
    b = client.get("/api/calibration/diagnostics").json()
    rendered = [b["note"], b["accuracy"]["baseline"]["label"],
                b["accuracy"]["model"]["label"]]
    rendered += [p["label"] for p in b["residual"]] + [p["axis"] for p in b["residual"]]
    for s in rendered:
        for bad in ("——", "**", "`", " · ", "→", "↳"):
            assert bad not in s, f"上屏文案里出现了被禁的 {bad!r}：{s!r}"
