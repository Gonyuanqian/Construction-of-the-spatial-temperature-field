"""页② 的数据面：特征构造表与标定包。

这一页最容易误读，所以有一条测试专门守那句**口径**：
「最优」最优的对象是这一份数据集 + 这一组特征组 + 留一测点这个准则，
而且只在 A 组上挑出来的；没有包时用的是兜底参数，不是最优。
那句话必须**随数据一起从后端来** —— 让前端各自去写，迟早写成
「最优参数」四个字，而那是这张页面最大的谎。
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps                                     # noqa: E402
from api.main import create_app                          # noqa: E402
from tfield import config as C                           # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


# ── 特征构造表 ──

def test_特征组表覆盖四组且列名来自后端库(client):
    b = client.get("/api/features").json()
    assert b["default_groups"] == list(C.DEFAULT_FEATURE_GROUPS)
    assert [g["group"] for g in b["groups"]] == list(C.DEFAULT_FEATURE_GROUPS)
    by_group = {g["group"]: g for g in b["groups"]}
    assert by_group["coord"]["columns"] == ["x", "y", "z"]
    assert by_group["zbasis"]["columns"] == ["z2", "z3"]
    assert by_group["meteo"]["columns"] == [
        "bg_temp", "bg_rh", "bg_light", "hour", "frac_day"]
    assert by_group["interaction"]["columns"] == [
        "bg_temp_x_z", "bg_light_x_z", "bg_temp_x_light"]
    assert all(g["n_columns"] == len(g["columns"]) for g in b["groups"])
    assert all(g["what"] for g in b["groups"])


def test_特征组的列名与后端库不是各写一份(client):
    """列名是**唯一真源**在 `tfield.features.add_feature_groups` ——
    接口必须从它那里取，不能手抄。手抄的那一份会在有人加特征时静默过期。"""
    import pandas as pd

    from tfield.features import add_feature_groups

    b = client.get("/api/features").json()
    zero = pd.DataFrame({k: [0.0] for k in
                         ("x", "y", "z", "bg_temp", "bg_rh", "bg_light",
                          "hour", "frac_day")})
    for g in b["groups"]:
        expect = list(add_feature_groups(zero, (g["group"],)).columns)
        assert g["columns"] == expect, f"{g['group']} 的列名与后端库不一致"


def test_全列清单等于四组的并集(client):
    b = client.get("/api/features").json()
    union: list[str] = []
    for g in b["groups"]:
        for c in g["columns"]:
            if c not in union:
                union.append(c)
    assert b["all_columns"] == union


def test_全列数由后端给出_且等于并集长度(client):
    """全列清单的**列数**由后端报，前端不做任何计数。

    「按各组 n_columns 之和」与「并集长度」是两个来源；组分一旦重叠，两者会
    静默不一致 —— 这正是「前端不做任何数值计算」这条约束要防的事。所以这个数
    只有一个真源：后端算出来的并集长度。

    ⚠️ 写死 13 是有意的：只断言 `== len(all_columns)` 是拿同一个计算比自己，
    等于没测。13 = 3（coord）+ 2（zbasis）+ 5（meteo）+ 3（interaction）。
    """
    b = client.get("/api/features").json()
    assert b["n_all_columns"] == 13
    assert b["n_all_columns"] == len(b["all_columns"])


def test_两条不加特征的说明在(client):
    """它们是从 `tfield.features` 的模块说明里搬过来的 —— 有测试盯着源文件里还在。"""
    b = client.get("/api/features").json()
    joined = "".join(b["notes"])
    assert "滞后" in joined and "湿度" in joined
    src = (BACKEND / "src" / "tfield" / "features.py").read_text(encoding="utf-8")
    assert "不加滞后特征" in src and "不加测点湿度" in src, "后端库的说明变了，这边要跟着改"


# ── 标定包 ──

def test_标定包在_且报得出参数与指标(client):
    b = client.get("/api/calibration").json()
    assert b["present"] is True, "本项目 configs/ 下应当有迁移过来的标定包"
    # 与旧包（2026-10-03 那一份）的数不可直接比大小：同折族、不同参数。
    # 换口径重标过（留出段 2026-07-27 12:00 起 144 帧只在训练段上标定）。
    assert b["created_at"] == "2026-10-05T13:52:09+00:00"
    assert b["tool_version"] == "0.1.0"
    assert b["groups_sig"] == "d6294c09"
    assert b["feature_groups"] == list(C.DEFAULT_FEATURE_GROUPS)
    assert b["n_folds"] == 8 and b["fold_kind"] == "position"
    assert len(b["metrics"]) == 8 and len(b["per_point"]) == 24

    # 参数与搜索空间成对出现 —— 「这个值是从哪挑出来的」要答得出
    keys = {t["key"] for t in b["tuned_keys"]}
    assert "metric.power" in keys and "trend.n_estimators" in keys
    assert all({"key", "value", "space"} == set(t) for t in b["tuned_keys"])
    params = {p["param"]: p["value"] for p in b["params"]}
    assert params["metric.power"] == "0.5"
    assert params["metric.ly"] == "1"            # ly 固定 1.0，从未进过搜索空间
    assert params["cross_shed"] == "关"


def test_每个调过的参数都报得出它的搜索空间(client):
    """**两个键空间不一样**：`tuned_keys` 里叫 `metric.power`，`search.space` 里叫 `idw.power`；
    `cross_shed` 在搜索侧挂了 `idw.` 前缀。映射漏一条，那一维的空间就会显示成「—」，
    看起来像「这一维没搜过」—— 而它其实搜过，只是没报出来。

    这条测试就是拿 `bundle.tuned_keys` 的**每一个**键去问「空间呢」。
    """
    b = client.get("/api/calibration").json()
    empty = [t["key"] for t in b["tuned_keys"] if t["space"] == "—"]
    assert empty == [], f"这些参数报了值却没报搜索空间：{empty}"

    by_key = {t["key"]: t for t in b["tuned_keys"]}
    assert by_key["metric.power"]["space"]          # 0.5、0.7、1、1.5、2… 至少两个候选
    assert "、" in by_key["metric.power"]["space"], "只有一个候选的话就不是搜出来的"
    assert by_key["cross_shed"]["space"] in ("关、开", "开、关")


def test_逐折与逐点是标定包里的原数_不是现算的(client):
    """页② 显示的性能数字必须**逐位等于包里那一份**。

    重新评估一遍会得到一个略微不同的数（同样的折、同样的参数，浮点求和顺序不同），
    于是页面上的数与盘上包里的数对不上 —— 验收对盘时这是最尴尬的一种错。
    """
    import json

    from tfield.calibration import load_for
    from tfield.data.loader import HOLDOUT_CUTOFF, load_dataset, split_holdout, test_data_path

    b = client.get("/api/calibration").json()
    # ⚠️ **必须切训练段**：路由报的是按训练段标出来的那个包。拿整份文件去
    # `load_for` 会命中**另一个**包（2026-10-03 那一份全量标定），于是这条守卫
    # 变成「拿 A 包的数比 B 包的数」—— 它想守的「页面上的就是盘上那一份」
    # 一个字都没验到，却仍然是绿的。**这就是它上一轮红的原因。**
    ds = split_holdout(load_dataset(test_data_path()), HOLDOUT_CUTOFF).train
    bundle = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=BACKEND / "configs")
    assert bundle is not None

    m = {r["fold"]: r["mae"] for r in b["metrics"]}
    for _, row in bundle.metrics.iterrows():
        key = row["fold"]
        assert m[key] == float(row["mae"]), f"第 {key} 折的 MAE 不是包里那一个"
    pp = {(r["shed"], r["position"]): r["mae"] for r in b["per_point"]}
    for _, row in bundle.per_point.iterrows():
        assert pp[(row["shed"], row["position"])] == float(row["mae"])


def test_最差的那一折由后端指出来(client):
    """「最差的是哪一折」是读数，不是算术 —— 但它仍然是数值比较，
    所以由后端定，前端不排。"""
    b = client.get("/api/calibration").json()
    worst = max(b["metrics"], key=lambda r: r["mae"])
    assert b["worst_fold"]["fold"] == worst["fold"]
    assert b["worst_fold"]["mae"] == pytest.approx(worst["mae"], abs=1e-12)


def test_某一折_mae_是_NaN_时判最差不_500_而是报_null(monkeypatch):
    """「最差的那一折」必须从**原始**数值里挑，不能从已置空的那一份里挑。

    ⚠️ 这一条盯的是一个真会 500 的写法：`metrics` 一旦先过 `_jsonable`，
    NaN 单元格就变成 None，再对它 `float(...)` 直接抛
    `TypeError: float() argument must be ... not 'NoneType'` → HTTP 500。
    这不是假想输入 —— 同一个包里 `search.trials` 就成片是 NaN。
    """
    import json
    from dataclasses import replace as dc_replace

    from api.routes import calibration as cal_routes
    from tfield.calibration import load_for
    from tfield.data.loader import load_dataset, test_data_path

    ds = load_dataset(test_data_path())
    bundle = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=BACKEND / "configs")
    assert bundle is not None

    # 改的是**内存里的副本**，盘上的包一个字节都不动
    metrics = bundle.metrics.copy(deep=True)
    bad_fold = str(metrics.loc[0, "fold"])
    metrics.loc[0, "mae"] = float("nan")
    broken = dc_replace(bundle, metrics=metrics)

    monkeypatch.setattr(cal_routes, "load_for", lambda *a, **k: broken)
    c = TestClient(create_app())
    r = c.get("/api/calibration")

    assert r.status_code == 200, r.text
    body = r.json()
    by_fold = {m["fold"]: m for m in body["metrics"]}
    assert by_fold[bad_fold]["mae"] is None           # 非有限值翻成 null
    assert body["worst_fold"] is not None
    assert body["worst_fold"]["fold"] != bad_fold     # 不把 NaN 那折报成最差
    json.dumps(body, allow_nan=False)


def test_全折_mae_都是_NaN_时_worst_fold_为_None(monkeypatch):
    """一折都没有有限 MAE 时不许硬报一折 —— 把所有折都报成「最差」里的第一折，
    在这一页（最容易误读口径的一页）是句谎话。契约扩展：`worst_fold` 现在可为 null。"""
    from dataclasses import replace as dc_replace

    from api.routes import calibration as cal_routes
    from tfield.calibration import load_for
    from tfield.data.loader import load_dataset, test_data_path

    ds = load_dataset(test_data_path())
    bundle = load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=BACKEND / "configs")
    assert bundle is not None
    metrics = bundle.metrics.copy(deep=True)
    metrics["mae"] = float("nan")
    broken = dc_replace(bundle, metrics=metrics)

    monkeypatch.setattr(cal_routes, "load_for", lambda *a, **k: broken)
    c = TestClient(create_app())
    r = c.get("/api/calibration")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["worst_fold"] is None
    assert all(m["mae"] is None for m in b["metrics"])
    assert len(b["metrics"]) == 8


def test_ab_两组都报_且_gap_是负的这件事写在说明里(client):
    b = client.get("/api/calibration").json()
    ab = b["ab"]
    # 与旧包（2026-10-03 那一份）的数不可直接比大小：同折族、不同参数。
    # 换口径重标过（留出段 2026-07-27 12:00 起 144 帧只在训练段上标定）。
    assert ab["mae_a"] == pytest.approx(0.119411, abs=1e-6)
    assert ab["mae_b"] == pytest.approx(0.168553, abs=1e-6)
    assert ab["gap"] == pytest.approx(ab["mae_a"] - ab["mae_b"], abs=1e-9)
    assert ab["gap"] < 0


def test_口径说明必须随包一起来(client):
    """这是这一页最大的谎最容易出现的地方。"""
    b = client.get("/api/calibration").json()
    note = b["note"]
    for frag in ("兜底", "留一测点", "A 组"):
        assert frag in note, f"口径说明里少了「{frag}」—— 那几个字是这个数唯一的前提"


def _lz_space(b: dict) -> list[float]:
    """从**响应本身**读 lz 的搜索空间（`tuned_keys` 里 `metric.lz` 那一行的 space）。

    不另去盘上加载标定包：这一条要验的是「响应里的值与响应里的空间对得上」，
    空间也必须从响应里来 —— 换成从包里读，测的就不是这一页了。
    """
    row = next(t for t in b["tuned_keys"] if t["key"] == "metric.lz")
    assert row["space"] != "—", "lz 报了值却没报搜索空间，_lz_space 无从取起"
    return [float(v) for v in row["space"].split("、")]


def test_lz_落在搜索下界时要自己说出来(client):
    """**规则**：lz 踩在搜索下界 ⟺ `lz_note` 有话说。两头都要成立。

    不钉「本项目正好踩在下界」—— 那是**某一份标定包**的性质，换一次标定就没了
    （换成训练段重标之后 lz 从 0.005 挪到 0.03，旧写法当场失效）。
    钉规则是因为两个方向都是错：踩在下界不吭声，是把「没扫够」说成「已收敛」；
    没踩下界却发警告，是狼来了，警告多了就没人看了。
    """
    b = client.get("/api/calibration").json()
    lo = min(_lz_space(b))
    params = {p["param"]: p["value"] for p in b["params"]}
    at_bound = float(params["metric.lz"]) == lo
    if at_bound:
        assert b["lz_note"] is not None, "lz 贴着搜索下界时必须有提示，不许静默"
        assert "搜索下界" in b["lz_note"]
    else:
        assert b["lz_note"] is None, (
            f"lz = {params['metric.lz']} 不在下界 {lo:g} 上，不该发「还没扫够」的警告")


def test_没有标定包时也要答得出来(monkeypatch, tmp_path):
    """空状态是行动的邀请，不是一片空白（spec §8.5）。

    没有包时界面要能显示**兜底参数**，并明说它不是最优。
    """
    from api.routes import calibration as cal_routes

    monkeypatch.setattr(cal_routes, "CONFIGS_ROOT", tmp_path)
    c = TestClient(create_app())
    b = c.get("/api/calibration").json()

    assert b["present"] is False
    assert b["reason"] and "标定" in b["reason"]
    assert b["metrics"] == [] and b["per_point"] == []
    assert {p["param"] for p in b["params"]} >= {"metric.lx", "metric.lz", "metric.power"}
    assert "兜底" in b["note"]


def test_上屏文案干净_没有被禁的连接符与_markdown_标记(client):
    """spec §8.5 禁的三种连接符（中点元信息串 / 带空格的破折号 / 箭头）与
    会漏成字面字符的 markdown 标记（`**` 星号、`` ` `` 反引号），只许出现在
    注释与 docstring 里；随响应体上屏的纯文本必须干净。

    ⚠️ 这条同时盯 `_params` 与 `_fallback_params` 两份文案 —— 「固定 1.0…」那句
    两边各有一份，只测一份会漏掉另一份。
    """
    from api.routes.calibration import _fallback_params
    from tfield.pipeline import PipelineConfig

    b = client.get("/api/calibration").json()
    rendered = [b["note"], b["reason"] or "", b["ab_note"], b["lz_note"] or ""]
    rendered += [p["note"] for p in b["params"]]
    rendered += [p["note"] for p in _fallback_params(PipelineConfig.fallback())]
    for s in rendered:
        for bad in ("——", "**", "`", " · ", "→", "↳"):
            assert bad not in s, f"上屏文案里出现了被禁的 {bad!r}：{s!r}"


# ── 两个出口：页① 认文件，模型认训练段 ──


def test_页1_仍然报整份文件(client):
    """`/api/dataset` 认的是**用户交进来的那个文件**。

    绝不能改成训练段：那样它会报「宽表 1164 × 52」却带着
    `fix.n_rows == 1308`、`fixed_indices` 五个序号 —— 一份自相矛盾的凭证，
    而这一页的全部职责就是出一份自洽的凭证。
    """
    b = client.get("/api/dataset").json()
    assert b["n_times"] == 1308
    assert b["fix"]["n_rows"] == 1308
    assert b["time_end"] == "2026-07-27T23:55:00"


def test_模型认的是训练段():
    from api import deps
    from tfield.data.loader import HOLDOUT_CUTOFF, derived_signature
    full = deps.get_dataset()
    train = deps.get_train_dataset()
    assert len(train.wide) == 1164
    assert train.signature == derived_signature(full.signature, HOLDOUT_CUTOFF)
    assert train.fix == full.fix
    live = deps.get_live_frames()
    assert len(live) == 144
    ts = pd.to_datetime(live[C.COL_TIMESTAMP])
    assert bool(ts.is_monotonic_increasing)


def test_管线用的是训练段(monkeypatch):
    """管的线是**训练段** fit 出来的 —— 与页① 报的那份文件不是同一个世界。"""
    from api import deps
    seen = {}
    real = deps._build_pipeline

    def spy(ds, groups, bundle):
        seen["n"] = len(ds.wide)
        seen["sig"] = ds.signature
        return real(ds, groups, bundle)

    monkeypatch.setattr(deps, "_PIPELINES", deps.PipelineCache(builder=spy))
    deps.get_pipeline()
    assert seen["n"] == 1164
    assert "-h20260727T1200" in seen["sig"]



@pytest.fixture(autouse=True)
def _current_dataset():
    """空态成为默认之后，这个文件也必须**显式声明**它测的是哪一份数据集。

    2026-10-06 起，「当前在用哪一份数据集」是一个进程级的模块变量，启动时为空
    （规格书 §1.1 的空态）。不声明的话，这个模块里凡是碰数据集的用例都会拿到 409，
    而报错位置离现场很远。

    写成 autouse 而不是改各文件形状各异的 `client` 夹具，是因为本仓还有 **6 处**
    在测试里**内联**建 `TestClient(create_app())`（test_api.py ×2、
    test_api_train.py ×3、test_deps.py ×1）—— 它们同样要碰数据集，
    而只改 `client` 夹具会漏掉它们。一段代码、12 个文件、一模一样。
    """
    from api import deps, paths
    deps.set_current_dataset(paths.dataset_path())
