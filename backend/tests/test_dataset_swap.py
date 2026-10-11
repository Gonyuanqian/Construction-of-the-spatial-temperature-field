"""换数据集：四样一起作废，一样都不能漏（规格书 §三.1）。

前三样由 `deps.reset_cache()` 自己管；第四样 —— 实时源 —— 不在那里，
而且 `live` 依赖 `deps`，反过来 import 成环，所以它**把自己登记进来**。
登记发生在 `api.live` 被 import 的那一刻，也就是「靠 import 顺序」——
本文件存在的唯一理由就是把它钉住，不靠推理。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, live, paths      # noqa: E402
from api.main import create_app        # noqa: E402
from tfield.data.loader import test_data_path  # noqa: E402

pytestmark = pytest.mark.skipif(not test_data_path().exists(),
                                reason="交付数据集不在（与 test_api_live.py 同一口径）")

ORIGINAL = test_data_path().read_bytes()


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(paths, "UPLOADS", tmp_path / "uploads")
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()
    live.reset_live_source()
    with TestClient(create_app()) as c:
        yield c
    deps.reset_cache()
    live.reset_live_source()
    deps.set_current_dataset(paths.dataset_path())


def _upload(client, name: str):
    return client.post("/api/dataset/upload", params={"name": name}, content=ORIGINAL,
                       headers={"Content-Type": "application/octet-stream"})


def test_实时源被作废(client):
    """T4：防「那个回调没登记上」。

    ⚠️ **不调 `prepare()`**：它真的要 fit 一次管线，几十秒。这一条测的是
    「登记生效了没有」，不是 prepare 的机制 —— 那由 `test_api_live.py` 覆盖
    （那里真的 prepare，并断言 `n_times == 1164`）。把一个「已经准备好」的
    实时源**直接装出来**，这条就变成一次瞬间的、确定的断言。
    """
    src = live.get_live_source()
    src.pipeline = object()                      # 装成「已经准备好」
    assert client.get("/api/live/status").json()["state"] == "ready"

    r = _upload(client, "换一份.xlsx")
    assert r.status_code == 200, r.text

    # 这里是**唯一**一处「作废」会让用户看见的地方（规格书 §六）。
    assert live.get_live_source() is not src
    assert client.get("/api/live/status").json()["state"] == "idle"


def test_四层缓存全清(client):
    """T5：防「只清了一半」。

    断言的是**对象换了**而不是计数归零：`reset_cache()` 重建 `_CACHE` /
    `_PIPELINES`，计数自然会从 0 重新开始 —— 拿计数看，一个「只清了一个」的
    实现也能显示 0。
    """
    deps.get_dataset()                 # 先让它装起来，好让「换没换」看得出来
    old_cache = deps._CACHE
    old_pipelines = deps._PIPELINES
    deps._HOLDOUTS[("哨兵", "哨兵")] = object()

    r = _upload(client, "另一份.xlsx")
    assert r.status_code == 200, r.text

    assert deps._CACHE is not old_cache
    assert deps._PIPELINES is not old_pipelines
    assert deps._HOLDOUTS == {}


def test_登记口是幂等的_重复登记不会叫两次():
    """`on_dataset_change` 是个累加列表：同一次 import 只发生一次，
    但测试里反复 import 同一个模块（`importlib.reload`）会重复登记。

    这一条钉住的是「重复登记**无害**」（回调是 `reset_live_source`，
    调两次只是把 `_SOURCE` 置空两次），不是「不许重复」。

    ⚠️ **收尾要把登记表还原**（计划原文只写了 `del calls`）。`_INVALIDATORS`
    是进程级的，`del calls` 删掉的只是本地名 —— 两个 lambda 的闭包仍然
    抓着那个列表，于是它此后每次 `reset_cache()` 都还在长。留着不报错，
    但那是**测试往全局状态里漏东西**，下一个读这张表的人会看见两条来历不明的
    回调。还原成进来时的样子，是把这条测试变成一次纯读。
    """
    saved = list(deps._INVALIDATORS)
    try:
        calls: list[int] = []
        deps.on_dataset_change(lambda: calls.append(1))
        deps.on_dataset_change(lambda: calls.append(1))
        deps.reset_cache()
        assert len(calls) == 2
    finally:
        deps._INVALIDATORS[:] = saved


def test_live_登记过了():
    """T4 的**根**：`api.live` 被 import 时确实登记了自己。

    没有这一条，上面那条 `test_实时源被作废` 也可能因为别的路径变绿
    （比如 `reset_live_source` 恰好被别处调了），而登记这条路其实断着。
    """
    assert live.reset_live_source in deps._INVALIDATORS


def test_启动路径上就会登记_不靠谁记得_import():
    """⚠️ 上面那两条**证明不了**这件事：本文件第 23 行就写着 `from api import live`，
    所以登记表非空是**这个测试文件自己**造成的。

    真正要成立的是：**只 import 生产入口**（`api.main`，也就是 uvicorn 走的那个）
    时登记也发生。若哪天 `api/routes/live.py` 改成从别处拿实时源（不再 import
    `api.live`），上面两条照旧全绿，而生产的进程里**登记表永远是空的** ——
    「换数据集忘了清实时源」原样复活，一条测试都不红。

    所以用子进程：一个新的解释器，除了 `api.main` 什么都不 import。
    这与 `test_api.py::test_不靠_pytest_的_pythonpath_也能_import_api` 同一个套路。
    """
    import os
    import subprocess

    code = (
        "import sys; sys.path[:0] = ['src', '.']\n"
        "import api.main\n"
        "from api import deps, live\n"
        "print(live.reset_live_source in deps._INVALIDATORS)\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().endswith("True"), r.stdout + r.stderr
