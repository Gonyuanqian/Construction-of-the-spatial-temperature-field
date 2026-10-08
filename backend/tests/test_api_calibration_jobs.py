"""页② 第二段：标定长任务的四态、取消、换数据集。

**全程用替身替掉搜索**：真跑一次是分钟级（阶段 2 是 40 次试验 × 4 折拟合），
而这个文件要验的是**我们这一层**的状态机与落点，不是库的搜索质量。
库那一边的保证（中断不写任何文件）由它自己的测试守。

⚠️ **2026-10-08 起跑完不再写回盘**（模型库那一轮，规格书 D2）：跑出来的那一份
挂在 `job.result` 上，用户点「保存到模型库」才存进库。所以这个文件里凡是
「盘上有没有包」的断言都反过来了 —— 「跑完**不**落盘」才是现在该钉的事。

⚠️ **`test_标定跑着时换了数据集_包写在旧签名下且不崩` 已退场**：它守的是
「包路径按**当前**数据集重算会写进别人的签名里」。现在 `_work` 一个字节都
不往盘上写，那条路在结构上不存在了。
"""
from __future__ import annotations

import pathlib
import sys
import time

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, jobs, paths                       # noqa: E402
from api.main import create_app                         # noqa: E402
from api.routes import calibration_jobs as cj           # noqa: E402
from tfield.calibration import CalibrationAborted, load_bundle   # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _library(current_model):
    """这一整个文件都要求模型库里有一份能用的当前模型（见 `tests/conftest.py`）。

    三条 `/api/calibration` 的读（job 字段、mismatch）现在都要读一次模型库。
    库里空着时它们也答得出来（`present: false`），但 `mismatch` 在
    `present: true` 那条路上**恒为 null** —— 于是
    `test_bak_不被_mismatch_捡走` 会变成拿 null 比 null，一个字都没验到。
    那一条自己标 `empty_library`，让空态成为它真实的前提。
    """
    return current_model


@pytest.fixture(autouse=True)
def _clean_jobs():
    """每个用例从「一次都没跑过」开始，收工时不留一个还在跑的任务。

    job 是**进程级**的模块变量：不清理的话，上一个用例留在 `_CURRENT` 上的
    那个 job 会让下一个用例的 `POST` 直接吃 409。

    ⚠️ 收工那一段不是洁癖：这个文件里的替身有好几个是
    `while not should_stop(): sleep(...)` 的**死循环**，而用例的断言完全可能
    在它自己的 `DELETE` 之前就红（`health` 那一条的 `took < 2.0` 就是）。
    那时线程仍在跑，而 `ThreadPoolExecutor` 的线程是**非 daemon** 的、
    在解释器退出时被 join —— 结果是 pytest 打印完结果，然后永远卡在退出上。
    症状极具误导性：没有失败、没有超时、没有一个字。
    """
    jobs.clear()
    yield
    cur = jobs.current()
    if cur is not None and cur.state == jobs.RUNNING:
        cur.cancel.set()
        try:
            _wait(lambda: cur.state != jobs.RUNNING, timeout=10)
        except AssertionError:
            pass          # 停不下来也不许把上一个用例真实的失败盖掉
    jobs.clear()


@pytest.fixture(autouse=True)
def _current_dataset():
    """与 `test_api_train.py` 同一条：空态是默认，这个文件必须显式声明数据集。"""
    deps.set_current_dataset(paths.dataset_path())


def _real_bundle():
    """一份真包，拿来当替身的返回值。**只读**，不改盘上任何东西。"""
    real = load_bundle(sorted(paths.CONFIGS.glob("bundle_*.json"))[0])
    assert real is not None
    return real


def _wait(pred, timeout=5.0):
    """等一个条件成立。轮询 10ms —— 这是状态机测试，不是性能测试。"""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        got = pred()
        if got:
            return got
        time.sleep(0.01)
    raise AssertionError(f"{timeout}s 内条件没成立")


def _settled(client, job_id: str):
    """轮询一步：状态已经不是 `running` 就交出那份摘要，否则 None（交给 `_wait`）。

    ⚠️ 不要把它写成 `lambda: (j := client.get(...).json()) if j["state"] != "running" else None`。
    条件表达式**先算条件、后算真值分支**，而条件里读的 `j` 正是真值分支那个
    walrus 赋的 —— 于是读到的是「尚未赋值」，`UnboundLocalError`。
    """
    j = client.get(f"/api/calibration/jobs/{job_id}").json()
    return j if j["state"] != "running" else None


# ── 四态（T3）──

def test_跑完置_done_并把结果留在任务上(client, tmp_path, monkeypatch):
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)
    monkeypatch.setattr(cj, "run_calibration", lambda ds, g, **k: _real_bundle())
    job = client.post("/api/calibration/jobs").json()
    assert job["state"] == "running"
    done = _wait(lambda: _settled(client, job["id"]))
    assert done["state"] == "done"
    assert done["error"] is None
    assert done["elapsed_s"] >= 0
    # 结果挂在 job 上 —— 「保存到模型库」那一层要从这里取
    stored = jobs.get(job["id"]).result
    assert stored is not None
    assert stored.dataset_sig == _real_bundle().dataset_sig
    # ⚠️ 盘上**一个包都不许有**：自动落盘在 2026-10-08 退场（规格书 D2）。
    # 这一条是那个退场的钉子 —— 谁把 save_bundle 加回来，它就红。
    assert list(tmp_path.glob("bundle_*.json")) == [], "跑完又自动落盘了"


def test_抛异常置_failed_且_detail_是异常原话(client, tmp_path, monkeypatch):
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)

    def boom(ds, g, **k):
        raise RuntimeError("显存不够了")

    monkeypatch.setattr(cj, "run_calibration", boom)
    job = client.post("/api/calibration/jobs").json()
    bad = _wait(lambda: _settled(client, job["id"]))
    assert bad["state"] == "failed"
    assert "显存不够了" in bad["error"], "异常的**原话**必须上屏，换成一句通用文案就丢了现场"
    assert list(tmp_path.iterdir()) == [], "失败了就不该在盘上留下东西"


def test_取消一个正在跑的置_cancelled(client, tmp_path, monkeypatch):
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)

    def slow(ds, g, *, progress=None, should_stop=None, **k):
        if progress:
            progress("阶段 2 试验之间")
        for _ in range(500):                    # 最多 5 秒
            if should_stop is not None and should_stop():
                raise CalibrationAborted("阶段 2 试验之间被中断")
            time.sleep(0.01)
        raise AssertionError("取消没传到库里")

    monkeypatch.setattr(cj, "run_calibration", slow)
    job = client.post("/api/calibration/jobs").json()
    # 等到进度那一行出现，说明 work 真的进了替身
    _wait(lambda: client.get(f"/api/calibration/jobs/{job['id']}").json()["progress"])
    # DELETE 当下**不改状态**：真正的取消点在库里下一次被问到时
    now = client.delete(f"/api/calibration/jobs/{job['id']}").json()
    assert now["state"] == "running", "取消不该在库里那次搜索还没真的停下来时就自称已取消"
    end = _wait(lambda: _settled(client, job["id"]))
    assert end["state"] == "cancelled"


def test_取消一个已经结束的报_409(client, tmp_path, monkeypatch):
    """已经跑完的那一次不能再「取消」—— 报「已取消」是句谎话。"""
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)
    monkeypatch.setattr(cj, "run_calibration", lambda ds, g, **k: _real_bundle())
    job = client.post("/api/calibration/jobs").json()
    _wait(lambda: _settled(client, job["id"]))
    r = client.delete(f"/api/calibration/jobs/{job['id']}")
    assert r.status_code == 409
    assert "来不及取消" in r.json()["detail"]


def test_第二次_post_报_409_并带上正在跑的那个_id(client, tmp_path, monkeypatch):
    """T3（§4.5）：指路，不排队、也不假装幂等。

    前端收到 409 就切去轮询**这个 id** —— 所以它必须在响应体里。
    """
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)

    def slow(ds, g, *, should_stop=None, **k):
        while not (should_stop and should_stop()):
            time.sleep(0.01)

    monkeypatch.setattr(cj, "run_calibration", slow)
    first = client.post("/api/calibration/jobs").json()
    r = client.post("/api/calibration/jobs")
    assert r.status_code == 409
    body = r.json()
    assert body["job_id"] == first["id"]
    assert isinstance(body["detail"], str), (
        "detail 必须是**一句话**：前端的 client.ts 拿 String(body.detail) 当报错文案，"
        "给它一个对象会印成 [object Object]")
    client.delete(f"/api/calibration/jobs/{first['id']}")
    _wait(lambda: client.get(f"/api/calibration/jobs/{first['id']}").json()["state"] != "running")


def test_没有这个任务时_404(client):
    assert client.get("/api/calibration/jobs/不存在的id").status_code == 404
    assert client.delete("/api/calibration/jobs/不存在的id").status_code == 404


# ── 取消之后盘上没变（T4，硬约束 2）──

def test_取消之后盘上逐位没变(client, tmp_path, monkeypatch):
    """T4：取消一次真跑起来的（替身）之后，包与 CSV 一个字节都不许变。

    盘上先放一份**同名**的真包：这样「写回会不会踩到它」这件事有个可观测的
    哨兵 —— 字节数与 mtime 只要有一处变了，就是取消没能拦住写。
    """
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)
    real = _real_bundle()
    target = tmp_path / f"bundle_{real.dataset_sig}_{real.groups_sig}.json"
    target.write_bytes('{"sentinel": "旧包"}'.encode())
    before = target.read_bytes()
    mtime = target.stat().st_mtime_ns

    def slow(ds, g, *, should_stop=None, **k):
        while not (should_stop and should_stop()):
            time.sleep(0.01)
        raise CalibrationAborted("阶段 2 试验之间被中断")

    monkeypatch.setattr(cj, "run_calibration", slow)
    job = client.post("/api/calibration/jobs").json()
    client.delete(f"/api/calibration/jobs/{job['id']}")
    _wait(lambda: client.get(f"/api/calibration/jobs/{job['id']}").json()["state"]
          != "running")

    assert target.read_bytes() == before, "取消之后包变了 —— 库的「中断不写盘」被绕过了"
    assert target.stat().st_mtime_ns == mtime
    assert not (tmp_path / (target.name + ".bak")).exists(), "取消不许留下 .bak"
    assert list(tmp_path.glob("sensitivity_*.csv")) == [], "取消不许留下参数曲面 CSV"
    assert jobs.get(job["id"]).result is None, (
        "取消了却把结果挂上去了 —— 挂上去等于这次取消只取消了一半")


def test_搜索跑完定下结果之前被取消_盘上什么都不留(client, tmp_path, monkeypatch):
    """**Review Focus 1**：搜索成功返回与「结果定下来」之间那一小段。

    人期待的是「已取消，什么都没发生」。这一段没有 `should_stop` 的问询点，
    靠的是 `_work` 在定下结果之前补的那一次检查 —— 把那次检查删掉，这条会红。
    """
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)
    real = _real_bundle()
    target = tmp_path / f"bundle_{real.dataset_sig}_{real.groups_sig}.json"

    holder: dict[str, jobs.Job] = {}

    def finish_then_user_cancels(ds, g, *, should_stop=None, **k):
        # 搜索成功返回的**那一瞬间**，用户点了取消
        holder["job"].cancel.set()
        return real

    monkeypatch.setattr(cj, "run_calibration", finish_then_user_cancels)
    holder["job"] = jobs.submit(cj._work)          # 绕过 409 那层，直接拿 job
    job = holder["job"]
    end = _wait(lambda: _settled(client, job.id))
    assert end["state"] == "cancelled"
    assert not target.exists(), "取消之后包不许出现"
    assert list(tmp_path.iterdir()) == []
    assert jobs.get(job.id).result is None, (
        "搜索跑完、取消检查之后被取消的那一次不许把结果挂上去")


# ── 备份的 .bak 不能被当成「上一次标定」（T8）──

@pytest.mark.empty_library
def test_bak_不被_mismatch_捡走(client, tmp_path, monkeypatch):
    """T8：`_mismatch` 用 `glob("bundle_*.json")`，`.json.bak` 不匹配。

    模式一旦被改宽（`bundle_*`），那一份备份就会冒充「上一次标定」，
    于是页② 会报出一份谁也不认识的包 —— 而它其实是同一份包的影子。

    ⚠️ **2026-10-08 保留这一条**（规格书 §5.6 把它算进了退场名单，那是把
    「跑完不再造 .bak」当成了「不用再防 .bak」）：它这里的 `.bak` 是**自己
    写上去的**，不依赖 `_work` 写回。盘上四份历史包还在，人手也可能造出
    一个 `.bak` —— 这个 glob 模式的守卫不该跟着写回一起退场。
    """
    from api.routes import calibration as cal_routes

    real = _real_bundle()  # 用来造那个 .bak 的**样本**，与库里的当前模型无关
    (tmp_path / f"bundle_{real.dataset_sig}_{real.groups_sig}.json.bak").write_text(
        real.to_json(), encoding="utf-8")
    monkeypatch.setattr(cal_routes, "CONFIGS_ROOT", tmp_path)
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()
    assert client.get("/api/calibration").json()["mismatch"] is None


# ── 刷新之后接得上（T3 的后半、§4.7）──

def test_跑着的时候_calibration_的_job_字段指得出它(client, tmp_path, monkeypatch):
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)

    def slow(ds, g, *, should_stop=None, **k):
        while not (should_stop and should_stop()):
            time.sleep(0.01)

    monkeypatch.setattr(cj, "run_calibration", slow)
    posted = client.post("/api/calibration/jobs").json()
    b = client.get("/api/calibration").json()
    assert b["job"] is not None
    assert b["job"]["id"] == posted["id"]
    assert b["job"]["state"] == "running"
    client.delete(f"/api/calibration/jobs/{posted['id']}")
    _wait(lambda: client.get(f"/api/calibration/jobs/{posted['id']}").json()["state"]
          != "running")


def test_一次都没跑过时_job_是_null(client):
    """反面的那一种：不许编一个 job 出来。

    这一格是**每次进页都要读**的载荷的一部分，所以它「有时有、有时没有」
    会让手写的夹具静默渲染成 undefined，而冒烟测试照样绿
    （与 `n_all_columns` 是同一个坑）。
    """
    b = client.get("/api/calibration").json()
    assert "job" in b
    assert b["job"] is None


# ── 标定跑着的时候服务还活着（T5，§4.2「不许推理，要实测」）──

def test_标定跑着的时候_health_在_2_秒内应答(client, tmp_path, monkeypatch):
    """防：把长任务跑在了请求线程上，或者占住了 GIL。

    替身里 `time.sleep` 会释放 GIL，所以这条测的是**我们有没有把活派到
    别的线程上**（真跑起来时 XGBoost 的 `n_jobs=-1` 与 numpy 也释放 GIL，
    但那是推理，不是观测 —— 这条测试能看的就是「派没派出去」）。
    """
    monkeypatch.setattr(cj, "CONFIGS_ROOT", tmp_path)

    def slow(ds, g, *, should_stop=None, **k):
        while not (should_stop and should_stop()):
            time.sleep(0.01)

    monkeypatch.setattr(cj, "run_calibration", slow)
    job = client.post("/api/calibration/jobs").json()

    t0 = time.monotonic()
    r = client.get("/api/health")
    took = time.monotonic() - t0
    assert r.status_code == 200
    assert took < 2.0, f"标定期间 /api/health 用了 {took:.2f}s —— 长任务挡住了请求"

    client.delete(f"/api/calibration/jobs/{job['id']}")
    _wait(lambda: client.get(f"/api/calibration/jobs/{job['id']}").json()["state"] != "running")
