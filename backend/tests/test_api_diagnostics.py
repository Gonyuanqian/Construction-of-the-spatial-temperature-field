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


def _post(client, **over):
    """打一次诊断：值**从面板载荷来**（不另抄一份常量），可以覆盖几维。

    `over` 的键是 `metric_power` 这种下划线写法（Python 形参名放不下点号），
    这里换成点号再合并。

    ⚠️ `k.replace("_", ".", 1)`：`metric_power` → `metric.power` ✓，
    `cross_shed` → `cross.shed` ✗。所以 `cross_shed` 走不到这条路 ——
    覆盖 `cross_shed` 的用例直接手写完整请求体（见 `test_布尔不许拿_1_顶`）。
    """
    panel = client.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    params.update({k.replace("_", ".", 1): v for k, v in over.items()})
    return client.post("/api/calibration/diagnostics", json={"params": params})


@pytest.fixture(autouse=True)
def _reset_diagnostics():
    """每个用例从空缓存开始。缓存是**模块级**的，不清就让「算了几遍」数不准。"""
    from api import diagnostics
    diagnostics._CACHE = diagnostics.DiagnosticsCache()
    yield


def test_诊断出口给出基线密度与残差(client):
    b = _post(client).json()
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
    _post(client)
    first = diagnostics._CACHE.n_builds
    _post(client)
    assert first == 1, "第一次就应当算了一遍"
    assert diagnostics._CACHE.n_builds == 1, "第二次没命中缓存，又跑了一遍八折"


def test_换一套参数会重算_同一套参数是秒回的(client):
    """T11：参数进了缓存键。不进去的话，拖完滑块点训练会拿回**上一套参数**
    的图 —— 而图上没有任何一个字会说这件事。

    ⚠️ 这一条与上面那条**不是**同一件事：上面验的是「同一份包同一套值不会
    白跑」，这一条验的是「换了一套值**必须**重跑」。只写前者的话，
    一个把参数签名丢掉的键也能过。
    """
    from api import diagnostics
    _post(client)
    assert diagnostics._CACHE.n_builds == 1
    _post(client)
    assert diagnostics._CACHE.n_builds == 1, "同一套参数又算了一遍"
    _post(client, metric_power=3)
    assert diagnostics._CACHE.n_builds == 2, "换了一套参数却命中了旧键"


def test_换一套参数真的算出了不一样的东西(client):
    """光验「缓存没命中」不够：得验参数**真的**走到了 `FieldPipeline`
    （规格书 §3.4 那条唯一的作用点）。一个「签了名但没用上」的实现
    能让上面那条全绿，而屏上永远是同一套数的图。
    """
    from tfield.calibration import IDW_SPACE

    base = client.get("/api/calibration").json()["panel"]
    cur = {r["key"]: r["current"] for r in base["trend"] + base["idw"]}
    other = next(v for v in IDW_SPACE["power"] if v != cur["metric.power"])

    a = _post(client).json()["accuracy"]["model"]["mae"]
    b = client.post("/api/calibration/diagnostics",
                    json={"params": {**cur, "metric.power": other}}).json()
    assert b["accuracy"]["model"]["mae"] != a, "换了距离幂，精度逐位相同"


@pytest.mark.parametrize("over, hint", [
    ({"metric.ly": 1.0}, "不在搜索域内"),
    ({"metric.power": 99}, "只能取"),
    ({"trend.nope": 1}, "不认识的参数"),
    ({"metric.power": None}, "只能取"),
])
def test_值必须在搜索空间里(client, over, hint):
    """值域**只有一个定义处**：库的搜索空间。客户端造不出一个空间里没有的值。"""
    panel = client.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    r = client.post("/api/calibration/diagnostics", json={"params": {**params, **over}})
    assert r.status_code == 422
    assert hint in r.json()["detail"]


def test_布尔不许拿_1_顶(client):
    """`True == 1` 是 Python 的语言事实，不是我们的设计。

    `cross_shed` 的候选是 `[True, False]` —— 只写 `v in cand` 的话，
    一个 `1` 会被当成「开」收下，而 1 从来不是一个档位。
    """
    panel = client.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    params["cross_shed"] = 1
    r = client.post("/api/calibration/diagnostics", json={"params": params})
    assert r.status_code == 422
    assert "cross_shed" in r.json()["detail"]


def test_整数维收得下_json_的整数(client):
    """JSON 不区分 `1` 与 `1.0`，而 `IDW_SPACE["power"]` 里 `1` 是 int、`1.5` 是 float。

    拿 `type(v) is type(c)` 去比，一个前端从 JSON 读回来的 `2`（整数）
    会被判成非法值 —— 而那正是浏览器**唯一**能发出来的东西。
    """
    panel = client.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    params["metric.power"] = 2          # 候选里是 `2`（int）与 `2.5`（float）
    assert client.post("/api/calibration/diagnostics",
                       json={"params": params}).status_code == 200


def test_十二个要一起给(client):
    """少一个不许猜默认值：这一条最不能出的错就是「这个数是拿哪套参数算的」
    说不清，而补一个默认值正是那样。"""
    panel = client.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    params.pop("metric.power")
    r = client.post("/api/calibration/diagnostics", json={"params": params})
    assert r.status_code == 422
    assert "metric.power" in r.json()["detail"]


def test_响应里带回实际用的那套值(client):
    """§四.3 的凭据：前端拿 `params_used` 比对屏上那套值，对不上就整块不显示。"""
    panel = client.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    b = client.post("/api/calibration/diagnostics", json={"params": params}).json()
    assert b["params_used"] == params


def test_旧包给出的当前值也收得下():
    """F1（预检裁定）：`_panel` 会把旧包的当前值并进那一维的档位（T12 的后半）。

    于是**面板给出的默认值**就可能是今天搜索空间里没有的值，而前端把屏上这套
    原样发回来 —— 这一条必须收下。收不下的话，页② 在「拿旧版搜索空间训出来的
    包」上第一次点「开始训练」就是 422，而屏上那个值是面板自己摆上去的，
    用户没有任何办法把它调对。

    与 `test_当前值不在候选里时并进候选`（Task 1）是一对：那条钉面板给出什么，
    这条钉后端收不收。喂假包的理由与那条相同：真包与今天的空间同版，走不到这一支。
    """
    from types import SimpleNamespace

    from api.routes import calibration as cal_routes

    fake = SimpleNamespace(
        metric=SimpleNamespace(power=9.9, lx=1.0, ly=1.0, lz=0.03),
        trend_params={k.partition(".")[2]: 0
                      for k in cal_routes.TUNED_KEYS if k.startswith("trend.")},
        cross_shed=True,
    )
    panel = cal_routes._panel(fake, None)
    values = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}

    # 面板摆上屏的这套值（含 9.9 与那一堆 0）必须一个不落地收下。
    assert cal_routes._validated_domain(values, fake) == values

    # 反面：一个既不在今天的空间里、也不是当前值的数，照旧要拒 ——
    # 上一条不许把「值域」这扇门整个拆掉。
    bad = dict(values, **{"metric.power": 8.8})
    with pytest.raises(cal_routes.HTTPException) as e:
        cal_routes._validated_domain(bad, fake)
    assert e.value.status_code == 422 and "metric.power" in e.value.detail


def test_换数据集之后诊断缓存被清掉(client, tmp_path, monkeypatch):
    """§8.4：诊断要登记进 `reset_cache()`。

    不清的后果是**新人拿到旧数据集的图** —— 而图上没有任何一个字会说这件事。
    """
    from api import deps, diagnostics, paths
    _post(client)
    assert diagnostics._CACHE.n_builds == 1
    deps.reset_cache()
    assert diagnostics._CACHE.n_builds == 0, "换数据集没有清诊断缓存"
    # 收尾：把交付数据集装回去，别留给后面的模块
    deps.install_dataset(paths.dataset_path())


def test_诊断的缓存键比管线缓存多一格_因为参数只进诊断那条链():
    """键里四个东西一个都不能少。

    少了 `created_at`：A/B 分组换过的另一份包会共用同一份图 ——
      `accuracy()` 读的是 `bundle.metrics` 里哪几折属于 B 组，
      那是**包的数据**，参数签名抓不住它。
    少了 `groups_sig`：换了特征组还在用旧图。
    少了数据集签名：换了数据还在用旧图。
    少了参数签名：拖完滑块还在看上一套参数的图。

    ⚠️ **前三位与 `deps.PipelineCache.key_of` 逐位相等**，第四位是诊断特有的。
    这条守卫以前钉的是「两个键一模一样」；判据改成「前三格相等」，
    理由是：管线缓存只装包**自己**那套参数（`deps.get_pipeline()` 走的是
    `bundle.config()`，从不接受外部参数），它不需要参数签名。
    改的是判据，防的东西没变 —— 少一格仍然会红。
    """
    from api import deps, diagnostics
    from dataclasses import replace
    deps.set_current_dataset(paths.dataset_path())
    ds = deps.get_train_dataset()
    b = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=BACKEND / "configs")

    dk = diagnostics.DiagnosticsCache.key_of(ds, C.DEFAULT_FEATURE_GROUPS, b, "sig")
    pk = deps.PipelineCache.key_of(ds, C.DEFAULT_FEATURE_GROUPS, b)
    assert dk[:3] == pk, "前三格必须逐位相等"
    assert len(dk) == 4 and dk[3] == "sig"

    # 少任何一位都会变
    assert diagnostics.DiagnosticsCache.key_of(
        ds, C.DEFAULT_FEATURE_GROUPS, replace(b, created_at="别的时刻"), "sig") != dk
    assert diagnostics.DiagnosticsCache.key_of(
        ds, C.DEFAULT_FEATURE_GROUPS, b, "别的签名") != dk


def test_没有包时诊断出口报_409_并说清下一步(monkeypatch, tmp_path):
    """⚠️ 请求体是**合法的** —— 面板与包无关（Task 1 的空态用例钉着）。

    这样 409 就只可能是「没有包」这一个原因，而不是「请求体不合法」。
    """
    from fastapi.testclient import TestClient
    from api import deps, paths
    from api.main import create_app
    from api.routes import calibration as cal_routes
    deps.set_current_dataset(paths.dataset_path())
    monkeypatch.setattr(cal_routes, "CONFIGS_ROOT", tmp_path)
    c = TestClient(create_app())
    panel = c.get("/api/calibration").json()["panel"]
    params = {r["key"]: r["current"] for r in panel["trend"] + panel["idw"]}
    r = c.post("/api/calibration/diagnostics", json={"params": params})
    assert r.status_code == 409
    assert "参数优选" in r.json()["detail"]


def test_请求体不合法时报_422_而不是被没有包的_409_盖住(monkeypatch, tmp_path):
    """⚠️ 次序：**结构检查排在 409 之前**（与上一条互为对照）。

    上一条送的是**合法**请求体，于是 422 与 409 谁也分不出先后（两种实现都绿）；
    这一条把「没有包」与「请求体不合法」两个条件**同时**摆上桌，只认 422 ——
    若把结构检查挪到 409 之后，「先去做参数优选」那个 409 就会盖住客户端
    自己的 bug（键写漏了），而这一屏最不能出的错就是「把哪一处错说成哪一处」。

    请求体故意漏键：`{"metric.power": 2}` 少另外十一维，`_validated_shape`
    必拒（缺键那条分支），且**与盘上有没有包无关**。
    """
    from fastapi.testclient import TestClient
    from api import deps, paths
    from api.main import create_app
    from api.routes import calibration as cal_routes
    deps.set_current_dataset(paths.dataset_path())
    monkeypatch.setattr(cal_routes, "CONFIGS_ROOT", tmp_path)
    c = TestClient(create_app())
    r = c.post("/api/calibration/diagnostics",
               json={"params": {"metric.power": 2}})
    assert r.status_code == 422, (
        f"结构检查应当排在 409 之前：拿到 {r.status_code} "
        f"{r.json().get('detail')!r}")
    assert "缺了这些参数" in r.json()["detail"]


def test_诊断的上屏文案过了字形守卫(client):
    """随响应体上屏的纯文本不许夹带被禁的连接符与 markdown 标记（硬约束 4）。"""
    b = _post(client).json()
    rendered = [b["note"], b["accuracy"]["baseline"]["label"],
                b["accuracy"]["model"]["label"]]
    rendered += [p["label"] for p in b["residual"]] + [p["axis"] for p in b["residual"]]
    for s in rendered:
        for bad in ("——", "**", "`", " · ", "→", "↳"):
            assert bad not in s, f"上屏文案里出现了被禁的 {bad!r}：{s!r}"
