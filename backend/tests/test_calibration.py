from __future__ import annotations
import json
import pandas as pd
import pytest
from tfield import config as C
from tfield.calibration import (TOOL_VERSION, CalibrationAborted, CalibrationBundle,
                                SearchRecord, bundle_path, groups_signature, load_bundle,
                                load_for, new_bundle, run_calibration, save_bundle)
from tfield.data.loader import load_dataset, test_data_path
from tfield.models.idw import AnisoMetric
from tfield.pipeline import PipelineConfig


class FakeDS:
    """只够 load_for / new_bundle 用 —— 它们只读 signature。"""
    signature = "0123456789abcdef"


def _bundle(sig="abc1234567890def", groups=C.DEFAULT_FEATURE_GROUPS, **kw) -> CalibrationBundle:
    base = dict(
        dataset_sig=sig, groups_sig=groups_signature(groups),
        created_at="2026-10-01T00:00:00", tool_version=TOOL_VERSION,
        feature_groups=tuple(groups), trend_kind="xgboost",
        trend_params={"max_depth": 4}, metric=AnisoMetric(lx=5.0, lz=0.03, power=1.0),
        cross_shed=True, tuned_keys=("metric.power", "metric.lx"),
        search=SearchRecord(seed=0, n_trials=2,
                            space={"power": [1, 2]},
                            trials=pd.DataFrame([{"power": 1, "mae": 0.15},
                                                 {"power": 2, "mae": 0.16}]),
                            best={"power": 1},
                            plateau={"power": (1.0, 3.0)}),
        folds=("position:x0.15_z0.4",), metrics=pd.DataFrame([{"mae": 0.16}]),
        per_point=pd.DataFrame([{"sensor_id": 0, "mae": 0.1}]),
        ab=None,
    )
    base.update(kw)
    return CalibrationBundle(**base)


def test_配置由包还原():
    cfg = _bundle().config()
    assert isinstance(cfg, PipelineConfig)
    assert cfg.metric.lx == 5.0 and cfg.metric.power == 1.0 and cfg.cross_shed is True
    assert cfg.feature_groups == C.DEFAULT_FEATURE_GROUPS


def test_存取往返(tmp_path):
    b = _bundle()
    p = save_bundle(b, root=tmp_path)
    assert p.exists()
    back = load_bundle(p)
    assert back.dataset_sig == b.dataset_sig
    assert back.groups_sig == b.groups_sig
    assert back.metric == b.metric
    assert back.tuned_keys == b.tuned_keys
    assert back.search.plateau["power"] == (1.0, 3.0)
    assert back.search.seed == 0 and back.search.n_trials == 2
    assert list(back.search.trials["power"]) == [1, 2]
    assert back.metrics["mae"].iloc[0] == pytest.approx(0.16)


def test_序列化含搜索空间与种子():
    raw = json.loads(_bundle().to_json())
    assert raw["search"]["space"]["power"] == [1, 2]
    assert raw["search"]["seed"] == 0
    assert raw["tuned_keys"] == ["metric.power", "metric.lx"]
    assert raw["metric"]["lx"] == 5.0
    assert raw["groups_sig"] == groups_signature(C.DEFAULT_FEATURE_GROUPS)


def test_JSON往返不丢字段():
    b = _bundle()
    back = CalibrationBundle.from_json(b.to_json())
    assert back.tuned_keys == b.tuned_keys
    assert back.metric == b.metric
    assert back.feature_groups == b.feature_groups
    assert back.groups_sig == b.groups_sig
    assert back.search.trials.shape == b.search.trials.shape


def test_路径同时编码数据集与特征组(tmp_path):
    p = bundle_path("deadbeefcafe1234", C.DEFAULT_FEATURE_GROUPS, root=tmp_path)
    assert "deadbeefcafe1234" in p.name
    assert groups_signature(C.DEFAULT_FEATURE_GROUPS) in p.name


def test_缺文件时返回None(tmp_path):
    assert load_bundle(tmp_path / "nope.json") is None


def test_new_bundle写入工具版本与指纹():
    b = new_bundle(FakeDS(), PipelineConfig.fallback(), tuned_keys=("metric.lx",),
                   search=_bundle().search, folds=("position:x0.15_z0.4",),
                   metrics=pd.DataFrame([{"mae": 1.0}]),
                   per_point=pd.DataFrame([{"sensor_id": 0}]))
    assert b.dataset_sig == "0123456789abcdef"
    assert b.tool_version == TOOL_VERSION
    assert b.tuned_keys == ("metric.lx",)
    assert b.groups_sig == groups_signature(C.DEFAULT_FEATURE_GROUPS)


def test_matches对指纹敏感():
    class DS:
        signature = "aaaaaaaaaaaaaaaa"
    assert _bundle(sig="aaaaaaaaaaaaaaaa").matches(DS())
    assert not _bundle(sig="bbbbbbbbbbbbbbbb").matches(DS())


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_指纹不匹配时拒绝返回(tmp_path):
    """Review Focus #1：换数据后不能悄悄用旧参数。"""
    ds = load_dataset(test_data_path())
    g = C.DEFAULT_FEATURE_GROUPS
    save_bundle(_bundle(sig="0000000000000000"), root=tmp_path)
    assert load_for(ds, g, root=tmp_path) is None

    save_bundle(_bundle(sig=ds.signature), root=tmp_path)
    got = load_for(ds, g, root=tmp_path)
    assert got is not None and got.matches(ds)


def test_同一份数据两组特征是两个包(tmp_path):
    """参数是**特征组的函数**：换了特征组，旧参数就不再是最优的，两者不能互相顶替。"""
    g1, g2 = ("coord", "meteo"), C.DEFAULT_FEATURE_GROUPS
    assert (bundle_path(FakeDS.signature, g1, tmp_path)
            != bundle_path(FakeDS.signature, g2, tmp_path))

    save_bundle(_bundle(sig=FakeDS.signature, groups=g1), root=tmp_path)
    save_bundle(_bundle(sig=FakeDS.signature, groups=g2), root=tmp_path)

    assert load_for(FakeDS(), g1, root=tmp_path).feature_groups == tuple(g1)
    assert load_for(FakeDS(), g2, root=tmp_path).feature_groups == tuple(g2)
    assert load_for(FakeDS(), ("coord",), root=tmp_path) is None, "没标过的特征组不能返回别的包"


def test_calibrate_or_load第二次走缓存(tmp_path, monkeypatch):
    """前端唯一入口的缓存语义：同一个 (数据, 特征组) 只真正标定一次。

    搜索是确定性的（固定种子、残差缓存、不做早停），所以第二次必须秒回同一个包，
    而不是把 40 组参数重训一遍。
    """
    import tfield.calibration as cal

    calls: list = []

    def fake_run(ds, groups, **kw):
        calls.append(tuple(groups))
        return _bundle(sig=FakeDS.signature, groups=groups)

    monkeypatch.setattr(cal, "run_calibration", fake_run)
    g = C.DEFAULT_FEATURE_GROUPS

    first = cal.calibrate_or_load(FakeDS(), g, root=tmp_path)
    second = cal.calibrate_or_load(FakeDS(), g, root=tmp_path)

    assert calls == [tuple(g)], "第二次必须命中缓存，不能再跑一遍标定"
    assert first.dataset_sig == second.dataset_sig == FakeDS.signature
    assert first.groups_sig == second.groups_sig == groups_signature(g)


def test_force绕过缓存(tmp_path, monkeypatch):
    import tfield.calibration as cal

    calls: list = []

    def fake_run(ds, groups, **kw):
        calls.append(tuple(groups))
        return _bundle(sig=FakeDS.signature, groups=groups)

    monkeypatch.setattr(cal, "run_calibration", fake_run)
    g = C.DEFAULT_FEATURE_GROUPS
    cal.calibrate_or_load(FakeDS(), g, root=tmp_path)
    cal.calibrate_or_load(FakeDS(), g, root=tmp_path, force=True)
    assert len(calls) == 2


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_真实数据集能走通new_bundle(tmp_path):
    ds = load_dataset(test_data_path())
    b = new_bundle(ds, PipelineConfig.fallback(), tuned_keys=("metric.lx",),
                   search=_bundle().search, folds=("position:x0.15_z0.4",),
                   metrics=pd.DataFrame([{"mae": 1.0}]),
                   per_point=pd.DataFrame([{"sensor_id": 0}]))
    save_bundle(b, root=tmp_path)
    assert load_for(ds, C.DEFAULT_FEATURE_GROUPS, root=tmp_path) is not None


def test_tuned_keys与搜索空间一一对应():
    """标定包里的 tuned_keys 声明「这些参数是标定搜出来的」。

    多写一个就是谎报 —— 比如 metric.ly：它恒为 1.0（IDW_SPACE 里根本没有 ly），
    从未被搜索。少写一个则相反：搜过的参数没声明，包就没法自证调参范围。
    """
    import dataclasses
    import tfield.calibration as cal
    from tfield.models.idw import AnisoMetric

    # metric.* 只能指向 AnisoMetric 真的有的字段 —— 从搜索空间的键名直接推前缀是错的：
    # IDW_SPACE 里有个 cross_shed，它不是 metric 的字段，而是一个独立开关。
    fields = {f.name for f in dataclasses.fields(AnisoMetric)}
    expected = ({f"metric.{k}" for k in cal.IDW_SPACE if k in fields}
                | {"cross_shed"} | {f"trend.{k}" for k in cal.TREND_SPACE})
    assert set(cal.TUNED_KEYS) == expected
    assert "metric.ly" not in cal.TUNED_KEYS, "ly 固定为 1.0，从未进过搜索空间"
    assert "metric.cross_shed" not in cal.TUNED_KEYS, "cross_shed 不是 AnisoMetric 的字段"


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_中断在第一次询问即生效且不留文件(tmp_path):
    """should_stop 立刻返回 True：阶段 1 一上来就停，磁盘上什么都不能有。"""
    ds = load_dataset(test_data_path())
    root = tmp_path / "configs"
    with pytest.raises(CalibrationAborted):
        run_calibration(ds, n_trials=1, root=root, should_stop=lambda: True)
    assert not root.exists(), f"中断后不该建目录，却有 {list(root.rglob('*'))}"


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_阶段1结束后中断不留灵敏度CSV(tmp_path):
    """阶段 1 跑完、阶段 2 动手之前中断 —— 旧的写点会在这里落下 CSV。"""
    ds = load_dataset(test_data_path())
    root = tmp_path / "configs"
    seen_stage1 = False

    def on_progress(msg: str) -> None:
        nonlocal seen_stage1
        if "阶段 1 最优" in msg:
            seen_stage1 = True

    with pytest.raises(CalibrationAborted):
        run_calibration(ds, n_trials=1, root=root, progress=on_progress,
                        should_stop=lambda: seen_stage1)
    assert seen_stage1, "进度回调没跑到阶段 1 结束，测试没测到该测的地方"
    assert not root.exists() or not list(root.rglob("*")), \
        f"中断后不该留文件，却有 {[p.name for p in root.rglob('*')]}"


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_阶段2试验之间中断不留文件(tmp_path):
    """阶段 2 的第一轮试验结束后中断：CSV 与标定包都不许出现。"""
    ds = load_dataset(test_data_path())
    root = tmp_path / "configs"
    seen_trial1 = False

    def on_progress(msg: str) -> None:
        nonlocal seen_trial1
        if "[1/2]" in msg:
            seen_trial1 = True

    with pytest.raises(CalibrationAborted):
        run_calibration(ds, n_trials=2, root=root, progress=on_progress,
                        should_stop=lambda: seen_trial1)
    assert seen_trial1, "进度回调没跑到阶段 2 第一轮试验，测试没测到该测的地方"
    assert not root.exists() or not list(root.rglob("*")), \
        f"中断后不该留文件，却有 {[p.name for p in root.rglob('*')]}"


def test_自定义搜索空间不被缓存静默顶替(tmp_path, monkeypatch):
    """缓存键是 (数据集指纹, 特征组哈希)，而搜索空间是入参 —— 双键没变、搜的范围变了。

    规格书 §三 用 `created_at` 覆盖的正是这一类：同一个数据集、同一个特征组，
    换了搜索范围重新搜出一套新参数。所以带自定义空间调用时必须真的重搜：
    否则用户在 ② 里改了范围，界面却把旧包当新包端上来，而参数压根不是那个范围里的最优。
    """
    import tfield.calibration as cal

    calls: list = []

    def fake_run(ds, groups, **kw):
        calls.append(kw.get("idw_space"))
        return _bundle(sig=FakeDS.signature, groups=groups)

    monkeypatch.setattr(cal, "run_calibration", fake_run)
    g = C.DEFAULT_FEATURE_GROUPS
    narrow = {"power": [2.0], "lx": [1.0], "lz": [0.1], "cross_shed": [True]}

    cal.calibrate_or_load(FakeDS(), g, root=tmp_path)
    cal.calibrate_or_load(FakeDS(), g, root=tmp_path)
    assert len(calls) == 1, "默认空间下第二次必须命中缓存"

    cal.calibrate_or_load(FakeDS(), g, root=tmp_path, idw_space=narrow)
    assert len(calls) == 2, "带自定义搜索空间时必须重搜，不能拿旧包顶替"
    assert calls[-1] == narrow, "重搜要真的用上自定义空间，而不是丢掉它照默认跑"


@pytest.mark.skipif(not test_data_path().exists(), reason="数据集不在仓库根")
def test_缩小搜索空间后能秒级跑完并写出CSV与包(tmp_path):
    """搜索空间传参生效：整条链路（阶段 1/2/3 + 写文件）在小空间上跑通。

    走 calibrate_or_load(force=True) 而不是 run_calibration —— 前者是模块文档写明的
    「前端唯一入口」，也是真正写出标定包的那一层（run_calibration 只写灵敏度 CSV）。
    顺带守住 Task 1 搬动写点后的成功路径：CSV 与包都必须出现。
    """
    import tfield.calibration as cal

    ds = load_dataset(test_data_path())
    root = tmp_path / "configs"
    idw_space = {"power": [2.0], "lx": [2.0], "lz": [0.12], "cross_shed": [True]}
    trend_space = {"objective": ["reg:squarederror"], "max_depth": [3],
                   "learning_rate": [0.05], "n_estimators": [5],
                   "min_child_weight": [5], "subsample": [0.7],
                   "colsample_bytree": [1.0], "reg_lambda": [1.0]}
    b = cal.calibrate_or_load(ds, C.DEFAULT_FEATURE_GROUPS, n_trials=1, root=root,
                              force=True, idw_space=idw_space, trend_space=trend_space)
    # bundle.metric 是 AnisoMetric 对象（to_dict 才变成 dict），逐字段比对
    assert (b.metric.power, b.metric.lx, b.metric.ly, b.metric.lz) == (2.0, 2.0, 1.0, 0.12)
    assert b.cross_shed is True
    assert b.search.space["idw.power"] == [2.0], "包里必须记下本次实际用的搜索空间"
    written = sorted(p.name for p in root.rglob("*"))
    assert any(n.startswith("sensitivity_") and n.endswith(".csv") for n in written), written
    assert any(n.startswith("bundle_") and n.endswith(".json") for n in written), written
