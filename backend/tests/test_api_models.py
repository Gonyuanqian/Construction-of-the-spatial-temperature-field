"""`/api/models` 四条路由：列表、详情、保存、设为当前。

⚠️ 要一个活着的 MySQL（独立库 `tfield_models_test`，库名由
`tests/conftest.py::_pin_test_library` 钉住）。连不上时**不 skip** ——
skip 会让「这台机器上 MySQL 没了」在测试结果里长得跟「全都通过」一样。

⚠️ 这个文件要的是**空库**，所以它不请求 `current_model`，只用 `models_db`
（每一格清一次）。列表里有多少行、`current_id` 是谁，全是这些用例自己
造出来的 —— 库里预先种着交付那一份的话，几乎每一条都比错了基准。
"""
from __future__ import annotations

import pathlib
import sys
import threading

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import conftest                                          # noqa: E402
from api import deps, jobs, models_store, paths          # noqa: E402
from api.main import create_app                          # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def raw_client() -> TestClient:
    """**不把服务端异常抛给调用方**的客户端。

    默认的 `TestClient` 是 `raise_server_exceptions=True`：未翻译的异常会从
    `client.get(...)` 那一行**直接抛出来**，于是「用户实际收到什么」根本看不见
    —— 用户收到的是 500。要断言状态码，必须关掉它（与 `test_api_live.py`
    的 `raw_client` 同一个东西）。
    """
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _library(models_db):
    """每一格都从「一条模型都没有」开始，并且手上没有残留的 job。

    ⚠️ 清库那件事在 `models_db` 里（`tests/conftest.py`），这里只管这个文件
    自己的两样状态：`jobs._CURRENT`（「刚跑完那一份」挂在它上面）与数据集
    缓存。漏掉前者的话，上一条用例跑完的 job 会**跨用例**压着库里的模型，
    而它红起来的样子像路由写错了。
    """
    jobs.clear()
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()
    yield
    jobs.clear()


@pytest.fixture()
def finish_job(delivered_bundle):
    """造一个「刚跑完、还没入库」的 job 的**工厂**。绕开几分钟的真搜索。

    ``finish_job()`` 调一次造一份；同一个用例要造两份（换人那一条）就调两次。

    ⚠️ 门闩（`gate`）是承重的：执行器是**单线程池**，`work` 卡在
    `gate.wait()` 上，所以下面的 `jobs.finish(...)` 一定**先于** `_run`
    那句「跑完了却没有结论」的兜底判断发生。不放门闩的话两边抢同一个 job，
    `_run` 会先把状态定成 `failed` 并摘掉 `_CURRENT` —— 于是后面所有
    `current_bundle()` 都读到 None，而它们红起来的样子像路由写错了。

    ⚠️ 也不许图省事写成 `jobs.submit(cj._work)`：那会真的跑一次标定，
    四十次试验乘四折，分钟级。
    """
    def go() -> None:
        gate = threading.Event()

        def work(job):
            gate.wait(5)

        job = jobs.submit(work)
        job.result = delivered_bundle
        jobs.finish(job, jobs.DONE)
        gate.set()

    return go


def test_空库时列表是空的_但接口是好的(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == []
    assert body["current_id"] is None


def test_保存需要手上有一份刚跑完的(client):
    """⭐ 409 而不是 422：请求本身没错，是**现在不能做这件事**。

    也不许「凭当前模型再造一行」—— 那就成了「保存」一个已经保存过的东西，
    而库里会多出一行谁都分不清的副本。
    """
    r = client.post("/api/models", json={"name": "没有刚跑完的"})
    assert r.status_code == 409
    assert "模型训练" in r.json()["detail"]


def test_保存之后出现在列表里_而且被标成当前(client, finish_job):
    finish_job()
    r = client.post("/api/models", json={"name": "棚里那套"})
    assert r.status_code == 201
    row = r.json()
    assert row["name"] == "棚里那套"

    body = client.get("/api/models").json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["is_current"] is True
    assert body["current_id"] == row["id"]
    assert body["rows"][0]["mae"] is not None
    # 列表行**不带包**：794 KB 一行，用户一屏十行就是 8 MB
    assert "bundle" not in body["rows"][0]


def test_保存之后那一份就退场了_页三认库里的(client, finish_job):
    """⭐ 退场条件的接口级钉子（规格书 §5.4）。

    ⚠️ 名字里的「页三」不是「页③」：`③`（U+2462）不是合法的 Python 标识符
    字符，带它的函数名会让**整个文件收不进来**（`SyntaxError`，一条都跑不了）。
    计划里写的就是那个字符。
    """
    finish_job()
    assert deps.current_bundle().source == "unsaved"
    client.post("/api/models", json={"name": "x"})
    assert deps.current_bundle().source == "library"


def test_名字不合格时报_422_而不是写进库(client, finish_job):
    """⭐ Review Focus 4。"""
    finish_job()
    for bad in ["", "   ", "\t\n", None, 123, "名" * 121]:
        r = client.post("/api/models", json={"name": bad})
        assert r.status_code == 422, f"{bad!r} 被放进去了"
        assert r.json()["detail"], "422 必须带一句人话"
    assert client.get("/api/models").json()["rows"] == [], "拒绝的那几次不许留下一行"


def test_名字首尾的空白被剪掉(client, finish_job):
    finish_job()
    row = client.post("/api/models", json={"name": "  棚里那套  "}).json()
    assert row["name"] == "棚里那套"


def test_请求体形状不对时报_422(client):
    assert client.post("/api/models", json=["不是对象"]).status_code == 422
    assert client.post("/api/models", json={}).status_code == 422


def test_详情带着参数_效果与搜索区间(client, finish_job, delivered_bundle):
    finish_job()
    mid = client.post("/api/models", json={"name": "x"}).json()["id"]
    d = client.get(f"/api/models/{mid}").json()
    assert d["id"] == mid
    # ⚠️ 两个时间不是一回事：saved_at 是用户点保存的时刻，created_at 是标定
    # 跑完的时刻。页上写「保存于」，不许互相冒充。
    assert d["saved_at"] and d["created_at"]
    assert d["created_at"] == delivered_bundle.created_at
    assert d["feature_groups"] == ["coord", "zbasis", "meteo", "interaction"]
    assert d["trend_kind"]
    assert set(d["metric"]) == {"lx", "ly", "lz", "power"}
    assert d["cross_shed"] in (True, False)
    assert d["tuned_keys"]
    assert len(d["metrics"]) == 8
    assert {r["group"] for r in d["metrics"]} == {"A", "B"}
    assert d["ab"] and set(d["ab"]) == {"mae_a", "mae_b", "gap"}
    assert d["plateau"] and set(d["plateau"][0]) == {"dim", "lo", "hi"}
    assert d["n_trials"] > 0
    # 逐测点表**不在**详情里：用户刚把页② 那张表撤掉（「没必要展示」），
    # 详情页再摆一张就是同一个东西换个地方（规格书 §6.1）。
    assert "per_point" not in d
    # trials 是 794 KB 的大头，屏上没地方放，也没有这个需求
    assert "trials" not in d


def test_没有这个模型时_404(client):
    assert client.get("/api/models/999999").status_code == 404
    assert client.post("/api/models/999999/current").status_code == 404


def test_设为当前能换人(client, finish_job):
    finish_job()
    a = client.post("/api/models", json={"name": "一"}).json()["id"]
    finish_job()
    b = client.post("/api/models", json={"name": "二"}).json()["id"]
    assert client.post(f"/api/models/{a}/current").status_code == 200
    body = client.get("/api/models").json()
    assert body["current_id"] == a
    assert [r["is_current"] for r in body["rows"] if r["id"] == a] == [True]
    assert [r["is_current"] for r in body["rows"] if r["id"] == b] == [False]


def test_设为当前会把未入库的那一份摘掉(client, finish_job):
    """否则「刚跑完那一份」会一直压着用户刚点的那个模型，页③ 一动不动。"""
    finish_job()
    client.post("/api/models", json={"name": "一"})
    finish_job()
    other = client.get("/api/models").json()["rows"][0]["id"]
    assert deps.current_bundle().source == "unsaved"
    client.post(f"/api/models/{other}/current")
    assert deps.current_bundle().source == "library"


def test_同文件名但签名变了_理由是改动过不是来源不同(client, finish_job):
    """⭐ Review Focus 5。

    签名里掺了文件的 **mtime**（`loader.py` 的 `Dataset.signature`），
    所以「换了一份数据集」与「同一个文件原地重存过一次」都会让签名对不上。
    只说「数据来源不同」，用户会去重新导入一份，然后发现还是不行 ——
    因为变的根本不是哪一份文件，是那个文件本身。

    ⚠️ 这一行**仍然选得中**（`compatible` 是 true）：2026-10-10 用户裁定之后，
    拦着选的只剩特征组那一轴。它能用、要标出来 —— 但不再是「用不了」。
    """
    finish_job()
    mid = client.post("/api/models", json={"name": "x"}).json()["id"]
    # 把库里那一行的签名改成别的，文件名保持与当前数据集一致
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE model SET dataset_sig = %s WHERE id = %s",
                        ("另一份的签名", mid))
        conn.commit()
    finally:
        conn.close()
    row = client.get("/api/models").json()["rows"][0]
    assert row["compatible"] is True, "数据集那一轴不再拦着选"
    assert row["borrowed"] is True, "它要带上「借来的」那个标"
    assert row["why"] == "同一个文件被改动过（内容或修改时间变了）"


def test_换了一份文件名_理由是来源不同并带上文件名(client, finish_job):
    finish_job()
    mid = client.post("/api/models", json={"name": "x"}).json()["id"]
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE model SET dataset_sig = %s, data_file = %s"
                        " WHERE id = %s", ("另一份的签名", "别人家的棚.xlsx", mid))
        conn.commit()
    finally:
        conn.close()
    row = client.get("/api/models").json()["rows"][0]
    assert row["compatible"] is True, "数据集那一轴不再拦着选"
    assert row["borrowed"] is True
    assert row["why"] == "数据来源不同：别人家的棚.xlsx"


def test_对得上的那一行_compatible_是_true_且理由是空串(client, finish_job):
    finish_job()
    client.post("/api/models", json={"name": "x"})
    row = client.get("/api/models").json()["rows"][0]
    assert row["compatible"] is True
    assert row["borrowed"] is False, "本地的不是借来的"
    assert row["why"] == ""


def test_特征组对不上的那一行_列表也说不兼容(client, finish_job):
    """⭐ 2026-10-10 用户裁定（模型不绑数据集）揭出来的第一条现有不一致。

    「对得上」这件事原先有**两套定义**：这张列表只看数据集签名与文件名
    （`routes/models.py::_compat`），而构场那条路上 `deps._usable` **还比
    特征组**。于是一行按别的特征组标出来的模型，列表说「能用」，选它当当前
    模型却会被丢开、退回兜底参数 —— 屏上没有一个字提示这件事。

    特征组列**可以**被改到这一格（页② 今天把它写死成 `C.DEFAULT_FEATURE_GROUPS`，
    所以真实操作里走不到；但构场拒绝的正是这一列所代表的那个东西）。

    ⚠️ 用户裁定放行的是**数据集那一轴**，这一轴照旧硬拦：它不是「哪一份数据」
    的问题，是**输入类型**的问题 —— 拿另一组特征拟出来的矩阵去配这份参数，
    要么尺寸对不上当场炸，要么静默画错。
    """
    finish_job()
    mid = client.post("/api/models", json={"name": "x"}).json()["id"]
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE model SET groups_sig = %s WHERE id = %s",
                        ("00000000", mid))
        conn.commit()
    finally:
        conn.close()
    body = client.get("/api/models").json()
    assert body["rows"], f"存进去的那一行不见了：{body}"
    row = body["rows"][0]
    assert row["compatible"] is False, f"列表说它能用，而构场那条路会拒绝它：{row}"
    assert row["why"], "不兼容必须带一句人话"
    # 用不了的行**不叫借来的**：那是「能借来用、但不是这份数据标的」的意思，
    # 给一行选都选不中的东西盖这个标，只是让人多问一句「那我到底能不能点」。
    assert row["borrowed"] is False


def test_借来的那一行选得中_而且真的拿去构场(client):
    """⭐⭐ 2026-10-10 用户裁定的正面：「只要是模型库中有模型，就能选择模型库
    中的任意一个模型来构建，而不是绑定数据集。」

    ⚠️ 与上面三条合起来才完整：那三条只说列表**怎么说**（`compatible` /
    `borrowed` / `why`），这一条说**点下去真的生效** —— 列表说完能选、
    `post /current` 选完，`current_bundle()` 却不认它，正是这次要拆掉的那个
    自相矛盾。也钉住 `current_bundle` 与列表用的是**同一个判据**
    （`deps.model_fit`），不是各写一份。

    ⚠️ 存的是一个**自洽的包**，不是上面那几条「把库里那一行的签名改掉」的手法：
    那样改，行说 A、包还说 B，而 `current_bundle()` 从行上读、构场从包上读 ——
    测的是一个线上造不出来的状态。这里换的是**包对象本身**（合成一份为别的
    数据集标的的，见 `conftest.bundle_for_another_dataset`），`save_model` 把它的
    签名抄进行里、把整包写进 LONGTEXT —— 行与包一起变。
    """
    ds = deps.get_train_dataset()
    other = conftest.bundle_for_another_dataset()
    assert other.dataset_sig != ds.signature, "取到的是对得上的那一份，这条白跑"
    row = models_store.save_model("别人家标的", other, ds, "别人家的棚.xlsx")

    listed = next(r for r in client.get("/api/models").json()["rows"]
                  if r["id"] == row.id)
    assert listed["compatible"] is True, "库里有就能挑，数据集那一轴不拦"
    assert listed["borrowed"] is True
    assert listed["why"], "借来的也要说得出理由"

    assert client.post(f"/api/models/{row.id}/current").status_code == 200
    got = deps.current_bundle()
    assert got.source == "library", "列表说能选，选完却不认它 —— 正是要拆的那个矛盾"
    assert got.bundle is not None
    assert got.bundle.dataset_sig == other.dataset_sig, "用的不是用户点的那个模型"
    assert got.mismatch_note, "借来的必须如实报出来"


def test_没有数据集时列表降级_不是_409(client, finish_job, monkeypatch, tmp_path):
    """⭐ 规格书 D5：这一格原来走 409（`get_train_dataset` 抛 `NoDatasetError`）。

    「模型库」这个动作在没有数据集时整页打不开，是这一轮要消掉的事 ——
    「库里有哪些模型」本来就不需要数据集。降级之后「能不能用」成了**这一行
    自己的性质**：有没有成品。

    ⚠️ 判据（`compatible`）**一个字都没改**，改的只是「没有数据集时拿哪一轴
    去判」—— 有数据集那一档仍走 `_compat`（规格书 D6）。这一条刚跑完就被保存，
    成品与包**同一条 INSERT** 落库，所以它仍然能用。
    """
    finish_job()
    row = client.post("/api/models", json={"name": "x"}).json()
    # ⚠️ 把页⑤ 那根轴**打掉**：这条要测的是「两根轴都不在」那一档。
    # 不打的话，开发机上一旦跑过 `make_live_source.py`，`configs/live/train.xlsx`
    # 就在，列表会改走页⑤ 那根轴 —— 这条用例的结果从此取决于**这台机器跑没跑过
    # 那条命令**，而那不是它要测的东西。
    monkeypatch.setattr(paths, "LIVE_TRAIN", tmp_path / "缺.xlsx")
    deps.clear_current_dataset()
    r = client.get("/api/models")
    assert r.status_code == 200, "没有数据集时模型库该降级，不是 409"
    body = r.json()
    assert body["dataset_file"] is None
    assert body["dataset_sig"] is None
    mine = [x for x in body["rows"] if x["id"] == row["id"]]
    assert mine and mine[0]["has_artifact"] is True, "保存那一路该把成品写进去"
    assert mine[0]["compatible"] is True, "有成品就够了 —— 参数已经固化"
    assert mine[0]["why"] == "", "能用就不该有一句理由"


def test_数据库连不上时列表接口报_500_并把原话带出来(raw_client, monkeypatch):
    """⭐ Review Focus 1。

    端到端那一条：`models_store` 抛出去，路由**不接**，由 FastAPI 兜成 500。
    **不许**在这里加 `except` 把它翻成空列表 —— 那会让「模型都没了」与
    「数据库连不上」在屏上长得一样。
    """
    monkeypatch.setenv("TFIELD_MYSQL_PORT", "1")
    r = raw_client.get("/api/models")
    assert r.status_code == 500


# ── 页⑤ 的判定轴（规格 §9.3） ──

#: 判定轴只要「读得出来」就够 —— `model_fit` 只拿 `ds.signature` 比，
#: 不碰场、不碰管线。所以一条 6 行的小样本足以当轴。
TIMES = pd.date_range("2026-07-27 11:30", periods=6, freq="5min")


def test_没有当前数据集时_判定轴换成页五那一份(client, finish_job, monkeypatch,
                                        synthetic_dataset):
    """规格 §9.3 第 1 条。`_CURRENT` 空、`live/train.xlsx` 在 —— 重启后的页⑤。

    ⚠️ 不接这一步的话：闸门放行了，页⑤ 仍被**另一张卡**挡住
    （「还没有能用的模型 / 库里现在还没有」），而那与实时源在不在没关系。
    """
    finish_job()                       # 「刚跑完那一份」，随后被保存进库
    made = client.post("/api/models", json={"name": "x"}).json()
    monkeypatch.setattr(paths, "LIVE_TRAIN", synthetic_dataset(TIMES, name="train.xlsx"))
    deps.clear_current_dataset()
    deps.reset_cache()

    body = client.get("/api/models").json()

    assert body["dataset_file"] == "train.xlsx", "「在比的是哪一份」说错了"
    assert body["dataset_sig"] is not None
    mine = [x for x in body["rows"] if x["id"] == made["id"]][0]
    assert mine["compatible"] is True, "特征组对得上就该能用 —— 数据集那一轴只报不拦"
    assert mine["why"].startswith("数据来源不同"), "换了轴，理由那句要说出来"


def test_两根轴都不在时退回今天那一档(client, finish_job, monkeypatch, tmp_path):
    """规格 §9.3 第 2 条：`_CURRENT` 空、`live/train.xlsx` 也不在 → `has_artifact`。"""
    finish_job()
    row = client.post("/api/models", json={"name": "x"}).json()
    monkeypatch.setattr(paths, "LIVE_TRAIN", tmp_path / "缺.xlsx")
    deps.clear_current_dataset()
    deps.reset_cache()

    body = client.get("/api/models").json()

    assert body["dataset_file"] is None
    mine = [x for x in body["rows"] if x["id"] == row["id"]][0]
    assert mine["compatible"] is True
    assert mine["why"] == ""
