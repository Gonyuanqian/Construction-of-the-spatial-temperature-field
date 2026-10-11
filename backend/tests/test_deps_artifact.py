"""`_build_pipeline` 装上成品；装不动时回落现训，并把理由带到屏上。

⭐ 判「装回来了」与「现训了一遍」用的是**数**，不是计数：成品里的趋势换成一个
**常数桩**（现训出来的是棵树，给不出 999.0 这个数）。桩定义在模块层是为了能被
pickle —— 定义在函数里的类存不进字节、也装不回来。

⚠️ 要一个活着的 MySQL（独立库 `tfield_models_test`，由
`tests/conftest.py::_pin_test_library` 钉住）。连不上时**不 skip**。

⚠️ **每一格要自己把库里清空**（`clean_library`）—— 这个文件要数是第几行、
`current_id` 是谁，所以它**不**请求 `current_model`（与
`test_api_models.py` 开头那段注释同一个理由）。
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from pymysql.err import OperationalError

import conftest
from api import deps, jobs, paths
from tfield.artifact import FORMAT_VERSION, MAGIC
from tfield.features import build_features
from tfield.pipeline import FieldPipeline

#: 一棵**很小**的树。它只为一件事存在：让「回落现训」那条路秒级跑完 ——
#: 交付包自带的那套参数一训就是十几秒，而这条用例要在一次运行里训好几遍。
TINY_TREND = {"n_estimators": 1, "max_depth": 1, "learning_rate": 0.1}

CONST = 999.0


class _ConstantTrend:
    """成品里的趋势桩：**常数**。判别全靠它。"""

    def __init__(self, v: float = CONST) -> None:
        self.v = float(v)

    def predict(self, X) -> np.ndarray:
        return np.full(len(X), self.v)


def tiny_bundle():
    """一份**很小**的交付包（参数换成小树）。"""
    return dataclasses.replace(conftest.delivered_train_bundle(),
                               trend_params=dict(TINY_TREND))


@pytest.fixture()
def ds(delivered_bundle):
    """当前数据集，并把指针指着它。

    `delivered_bundle` 保证盘上有数据集、也有那份交付包；`install_dataset`
    顺手清一次管线缓存 —— 它就是把「清缓存 + 改指针」合成一个入口的那一支。
    """
    deps.install_dataset(paths.dataset_path())
    return deps.get_train_dataset()


@pytest.fixture()
def clean_library(models_db):
    """空库。**每一格清一次**，理由见模块 docstring。"""
    conn = models_db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM model")
        conn.commit()
    finally:
        conn.close()
    return models_db


@pytest.fixture()
def fresh_cache(monkeypatch):
    """换一个空的管线缓存。

    `deps._PIPELINES` 是**模块级**的，跨用例活着。键是
    `(ds.signature, groups_sig, bundle.created_at)`，而本文件几条用例用的是
    **同一份交付包** —— 不换缓存，第二条用例会命中第一条留下的管线，
    成品根本没被读过，而用例照样绿。这就是「测试骗过自己」的样子。
    """
    monkeypatch.setattr(deps, "_PIPELINES", deps.PipelineCache())
    return deps._PIPELINES


@pytest.fixture(autouse=True)
def _isolated():
    """每一格都从「手上没有残留的 job」开始。**不是可选的。**

    `jobs._CURRENT` 是**模块级**的，跨文件活着。而 `current_bundle()` 的第 1 档
    （「刚跑完还没入库的那一份」）压在库里那一份**上面** —— 上一份文件留下的
    DONE job 会跨用例压着本文件种的那一行，于是 `test_没有成品时照常现训`
    拿到的是**它的**趋势（交付包那棵大树，不是小树），红起来的样子像成品
    那一路写错了。`test_api_models.py:45-59` 与本仓
    `test_deps_current_bundle.py:60` 都有同一个夹具，同一个理由。

    `deps.reset_cache()` 一起清：数据集缓存与管线缓存都是模块级的。
    """
    jobs.clear()
    deps.reset_cache()
    yield
    jobs.clear()


def refit(ds) -> FieldPipeline:
    """用同一套小树参数现训一遍，当参考。"""
    cfg = tiny_bundle().config()
    return FieldPipeline(cfg, ds).fit(build_features(ds, cfg.feature_groups), ds)


def trend_at(pipe) -> np.ndarray:
    """两个点 × 两个时刻的趋势值。"""
    pts = np.array([[0.5, 5.0, 1.0], [1.2, 9.0, 0.4]])
    return pipe.trend_at_coords(pts, np.array([0, 3]))


def test_有成品时走装回来_不是现训(clean_library, ds, fresh_cache):
    """⭐ 主断言。成品里的趋势是**常数桩**；现训出来的是棵树，给不出 999.0。"""
    ref = refit(ds)
    raw = dataclasses.replace(ref.capture(), trend=_ConstantTrend()).to_bytes()
    clean_library.save_model("带成品的一份", tiny_bundle(), ds,
                             paths.dataset_path().name, artifact=raw)

    got = deps.get_pipeline()
    got_trend = trend_at(got)
    assert (got_trend == np.full((2, 1), CONST)).all(), (
        f"装回来的应当是成品里那个常数；实际 {got_trend.ravel().tolist()}，"
        "说明它走的是现训那条路")
    assert (trend_at(ref) != np.full((2, 1), CONST)).any(), (
        "现训出来的要是 999.0，这条用例就什么都判不了")
    # 残差是**从当前数据现算**的，成品里一个字节都没有（`tfield/artifact.py`
    # 的模块 docstring：IDW 是精确插值，存了残差就会把 A 的实测温度搬到 B 的
    # 测点上，还长得毫无破绽）。所以这里只能钉「算得出来、形状对、是有限数」——
    # **不能**钉它等于 `ref` 的残差：`got` 的趋势是 999.0 那个常数桩，
    # `y - 999.0` 与 `y - 树` 本来就不该相等。
    # 「装回来的残差与当场 fit 逐位相等」由 **Task 2** 的
    # `test_成品装回来与当场fit逐位相等` 钉着 —— 那里两侧用的是同一套配置。
    got_resid = got.residual_matrix()
    assert got_resid.shape == ref.residual_matrix().shape, (
        "残差矩阵的形状只由**当前**数据决定，成品的趋势换了它也不该变")
    assert np.isfinite(got_resid).all(), "残差里出现了 inf/nan"


def test_成品是坏字节时回落现训_并把理由写在管线上(clean_library, ds, fresh_cache):
    ref = refit(ds)
    clean_library.save_model("坏成品的一份", tiny_bundle(), ds,
                             paths.dataset_path().name, artifact=b"\x00" * 64)

    got = deps.get_pipeline()
    assert (trend_at(got) == trend_at(ref)).all(), "坏成品时给的应当是现训的数"
    assert got.calibrated is True, "包是在的 —— 回落的是成品，不是标定"
    assert got.artifact_note, "回落了却一个字不说，屏上只会看到它慢了十几秒"
    assert "——" not in got.artifact_note, "屏上文案禁用破折号"
    assert got.mismatch_note == "", "这一份是为当前数据标的，不该自称「借来的」"


def test_版本不对与字节坏了是两句不同的话(clean_library, ds, fresh_cache):
    """⭐ 规格书 D7/D8：两种错分得开，屏上才是两句不同的话。"""
    good = refit(ds).capture().to_bytes()
    bad_ver = (MAGIC + (FORMAT_VERSION + 1).to_bytes(4, "big")
               + good[len(MAGIC) + 4:])

    notes = []
    for i, raw in enumerate((bad_ver, b"\x00" * 64)):
        conn = clean_library.connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM model")
            conn.commit()
        finally:
            conn.close()
        # ⚠️ 两轮的包要**互不相同**（这里换 `created_at`）。管线缓存键的第三格
        # 就是它：两轮若用同一份包，第二轮会命中第一轮留下的管线 ——
        # 于是它报的还是第一轮那句话，而这条用例正好是判别两句话的，
        # 它会以一个**看起来像实现写错了**的样子红。
        # 换 `created_at` 也正是线上的样子：一份成品与它的包是**同一条
        # INSERT** 写进去的（`models_store.save_model`），成品不同、包必不同。
        clean_library.save_model("一份", dataclasses.replace(
            tiny_bundle(), created_at=f"第 {i} 刻标出来的"), ds,
            paths.dataset_path().name, artifact=raw)
        notes.append(deps.get_pipeline().artifact_note)

    assert "第 2 版" in notes[0], f"版本不对该报版本：{notes[0]!r}"
    assert "坏" in notes[1], f"字节坏了该说坏了：{notes[1]!r}"
    assert notes[0] != notes[1], "两种错不该是同一句话"


def test_没有成品时照常现训_且一个字不说(clean_library, ds, fresh_cache):
    """没成品**不是错**：老库里的行、或者 `artifact` 列刚加上时的行都长这样。
    屏上不该因此多一句话 —— 说「没有成品」而用户从没听说过「成品」，
    只是在报一个内部阶段名。
    """
    ref = refit(ds)
    clean_library.save_model("没成品的一份", tiny_bundle(), ds,
                             paths.dataset_path().name)
    got = deps.get_pipeline()
    assert (trend_at(got) == trend_at(ref)).all()
    assert got.artifact_note == ""


def test_同一份数据重训出来的另一份_不拿库里那一行的成品(clean_library, ds):
    """⭐ 这条钉的是 `_artifact_of` 的**判据本身**。

    「刚跑完还没保存」的那一份与库里那一行，`dataset_sig` 与 `groups_sig`
    **完全相等**（同一份数据、同一组特征）。拿这两列当身份判据，装上的会是
    **上一次**的模型 —— 而屏上没有一个字会提示。只有 `created_at` 分得开它们。
    """
    clean_library.save_model("库里那一份", tiny_bundle(), ds,
                             paths.dataset_path().name, artifact=b"TFART\x00")
    other = dataclasses.replace(tiny_bundle(), created_at="另一刻标出来的")

    assert other.dataset_sig == tiny_bundle().dataset_sig, "前提：这两列确实相等"
    assert other.groups_sig == tiny_bundle().groups_sig, "前提：这两列确实相等"
    assert other.created_at != tiny_bundle().created_at, "前提：只有这一刻不同"

    assert deps._artifact_of(other) == (None, ""), (
        "手上这份包不是库里那一行，就该现训 —— 拿 dataset_sig 判会装错模型")


def test_库里那一行的包读不动时当没有成品_不在这里报(clean_library, ds):
    """⭐ Review Focus 4。为了取成品，这条路比今天**多读一次库里的包**，
    而「刚跑完还没保存」那一档**从来没有读过库** —— 读一处旧代码从没碰过的
    地方，不该把好用的请求变成 500。

    ⚠️ 这条直接验 `_artifact_of` 的守卫，不绕 jobs 那套机具：它要证的正是
    「读库那一步失败时不抛」。
    """
    clean_library.save_model("包里是坏 JSON 的一份", tiny_bundle(), ds,
                             paths.dataset_path().name, artifact=b"TFART\x00")
    conn = clean_library.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE model SET bundle = %s", ("{ 这不是 JSON",))
        conn.commit()
    finally:
        conn.close()

    # 手上这份包「不是库里那一行」→ 会走到读库比对那一步，而读库就在这一步炸
    other = dataclasses.replace(tiny_bundle(), created_at="另一刻标出来的")
    assert deps._artifact_of(other) == (None, ""), (
        "库里那一行读不动，该当「这一条没有成品」，不是抛")


def test_库自己读不动时_这一路也不许抛(clean_library, ds, fresh_cache, monkeypatch):
    """⭐ Review Focus 4 的**另一半**：多读的那一次库，它**自己**可能读不动。

    「刚跑完还没保存」那一档（`current_bundle` tier 1）到今天为止**完全不读库**
    —— 那正是 MySQL 挂掉时构场仍能出图的原因。为了取成品，`_artifact_of` 多读了
    两处库；只要它们抛出，屏上本来是好的请求就变成 500。上一条挡的是「库里那一行
    的**包里**是坏数据」，这一条挡的是「**库这层**读不动」，两种都在这条路上。

    ⚠️ 打的是真错号（2003 连不上），不是随便一个异常：这条守卫要挡的正是这一种。
    """
    orig_id = deps.models_store.current_id
    clean_library.save_model("库里那一份", tiny_bundle(), ds,
                             paths.dataset_path().name, artifact=b"TFART\x00")
    other = dataclasses.replace(tiny_bundle(), created_at="另一刻标出来的")

    def boom():
        raise OperationalError(2003, "Can't connect to MySQL server")

    # ① 认「当前那一行」那一步
    monkeypatch.setattr(deps.models_store, "current_id", boom)
    assert deps._artifact_of(other) == (None, ""), (
        "current_id 抛出时该当「这一条没有成品」，不是把请求变成 500")
    monkeypatch.setattr(deps.models_store, "current_id", orig_id)

    # ② 取成品字节那一步。**必须**用与库里那一行 `created_at` 相等的包才走得到它
    monkeypatch.setattr(deps.models_store, "artifact_of", boom)
    assert deps._artifact_of(tiny_bundle()) == (None, ""), (
        "artifact_of 抛出时该当「这一条没有成品」，不是把请求变成 500")


def test_借来的那一份_两句话各在各的格子里(clean_library, ds, fresh_cache):
    """⭐ Review Focus 5。两件事会**同时**成立：这一份包不是为当前数据标的
    （`mismatch_note`），而且它的成品读不动（`artifact_note`）。

    载荷里 `mismatch_note` 原来只有**一个格**，而前端
    `copy.ts:225` 的 `calibratedLabel` 是**用「格子里有没有话」**判
    「已标定（借来的）」的。把成品的理由塞进同一格，就会出现两种错，方向相反：
    合成一句、写进 `mismatch_note` → 一份本地模型自称「借来的」；
    合成一句、写进 `artifact_note` → 「借来的」那句**没了**，用户以为这份参数
    是他自己数据标出来的。两句话都在、且不是同一句，才是对的。

    ⚠️ 行与包必须**一起**换成「借来的」：`save_model` 把 `bundle.dataset_sig`
    抄进行里，所以造一份换了签名的包就够了（`test_deps_current_bundle.py::_other_bundle`
    同一条理由 —— 只改一处会造出线上不可能出现的「行说 A、包说 B」）。
    """
    borrowed = dataclasses.replace(tiny_bundle(),
                                   dataset_sig="别的数据集那一份的指纹")
    assert borrowed.dataset_sig != ds.signature, "前提：这一份得真的是借来的"

    clean_library.save_model("借来的一份", borrowed, ds,
                             paths.dataset_path().name, artifact=b"\x00" * 64)

    got = deps.get_pipeline()
    assert got.mismatch_note == deps._BORROWED_NOTE, "「借来的」那一句没了，来历说反了"
    assert got.artifact_note, "成品读不动那一句没了，屏上只会看到它慢了十几秒"
    assert got.mismatch_note != got.artifact_note, "两件事两句话，不是同一句"
