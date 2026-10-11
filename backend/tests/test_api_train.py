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

import conftest                                          # noqa: E402
from api import deps, models_store, paths, routes        # noqa: E402
from api.main import create_app                          # noqa: E402
from tfield import config as C                           # noqa: E402
from tfield.calibration import IDW_SPACE, TREND_SPACE, TUNED_KEYS   # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _library(current_model):
    """这一整个文件都要求模型库里存着交付那一份模型（见 `tests/conftest.py`）。

    2026-10-08 起「用哪一份模型」唯一的来路是模型库，而本文件大多数用例要
    断言包里的数（`created_at` 2026-10-05T13:52:09+00:00、`groups_sig`
    d6294c09、八折、A/B 两组的 MAE）。库里空着的话它们拿到的是**兜底参数**
    那一份 —— 红绿还在、测的东西换了，而没有一个字提示。要空态的那几条
    自己标 `@pytest.mark.empty_library`。

    写成 autouse 而不是给每条用例加参数：本文件有 **3 处**内联
    `TestClient(create_app())`，逐个加参数必漏（与本文件 `_current_dataset`
    那条同一个理由）。
    """
    return current_model


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
    # 第三档：库里的那一份**就是为这个训练段标的**（`library_module` 种的就是
    # 交付那一份），所以「借来的」那句话是空串，而不是缺这个键。
    assert b["source"] == "library"
    assert b["mismatch_note"] == "", b["mismatch_note"]
    # 与旧包（2026-10-03 那一份）的数不可直接比大小：同折族、不同参数。
    # 换口径重标过（留出段 2026-07-27 12:00 起 144 帧只在训练段上标定）。
    assert b["created_at"] == "2026-10-05T13:52:09+00:00"
    assert b["tool_version"] == "0.1.0"
    assert b["groups_sig"] == "d6294c09"
    assert b["feature_groups"] == list(C.DEFAULT_FEATURE_GROUPS)
    assert b["n_folds"] == 8 and b["fold_kind"] == "position"
    assert len(b["metrics"]) == 8 and len(b["per_point"]) == 24

    # 面板：**一套值，两条来路**（规格书 §3.1）—— 「从哪些值里挑」与
    # 「挑出来是多少」现在是同一行的两列，不再是上下两张表。
    panel = b["panel"]
    rows = panel["trend"] + panel["idw"]
    # 屏上次序 = XGBoost 八个在前、IDW 四个在后；两组之内各按 `TUNED_KEYS` 的
    # 次序。⚠️ `TUNED_KEYS` 把 IDW 那四个排在前面，所以不能拿整个它直接比 ——
    # 要按屏上那个「先 trend 后 idw」的分组各取一次。
    assert [r["key"] for r in rows] == (
        [k for k in TUNED_KEYS if k.startswith("trend.")]
        + [k for k in TUNED_KEYS if not k.startswith("trend.")]), "次序即屏上次序，前端不排"
    assert all(set(r) == {"key", "label", "values", "raw", "current"} for r in rows)
    assert len(panel["trend"]) == 8 and len(panel["idw"]) == 4
    by_key = {r["key"]: r for r in rows}
    assert by_key["metric.power"]["current"] == 0.5
    assert by_key["cross_shed"]["current"] is False       # 布尔必须仍是布尔
    # 三列同下标：印出来的是 `values[i]`，要发回去的是 `raw[i]`
    for r in rows:
        assert len(r["values"]) == len(r["raw"])
        assert r["current"] in r["raw"]


def test_面板每一维都报得出候选值(client):
    """`_SPACE_KEY` 漏一条，那一维的候选就是空的 —— 屏上那个滑块没有档。

    ⚠️ 这条原来叫「每个调过的参数都报得出它的搜索空间」，盯的是
    `tuned_keys` 里那个 `space` 字串。**它防的东西没变**（映射漏一条就露馅），
    只是判据从「那一列不是『—』」换成了「`raw` 至少两档」——
    后者更硬：一个空的候选数组连一个字符都印不出来。
    """
    b = client.get("/api/calibration").json()
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    thin = [r["key"] for r in rows if len(r["raw"]) < 2]
    assert thin == [], f"这些参数没有可挑的候选值：{thin}"

    by_key = {r["key"]: r for r in rows}
    # 印法硬写两条：两个循环两边都过 `fmt_value`，光靠它们看不出口径被换成
    # `str()` —— 而 `1.0` 上屏必须是 `1`（`%g`），不是 `1.0`。
    assert by_key["metric.power"]["values"] == ["0.5", "1", "1.5", "2", "2.5", "3", "4"]
    assert by_key["trend.subsample"]["values"] == ["0.7", "0.85", "1"]
    # 布尔印成「开」「关」，不是 True / False
    assert by_key["cross_shed"]["values"] == ["开", "关"]
    assert by_key["cross_shed"]["raw"] == [True, False]


def test_逐折与逐点是标定包里的原数_不是现算的(client):
    """页② 显示的性能数字必须**逐位等于包里那一份**。

    重新评估一遍会得到一个略微不同的数（同样的折、同样的参数，浮点求和顺序不同），
    于是页面上的数与盘上包里的数对不上 —— 验收对盘时这是最尴尬的一种错。
    """
    import json

    b = client.get("/api/calibration").json()
    # ⚠️ **必须取训练段那一份**：路由报的是按训练段标出来的那个包。拿**整份文件**
    # 那一份（`conftest.delivered_full_bundle()`）来比会变成「拿 A 包的数比 B 包的
    # 数」—— 它想守的「页面上的就是盘上那一份」一个字都没验到，却仍然是绿的。
    # **这就是它上一轮红的原因。**
    bundle = conftest.delivered_train_bundle()

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

    # 整份文件那一份包就够：这条要的只是一张**真**的逐折表，好挑一折把它改成 NaN。
    bundle = conftest.delivered_full_bundle()

    # 改的是**内存里的副本**，盘上的包一个字节都不动
    metrics = bundle.metrics.copy(deep=True)
    bad_fold = str(metrics.loc[0, "fold"])
    metrics.loc[0, "mae"] = float("nan")
    broken = dc_replace(bundle, metrics=metrics)

    # ⚠️ 接口点从 `cal_routes.load_for` 换成了 `deps.current_bundle`（2026-10-08
    # 模型库那一轮）：路由不再自己读盘，而是问「这次用哪一份模型」那一个出口。
    # 补 `cal_routes.load_for` 现在是 `AttributeError` —— `calibration.py` 里
    # 已经没有这个名字了。
    monkeypatch.setattr(deps, "current_bundle",
                        lambda *a, **k: deps.CurrentBundle(bundle=broken,
                                                           source="library"))
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

    # 同上：整份文件那一份包，要的只是一张真的逐折表。
    bundle = conftest.delivered_full_bundle()
    metrics = bundle.metrics.copy(deep=True)
    metrics["mae"] = float("nan")
    broken = dc_replace(bundle, metrics=metrics)

    # 接口点同 `test_某一折_mae_是_NaN_时…`：`cal_routes.load_for` 已退役。
    monkeypatch.setattr(deps, "current_bundle",
                        lambda *a, **k: deps.CurrentBundle(bundle=broken,
                                                           source="library"))
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
    """从**响应本身**读 lz 的搜索空间（`panel.idw` 里 `metric.lz` 那一行的 `values`）。

    不另去盘上加载标定包：这一条要验的是「响应里的值与响应里的空间对得上」，
    空间也必须从响应里来 —— 换成从包里读，测的就不是这一页了。
    """
    row = next(r for r in b["panel"]["idw"] if r["key"] == "metric.lz")
    assert row["values"], "lz 报了值却没报候选值，_lz_space 无从取起"
    return [float(v) for v in row["values"]]


def test_lz_落在搜索下界时要自己说出来(client):
    """**规则**：lz 踩在搜索下界 ⟺ `lz_note` 有话说。两头都要成立。

    不钉「本项目正好踩在下界」—— 那是**某一份标定包**的性质，换一次标定就没了
    （换成训练段重标之后 lz 从 0.005 挪到 0.03，旧写法当场失效）。
    钉规则是因为两个方向都是错：踩在下界不吭声，是把「没扫够」说成「已收敛」；
    没踩下界却发警告，是狼来了，警告多了就没人看了。
    """
    b = client.get("/api/calibration").json()
    lo = min(_lz_space(b))
    # 当前值同样**从响应来**：`panel` 里 `metric.lz` 那一行的 `current`
    # （原先是 `params` 里的 `value` 字串；两张表已并成一张）。
    lz = next(r["current"] for r in b["panel"]["idw"] if r["key"] == "metric.lz")
    at_bound = lz == lo
    if at_bound:
        assert b["lz_note"] is not None, "lz 贴着搜索下界时必须有提示，不许静默"
        assert "搜索下界" in b["lz_note"]
    else:
        assert b["lz_note"] is None, (
            f"lz = {lz:g} 不在下界 {lo:g} 上，不该发「还没扫够」的警告")


@pytest.mark.empty_library
def test_没有标定包时也要答得出来():
    """空状态是行动的邀请，不是一片空白（spec §8.5）。

    没有包时界面要能显示**兜底参数**，并明说它不是最优。

    ⚠️ 空态现在由**模型库里没有当前模型**造出来（`empty_library` 标记），
    不再是「把 `CONFIGS_ROOT` 指到一个空目录」—— `present` 已经不问盘了，
    指着空目录也是空转：用例照旧拿到库里那一份，而它断言的每一句都在测
    另一条路。
    """
    c = TestClient(create_app())
    b = c.get("/api/calibration").json()

    assert b["present"] is False
    assert b["reason"] and "标定" in b["reason"]
    assert b["metrics"] == [] and b["per_point"] == []
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    assert {r["key"] for r in rows} >= {"metric.lx", "metric.lz", "metric.power"}
    assert "兜底" in b["note"]


def test_上屏文案干净_没有被禁的连接符与_markdown_标记(client):
    """spec §8.5 禁的三种连接符（中点元信息串 / 带空格的破折号 / 箭头）与
    会漏成字面字符的 markdown 标记（`**` 星号、`` ` `` 反引号），只许出现在
    注释与 docstring 里；随响应体上屏的纯文本必须干净。

    ⚠️ 这条原来同时盯 `_params` 与 `_fallback_params` 两份文案 —— 这两个函数
    已退役，`_LABELS` / `_FIXED` 成了**唯一**一份（有包与空态共用），所以两份
    文案分家的坑消失了。但两条路仍要**各自**跑一遍：上面这条走 `bundle`，
    下面那条走 `cfg`。
    """
    b = client.get("/api/calibration").json()
    rendered = [b["note"], b["reason"] or "", b["ab_note"], b["lz_note"] or ""]
    rendered += [f["note"] for f in b["panel"]["fixed"]]
    rendered += [r["label"] for r in b["panel"]["trend"] + b["panel"]["idw"]]
    # ⚠️ `values` 也要扫：它是**新出现的一族上屏文字**（旧测试扫的 `space.*.values`
    # 正是它）。`fmt_value` 现在吐的是 `%g` 数字与「开」「关」，今天一个都不会红 ——
    # 但 `objective` 那一维吐的是库里的字符串（`reg:squarederror` 这种），
    # 库要是换了印法，这里是唯一会当场说话的地方。
    rendered += [v for r in b["panel"]["trend"] + b["panel"]["idw"] for v in r["values"]]
    for s in rendered:
        for bad in ("——", "**", "`", " · ", "→", "↳"):
            assert bad not in s, f"上屏文案里出现了被禁的 {bad!r}：{s!r}"


# 空态那一份（没有包时走的是 `PipelineConfig.fallback()`，与上面的包**不是**
# 同一个来源），标签与固定值必须与有包时逐字相同。
@pytest.mark.empty_library
def test_空态的上屏文案也干净():
    b = TestClient(create_app()).get("/api/calibration").json()
    rendered = [r["label"] for r in b["panel"]["trend"] + b["panel"]["idw"]]
    rendered += [v for r in b["panel"]["trend"] + b["panel"]["idw"] for v in r["values"]]
    rendered += [f["label"] + f["value"] + f["note"] for f in b["panel"]["fixed"]]
    for s in rendered:
        for bad in ("——", "**", "`", " · ", "→", "↳"):
            assert bad not in s, f"空态的上屏文案里出现了被禁的 {bad!r}：{s!r}"


# ── 待优选参数清单（规格书 §三）──

@pytest.mark.empty_library
def test_面板在没有包时也在():
    """T1：面板是**模块常量加兜底值**，与库里有没有模型无关。

    只在有包时才给 = 逼用户先跑一次才知道要调什么，而 §三 那个「先」字
    说的正是「点之前就在屏上」。空态是唯一能验这一条的地方。
    """
    c = TestClient(create_app())
    b = c.get("/api/calibration").json()
    assert b["present"] is False
    assert len(b["panel"]["trend"]) == 8 and len(b["panel"]["idw"]) == 4
    assert {r["key"]: r["current"] for r in b["panel"]["trend"] + b["panel"]["idw"]}[
        "metric.power"] == C.FALLBACK_POWER


def test_面板与库的搜索空间一一对应(client):
    """T1：面板**从 `TUNED_KEYS` 与两个空间生成**，不是另抄一份。

    ⚠️ 写死 8 与 4 是有意的：只断言 `len(panel["trend"]) == len(TREND_SPACE)`
    是拿同一个来源比自己，等于没测。8 与 4 是规格书 §3.1 明写的数，
    XGBoost 八个（含 objective）、IDW 四个。
    """
    from api import ported

    b = client.get("/api/calibration").json()
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    assert sorted(r["key"] for r in rows) == sorted(TUNED_KEYS)
    assert len(b["panel"]["trend"]) == 8 and len(b["panel"]["idw"]) == 4

    by = {r["key"]: r["values"] for r in rows}
    for k, vals in TREND_SPACE.items():
        assert by[f"trend.{k}"] == [ported.fmt_value(v) for v in vals]
    for k in ("power", "lx", "lz"):
        assert by[f"metric.{k}"] == [ported.fmt_value(v) for v in IDW_SPACE[k]]


def test_固定值不进面板但仍有它的那一行(client):
    """T2：ly 恒为 1.0、从未进过搜索空间，所以它**不做成控件** ——
    一个拖不动的滑块比一句话更容易让人以为是自己没点对（规格书 §2.3）。

    ⚠️ 它防的还是原来那件事：把 ly 列进「待优选」是谎报调参范围。
    判据从「不在 not keys 里」变成「不在 panel 里」，**更硬**：
    panel 是唯一的来源，漏进去就是屏上多一个滑块。
    """
    b = client.get("/api/calibration").json()
    keys = [r["key"] for r in b["panel"]["trend"] + b["panel"]["idw"]]
    assert "metric.ly" not in keys

    fixed = {f["key"]: f for f in b["panel"]["fixed"]}
    assert "metric.ly" in fixed
    assert "从未进过搜索空间" in fixed["metric.ly"]["note"]
    assert fixed["metric.ly"]["value"] == "1"


def test_面板的标签表与调参键一一对应(client):
    """面板上每一维都印着中文名 —— 它现在是控件的标签（规格书 §2.1）。

    `_LABELS` 是一张**显示名**表，不是第二份「要搜什么」（候选值一律由
    两个空间现取）。它唯一会错的方式是「库加了一个参数而它没跟」，
    那时 `_LABELS[key]` 会抛 `KeyError`，接口当场 500 —— 这条就是钉那个。
    """
    b = client.get("/api/calibration").json()
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    # ⚠️ 右边**不能**写成 `list(TUNED_KEYS)`：`TUNED_KEYS` 是 IDW 四个在前，
    # 而屏上（也是这里）是 trend 八个在前，两者恒不相等。按屏上的分组各取一遍
    # 才是同一个意思，而且比 `sorted()` 更紧 —— 它还钉住了组内次序。
    assert [r["key"] for r in rows] == (
        [k for k in TUNED_KEYS if k.startswith("trend.")]
        + [k for k in TUNED_KEYS if not k.startswith("trend.")]
    )
    assert all(r["label"].strip() for r in rows), "有一维没有标签"


def test_面板每一维的当前值都不是空的(client):
    """当前值读的是包的 `trend_params` / `metric`。**哪一维读不到，屏上就是
    `None` 或 `undefined`** —— 而对 `fmt_value` 来说 `None` 是合法输入，
    它会老老实实印出 `None` 三个字母，不抛错。
    """
    b = client.get("/api/calibration").json()
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    empty = [r["key"] for r in rows if r["current"] is None]
    assert empty == [], f"这些维度读不出当前值：{empty}"


@pytest.mark.empty_library
def test_空态面板十二维的当前值都在候选里():
    """**没包那条路**也要十二维齐全，而且当前值都得是屏上的一档。

    上面两条用的是有包的 `client` 夹具，于是空态整个漏在网外 —— 而空态正是
    页② 打开时的样子（「点之前就在屏上」，规格书 §三）。兜底配置
    `FALLBACK_TREND_PARAMS` 只带七维，剩下五维若没人补，`_current` 会返回
    `None`：`fmt_value(None)` 印成 `"None"`（一个英文单词落在中文面板上），
    又不落进 `raw`，前端那个按下标定位的滑块一格都不选中。
    """
    c = TestClient(create_app())
    b = c.get("/api/calibration").json()
    assert b["present"] is False
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    assert len(rows) == 12
    empty = [r["key"] for r in rows if r["current"] is None]
    assert empty == [], f"空态下这些维度读不出当前值：{empty}"
    stray = [r["key"] for r in rows if r["current"] not in r["raw"]]
    assert stray == [], f"空态下这些维度的当前值不在候选里：{stray}"
    # 兜底值必须是**真档位**，不是被 `_legal_values` 现并进去的 —— 并进去的
    # 值同样满足 `current in raw`，所以上面那条抓不到它。这里对着库里的档位
    # 单子逐个点一遍（**字面量**：拿 `_candidates` 与响应比会掉进「拿被测函数
    # 跟自己比」的恒真陷阱）。一个非法值会让 `raw` 多出一格，当场红。
    by = {r["key"]: r for r in rows}
    assert by["trend.min_child_weight"]["raw"] == [1, 3, 5, 10]
    assert by["trend.subsample"]["raw"] == [0.7, 0.85, 1.0]
    assert by["trend.colsample_bytree"]["raw"] == [0.7, 0.85, 1.0]
    assert by["trend.reg_lambda"]["raw"] == [0, 1, 5]
    assert by["trend.objective"]["raw"] == [
        "reg:squarederror", "reg:absoluteerror", "reg:pseudohubererror"]
    assert routes.calibration._TREND_FALLBACK.keys() == (
        {k.partition(".")[2] for k in TUNED_KEYS if k.startswith("trend.")}
        - set(C.FALLBACK_TREND_PARAMS)
    ), "兜底表与「兜底配置缺的那几维」对不上了"


def test_包里缺了某一维也要落回默认值():
    """上面那条只管**没包**那一半；这一条管有包那一半。

    包是别的工具写的、或换过库版本时，`trend_params` 里可能少一维 ——
    那时 `_tuned_value` 走 `bundle.trend_params.get(tail)` 返回 `None`，
    屏上那个滑块没有对应的档；更糟的是 `_legal_values` 见到 `None` 就不并入，
    面板摆上屏的那个值发回来会被 `_validated_domain` 判 422 ——
    页② 第一次点「开始训练」就是死的，而那个值正是面板自己放上去的。

    喂假包的理由与 `test_当前值不在候选里时并进候选` 相同：真包永远是齐的，
    这一支走不到。
    """
    from types import SimpleNamespace

    from api.routes import calibration as cal_routes

    fake = SimpleNamespace(
        metric=SimpleNamespace(power=2.0, lx=2.0, ly=1.0, lz=0.12),
        trend_params={"max_depth": 4, "learning_rate": 0.08, "n_estimators": 300},
        cross_shed=False,
    )
    panel = cal_routes._panel(fake, None)
    rows = panel["trend"] + panel["idw"]
    assert len(rows) == 12
    empty = [r["key"] for r in rows if r["current"] is None]
    assert empty == [], f"包里缺的维度没有落回默认值：{empty}"
    stray = [r["key"] for r in rows if r["current"] not in r["raw"]]
    assert stray == [], f"这些维度的当前值不在候选里：{stray}"
    # 兜底值必须是**真档位**，不是被 `_legal_values` 现并进去的 —— 并进去的
    # 值同样满足 `current in raw`，所以上面那条抓不到它。这里对着库里的档位
    # 单子逐个点一遍（**字面量**：拿 `_candidates` 与响应比会掉进「拿被测函数
    # 跟自己比」的恒真陷阱）。一个非法值会让 `raw` 多出一格，当场红。
    by = {r["key"]: r for r in rows}
    assert by["trend.min_child_weight"]["raw"] == [1, 3, 5, 10]
    assert by["trend.subsample"]["raw"] == [0.7, 0.85, 1.0]
    assert by["trend.colsample_bytree"]["raw"] == [0.7, 0.85, 1.0]
    assert by["trend.reg_lambda"]["raw"] == [0, 1, 5]
    assert by["trend.objective"]["raw"] == [
        "reg:squarederror", "reg:absoluteerror", "reg:pseudohubererror"]


def test_面板的当前值都在候选里(client):
    """T12 的前半：`current` 必在 `raw` 里 —— 屏上那个滑块**一定有**对应的档。

    前端是按下标定位的（`row.raw.indexOf(values[key])`），所以这一条不是
    前端的好习惯，是**前端的正确性前提**：不成立时滑块停错档、旁边那个数
    印成空白，而屏上没有任何字会说这件事。

    ⚠️ 真包那条路上这一条**必然**成立（`_panel` 里那段「不在就并进去」）——
    所以它真正的价值是当那一段被谁删掉时当场变红。旧空间训练出来的包那一种
    由下面那条单独钉。
    """
    b = client.get("/api/calibration").json()
    rows = b["panel"]["trend"] + b["panel"]["idw"]
    stray = [r["key"] for r in rows if r["current"] not in r["raw"]]
    assert stray == [], f"这些维度的当前值不在候选里，屏上那个滑块没有对应的档：{stray}"

    # 三列同下标（`values[i]` 是印法，`raw[i]` 是要发回去的值）——
    # 这里再说一遍，因为它与上面那条是同一个不变式的两面。
    for r in rows:
        assert len(r["values"]) == len(r["raw"])


def test_当前值不在候选里时并进候选():
    """T12 的后半：包可能是拿**旧版**搜索空间训的，那时当前值不在今天的候选里。

    并进来，是为了让「屏上能选的就是后端列的」这条不变式在**后端**成立 ——
    前端因此不必为这件事写任何分支（见 `test_面板的当前值都在候选里` 那条的说明）。

    ⚠️ 为什么要喂假包：真包与今天的空间同版，这段合并代码在真数据上**走不到**。
    一条走不到的防线等于没有防线，所以这里用一个最小的假包把那一支逼出来。
    `_panel` 对包的全部要求就是 `_tuned_value` 读的那三处
    （`.cross_shed` / `.metric.<tail>` / `.trend_params`），`SimpleNamespace` 足够。
    """
    from types import SimpleNamespace

    from api.routes import calibration as cal_routes

    fake = SimpleNamespace(
        # 9.9 不在 `IDW_SPACE["power"]` 里；0 不在任何一个 trend 空间里。
        metric=SimpleNamespace(power=9.9, lx=1.0, ly=1.0, lz=0.03),
        trend_params={k.partition(".")[2]: 0
                      for k in TUNED_KEYS if k.startswith("trend.")},
        cross_shed=True,
    )
    panel = cal_routes._panel(fake, None)
    by = {r["key"]: r for r in panel["trend"] + panel["idw"]}

    power = by["metric.power"]
    assert power["current"] == 9.9
    assert 9.9 in power["raw"], "旧空间的当前值没有并进候选，屏上那个滑块没有档"
    assert power["raw"][-1] == 9.9, "并进来的当前值应当落在末尾（候选的次序不许被搅乱）"
    assert len(power["values"]) == len(power["raw"])

    depth = by["trend.max_depth"]
    assert depth["current"] == 0 and depth["raw"][-1] == 0

    # 已经在候选里的那些**一个都不许被动**：并进去是特例，不是常态。
    # ⚠️ 右边写**字面量**而不是 `_candidates("metric.lx")`：拿被测函数与它自己
    # 比，这条恒真，删掉那段合并逻辑它也照样绿。
    assert by["metric.lx"]["raw"] == [0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0]
    assert by["metric.lx"]["current"] == 1.0


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


# ── 换数据集之后的标定（规格书 §七）──

@pytest.mark.empty_library
def test_换了数据集之后报出上一次标定对的是谁(client, tmp_path, monkeypatch):
    """规格书 §七：`present=False` 那条路上要走两种处境分开。

    现在的 `NO_BUNDLE_REASON` 是「这一份数据集还没有标定包」——
    这句话在**换数据集之后**不够：它把
      · 这份数据集从来没标过（系统的正常起点），
      · 这份数据集是刚换上的，上一次标定对的是**另一份**数据，
    说成了一种。用户要看的是后一句。

    ⚠️ **这条用例的前提 2026-10-10 变过一次**（用户裁定「模型不绑数据集」）。
    在那之前，换数据集**必然**让 `present` 变 false —— 库里那一份的数据集签名
    对不上就被丢掉，所以「换数据集」这件事自己就把人送到这条路上，不用额外
    摆前提。现在库里那一份**照用**（特征组对得上就够），于是换数据集之后
    页② 会报 `present=true` + `source="library"` + 一句话说这是借来的
    （那一条由 `test_库里那一份是为别的数据标的时_页二照用并如实报出来` 钉着）。

    走 `present=false` 的**新前提**因此是「库里一份能用的都没有」——
    这正是 `@pytest.mark.empty_library` 在这里做的事（本文件那条 autouse
    `_library` 会经 `current_model` → `models_db` 清表，标了就不再种回去，
    与末尾那三条兄弟用例同一个手法）。**两条用例说的是两件事，不是同一条的
    新旧两版**：那条说「借来了也照用，但要说出来」，这条说「一份都没有时，
    页② 报得出上一次标定对的是哪一份数据」。

    ⚠️ 于是原先那句前提断言（「交付数据集有包 → `mismatch` 是 None」）也
    跟着不成立了：库一空，页② 对**交付数据集自己**就走 `present=false`，
    而 `_mismatch` 报的是盘上那些**别的数据集**的包（`configs/` 里那两份）。
    它要证明的东西（换数据集之前报的不是这一次）改由下面 `before` 那两行来证。
    """
    monkeypatch.setattr(paths, "UPLOADS", tmp_path / "uploads")
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()

    # 换之前先记下它报的是谁：库空着，所以这一格已经有值了。
    before = client.get("/api/calibration").json()
    assert before["present"] is False
    assert before["mismatch"] is not None      # 盘上有别人的包，只是没有这一份的

    # 换一份（同名不同路径 → 签名不同 → 没有一份包对得上）
    from tfield.data.loader import test_data_path
    r = client.post("/api/dataset/upload?name=另一份.xlsx",
                    content=test_data_path().read_bytes(),
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200, r.text

    body = client.get("/api/calibration").json()
    assert body["present"] is False
    m = body["mismatch"]
    assert m is not None
    assert m["dataset_sig"] != body["dataset_sig"]      # 上一次标的是**另一份**
    assert m["created_at"]
    assert m["file"].startswith("bundle_") and m["file"].endswith(".json")
    # 换数据集**换掉了这一页的答案**：新那份数据集的签名与旧的对不上，
    # 所以「上一次标定对的是谁」这句问话的答案也跟着换了主语。
    assert body["dataset_sig"] != before["dataset_sig"]

    # 收尾：把交付数据集装回去，别留给后面的模块
    deps.install_dataset(paths.dataset_path())


def test_库里那一份是为别的数据标的时_页二照用并如实报出来(client):
    """⭐ 2026-10-10 用户裁定：「只要是模型库中有模型，就能选择模型库中的任意
    一个模型来构建，而不是绑定数据集。」

    页② 那一屏数的是**包里那些数**（参数、A/B、逐折 MAE）—— 它照旧报，
    但要把「这一份不是为当前这份数据标的」说出来。屏上要是只印着这些数字
    而不提这一句，读的人会以为它们是这份数据的成绩。
    """
    ds = deps.get_train_dataset()
    # ⚠️ 合成的**为别的数据集标的**那一份（`conftest.bundle_for_another_dataset`），
    # 不是盘上排序第一的那一份 —— 盘上有没有别人的包取决于谁在这台机器上跑过
    # 标定，别人的克隆里没有。先确认它真的对不上，否则这一条白跑：拿一份对得上
    # 的包进来，「借来的」那句话本来就该是空串，红绿都不动。
    other = conftest.bundle_for_another_dataset()
    assert other.dataset_sig != ds.signature, "取到的是对得上的那一份，这条白跑"

    models_store.save_model("别人家标的", other, ds, "别人家的棚.xlsx")
    deps.reset_cache()

    b = client.get("/api/calibration").json()
    assert b["present"] is True, "用户点了它当当前模型，就该用它"
    assert b["source"] == "library"
    assert b["dataset_sig"] == other.dataset_sig, "报的不是用户点的那个模型"
    assert b["mismatch_note"] == deps._BORROWED_NOTE


@pytest.mark.empty_library
def test_从来没有标过的数据集_mismatch_是_null(client, monkeypatch, tmp_path):
    """反面的那一种：`configs/` 是空的 → 没有「上一次」，不许编一个出来。

    ⚠️ `mismatch` 只在 `present=false` 那条路上被算（`present=true` 时它恒为
    null）。所以这一条要**两个空**同时成立：`CONFIGS_ROOT` 空，模型库也空
    （`empty_library` 标记）。只空其中一个的话，`mismatch` 照样是 null ——
    而它 null 的原因是另一个，这条用例一个字都没验到。
    """
    monkeypatch.setattr(routes.calibration, "CONFIGS_ROOT", tmp_path)
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()
    body = client.get("/api/calibration").json()
    assert body["present"] is False
    assert body["mismatch"] is None
    # 没有模型时那句话是空串（不是缺键）：前端不必判两种空，与 `ModelRow.why`
    # 同一条房规。`mismatch` 那个字典说的是另一件事（盘上躺着的旧包）。
    assert body["mismatch_note"] == ""


@pytest.mark.empty_library
def test_configs_里有一份读不动的包_mismatch_要跳过它而不是把接口打挂(
        client, monkeypatch, tmp_path):
    """Review Focus 之外的第六类输入：`configs/` 里躺着半份包。

    `save_bundle()` 是 `write_text` —— 不是原子的。跑标定跑到一半 Ctrl-C，
    或者盘写满，都会留下一份**截断的 JSON**。它照样叫 `bundle_*.json`，
    照样会被 glob 到。

    期望：读不动的那一份**跳过**（说不清它标的是哪一份数据集，就不能替它说），
    剩下的照常挑。**不许把 `/api/calibration` 打成 500** —— 这一页的全部职责
    就是把口径说清楚，为一份读不动的文件整页报错，是把用户手里能用的东西
    也一起拿走了。
    """
    (tmp_path / "bundle_6145fa9261e89f1b_d6294c09.json").write_text(
        '{"dataset_sig": "6145fa9261e89f1b", "created_at": "2026-0', encoding="utf-8")
    monkeypatch.setattr(routes.calibration, "CONFIGS_ROOT", tmp_path)
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()

    r = client.get("/api/calibration")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["present"] is False
    assert body["mismatch"] is None


@pytest.mark.empty_library
def test_坏包旁边有一份好包时_照旧报出好包那一份(client, monkeypatch, tmp_path):
    """跳过坏的那一份，不等于整条路都不报 —— 好的那一份要说出来。

    ⚠️ 要空库，同上：库里只要有一份能用的当前模型，`present` 就是 true，
    `mismatch` 就是 null，下面那句 `assert m is not None` 会直接红 ——
    而它红起来的样子像「`_mismatch` 挑包挑错了」，离真正的原因很远。
    """
    from dataclasses import replace
    from tfield.calibration import save_bundle

    # 拿交付那份包改成「别的签名」再存回去。**不能用一份手写的两键 JSON**：
    # 那份东西 `from_dict` 会直接拒（它要 `search` 等字段），于是它落在
    # 「坏包」那一类里，这条测试就证不了「好包照旧报得出来」。
    real = conftest.delivered_train_bundle()
    save_bundle(replace(real, dataset_sig="别的签名"), root=tmp_path)
    (tmp_path / "bundle_截断的.json").write_text("{ 半份", encoding="utf-8")

    monkeypatch.setattr(routes.calibration, "CONFIGS_ROOT", tmp_path)
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()

    m = client.get("/api/calibration").json()["mismatch"]
    assert m is not None
    assert m["dataset_sig"] == "别的签名"
    assert m["created_at"] == real.created_at
    # 报出来的是好的那一份，不是坏的那一份
    assert m["file"].startswith("bundle_别的签名_")

