"""成品在路由上的两个可见后果：保存时固化、没有数据集时降级。

⚠️ 要一个活着的 MySQL（`models_db`，独立库 `tfield_models_test`）。
⚠️ **不请求 `current_model`** —— 这个文件要空库、要数是第几行，
   与 `test_api_models.py` 开头那段注释同一个理由。
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import threading

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import conftest                                          # noqa: E402
from api import deps, jobs, models_store, paths          # noqa: E402
from api.main import create_app                          # noqa: E402

#: 一棵**很小**的树。**这一条是本文件的寿命所在**：保存那一路必定要训一遍
#: （固化 = 把拟合好的趋势存下来），交付包自带的那套参数一训十几秒，
#: 而本文件要 POST 好几次。
TINY_TREND = {"n_estimators": 1, "max_depth": 1, "learning_rate": 0.1}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture()
def ds(delivered_bundle):
    """当前数据集，并把指针指着它。"""
    deps.install_dataset(paths.dataset_path())
    return deps.get_train_dataset()


@pytest.fixture()
def empty(models_db):
    """空库，并返回它。"""
    conn = models_db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM model")
        conn.commit()
    finally:
        conn.close()
    return models_db


@pytest.fixture()
def tiny_job():
    """造一个「刚跑完、还没入库」的 job，且包里是小树参数。

    ⚠️ **这是 `test_api_models.py::finish_job` 的本地副本，故意的**：
    跨测试模块借夹具要 `conftest` 或 `import`，而后者会让两个文件在一个
    收集顺序下互相牵动。差别只有一处 —— 包里的趋势参数换成小树。

    ⚠️ 门闩（`gate`）是承重的：执行器是**单线程池**，`work` 卡在 `gate.wait()`
    上，所以 `jobs.finish(...)` 一定**先于** `_run` 那句「跑完了却没有结论」的
    兜底判断发生。不放门闩的话两边抢同一个 job，`_run` 会先把状态定成 `failed`
    并摘掉 `_CURRENT`，于是后面所有 `current_bundle()` 都读到 None，
    而它们红起来的样子像路由写错了。
    """
    def go() -> None:
        gate = threading.Event()

        def work(job):
            gate.wait(5)

        bundle = dataclasses.replace(conftest.delivered_train_bundle(),
                                     trend_params=dict(TINY_TREND))
        job = jobs.submit(work)
        job.result = bundle
        jobs.finish(job, jobs.DONE)
        gate.set()

    return go


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    """每一格都从一个**空的管线缓存**开始，并原样交还。

    ⚠️ **必须 autouse，理由不在这一格、在别人身上。** `deps._PIPELINES` 是
    **模块级**的，跨用例、跨文件活着；而本文件从头到尾用的都是**交付那一份包**
    （`tiny_job` 与下面几条造出来的包只换了趋势参数，`dataclasses.replace`
    保住了 `created_at`）。于是它们的缓存键
    `(ds.signature, groups_sig, bundle.created_at)` 与**交付包那一份完全一样**。

    留一个下去，下一个文件就替它背：

      · `test_api_borrowed_model.py`（按文件名字母序紧随本文件）要的正是「借来的」
        那一句，而留下去的那一份的 `mismatch_note` 是**空串** —— 屏上把借来的模型
        说成本地的。实测：`pytest tests/test_api_artifact.py
        tests/test_api_borrowed_model.py` 两条必红，单独跑那条文件四条全绿。
      · 本文件自己也有同一个坑的另一面：键撞上就命中上一条留下的管线，
        成品根本没被读过而用例照样绿。

    与 `test_deps_artifact.py:75` 的 `fresh_cache` 是同一件事 —— 那边逐条按需
    请求，这边 autouse：本文件**每一条**都会走 `get_pipeline()`（保存那一路自己
    会调它），没有一条不需要。
    """
    monkeypatch.setattr(deps, "_PIPELINES", deps.PipelineCache())


def test_保存那一路会把成品写进同一行(client, empty, ds, tiny_job):
    """⭐ 规格书 D3：成品与包**同一条 INSERT**，不是事后再补一次 UPDATE。

    ⚠️ 这条走的是真路由：`deps.get_pipeline()` 必须在 `save_model` **之前**
    拿 —— 此刻「当前那一份」就是刚跑完还没保存的那一份，那正是要固化的模型。
    """
    tiny_job()
    r = client.post("/api/models", json={"name": "固化一份"})
    assert r.status_code == 201, r.text[:300]
    row = r.json()
    assert row["name"] == "固化一份"

    raw = empty.artifact_of(row["id"])
    assert raw is not None, "保存之后库里那一行该有成品"
    assert raw[:6] == b"TFART\x00", "写进去的该是一份成品字节"
    assert len(raw) > 1000, f"成品 {len(raw)} 字节 —— 像是个空壳"

    body = client.get("/api/models").json()
    mine = [x for x in body["rows"] if x["id"] == row["id"]]
    assert mine and mine[0]["has_artifact"] is True


def test_没有数据集时_有成品的行仍然可用(client, empty, ds, monkeypatch, tmp_path):
    """⭐ 规格书 D5/D6：`GET /api/models` 不再需要数据集。有成品的那一行
    照样 `compatible` —— 它的参数**已经固化**，不需要那份数据才存在。

    ⚠️ 把页⑤ 那根轴**也打掉**（`monkeypatch` 那两句）：2026-10-16 起没有当前
    数据集时列表改用 `configs/live/train.xlsx` 判定，而那台机器上跑过一次
    `make_live_source.py` 就有了 —— 不打的话，这条用例测的「两根轴都没有」那一档
    会悄悄换成「页⑤ 那根轴在」那一档，结果取决于这台机器跑没跑过那条命令。
    """
    bundle = dataclasses.replace(conftest.delivered_train_bundle(),
                                 trend_params=dict(TINY_TREND))
    cfg = bundle.config()
    from tfield.features import build_features
    from tfield.pipeline import FieldPipeline
    ref = FieldPipeline(cfg, ds).fit(build_features(ds, cfg.feature_groups), ds)
    row = empty.save_model("带成品的一份", bundle, ds,
                           paths.dataset_path().name,
                           artifact=ref.capture().to_bytes())

    monkeypatch.setattr(paths, "LIVE_TRAIN", tmp_path / "缺.xlsx")
    deps.clear_current_dataset()
    try:
        body = client.get("/api/models").json()
    finally:
        deps.install_dataset(paths.dataset_path())

    assert body["dataset_file"] is None
    assert body["dataset_sig"] is None
    got = [x for x in body["rows"] if x["id"] == row.id]
    assert got, "没有数据集时这一行仍然该在列表里"
    assert got[0]["compatible"] is True, "有成品就够了 —— 参数已经固化"
    assert got[0]["why"] == "", "能用就不该有一句理由"


def test_没有数据集时_没成品的行说得出为什么(client, empty, ds, monkeypatch,
                                        tmp_path):
    """`why` 是那句话，不是空串、也不是 `null` —— 前端不用判两种空。

    同上：页⑤ 那根轴必须打掉，否则测的是「页⑤ 那根轴在」那一档。
    """
    empty.save_model("没成品的一份", conftest.delivered_train_bundle(), ds,
                     paths.dataset_path().name)

    monkeypatch.setattr(paths, "LIVE_TRAIN", tmp_path / "缺.xlsx")
    deps.clear_current_dataset()
    try:
        body = client.get("/api/models").json()
    finally:
        deps.install_dataset(paths.dataset_path())

    got = [x for x in body["rows"] if x["name"] == "没成品的一份"]
    assert got and got[0]["compatible"] is False
    assert got[0]["why"] == "这一条还没有成品，先导入数据集才能用"


def test_没有数据集时不该报错_而且是可序列化的(client, empty, ds):
    """⭐ 规格书 D5：这一格原来会 409（`get_train_dataset` 抛
    `NoDatasetError`）。整页因为「模型库」这个动作而打不开，是这一轮要消掉的事。
    """
    deps.clear_current_dataset()
    try:
        r = client.get("/api/models")
    finally:
        deps.install_dataset(paths.dataset_path())

    assert r.status_code == 200, (
        f"没有数据集时模型库该降级，不是 {r.status_code}：{r.text[:300]}")
    json.dumps(r.json())          # `None` 不许在序列化时变成 NaN 之类


def test_有数据集时_compatible的行挑起来真的不炸(client, empty, ds):
    """⭐ Review Focus 3。`compatible` 说的是「特征组对得上」，而构场要建
    特征矩阵 —— 两轴之间那道缝今天是靠一条推论撑着的，没有任何用例钉过。

    对库里**每一行** `compatible` 为真的记录真的跑一次 `get_pipeline()`。
    """
    empty.save_model("小树的一份", dataclasses.replace(
        conftest.delivered_train_bundle(), trend_params=dict(TINY_TREND)),
        ds, paths.dataset_path().name)

    body = client.get("/api/models").json()
    usable = [x for x in body["rows"] if x["compatible"]]
    assert usable, "一条能用的都没有，这条用例什么都判不了"
    for x in usable:
        assert models_store.set_current(x["id"]) is True
        deps._PIPELINES = deps.PipelineCache()
        pipe = deps.get_pipeline()
        assert pipe.fitted, f"行 {x['id']} 说能用，挑起来却是死的"
        assert pipe.feature_names, f"行 {x['id']} 的特征列是空的"
