"""两条流水线走通一次：页① 与页② 各自要的所有数据都拿得到。

这一条不是「再多测一个端点」，它测的是**页面**：一个页面要打的全部接口
一次打完，全都通 —— 少一个，那一页就是半张白屏。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api.main import create_app                          # noqa: E402

PAGE_1 = ["/api/dataset", "/api/field/arch",
          "/api/dataset/timeseries", "/api/dataset/layer-timeheight"]
PAGE_2 = ["/api/features", "/api/calibration"]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize("path", PAGE_1 + PAGE_2 + ["/api/health"])
def test_每个接口都通且是合法_JSON(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} 返回 {r.status_code}：{r.text[:200]}"
    assert "NaN" not in r.text and "Infinity" not in r.text


def test_页1要的四个接口一起打(client):
    for path in PAGE_1:
        assert client.get(path).status_code == 200, path


def test_页2要的两个接口一起打(client):
    for path in PAGE_2:
        assert client.get(path).status_code == 200, path


def test_缓存让第二次全量请求快得多(client):
    """页① 打四个接口。第一次要读 xlsx，之后不该再读。

    这是**粗兜底**，别删。它抓得住「缓存整体坏掉」；但本机 cold≈0.8 s、
    热三个≈0.8 s，合计仍 < 1.5 s —— **单个端点绕开缓存它抓不住**。
    直接的判据在下面那条（计数加载器）。
    """
    import time

    client.get("/api/dataset")            # 预热，保证缓存里有了
    t0 = time.time()
    for path in PAGE_1:
        client.get(path)
    elapsed = time.time() - t0
    assert elapsed < 1.5, f"四个接口花了 {elapsed:.2f} s —— 缓存没吃上"


@pytest.mark.parametrize("first", PAGE_1)
def test_四个接口共用同一份缓存_合计只加载一次(monkeypatch, client, first):
    """**直接的判据**（评审 3a）：缓存重置后连打页① 的四个端点，合计只加载一次。

    照 `test_deps.py::test_api_的数据集接口真的走了缓存` 的计数加载器写法 ——
    把 `api.deps._CACHE` 换成一台带计数的**真**缓存（返回真 Dataset，不是假对象：
    路由拿到它要读 wide / sheds / layout 才拼得出响应体）。

    ⚠️ **计数要装在两处**：只换 `_CACHE` 的话，计数发生在**缓存命中路径**上，
    一个端点若绕开缓存直接 `load_dataset()`，那次加载根本不过计数器 ——
    合计仍是 1，测试静默放行（这正是自评时踩到的）。所以同时把
    `tfield.data.loader.load_dataset` 也换成计数版，把「绕过缓存的直接调用」
    一并数进来。局限：若某路由在**模块顶层** `from tfield.data.loader import
    load_dataset`，那个绑定在 monkeypatch 之前就固定了，数不到；本项目四个路由
    都走 `deps`，不受影响。

    参数化 `first` 是让四个端点轮流当第一个请求：任何一种次序下合计都必须是 1。
    """
    import tfield.data.loader as loader_mod

    from api import deps
    from api.deps import DatasetCache

    real_load = loader_mod.load_dataset
    calls: list[pathlib.Path] = []

    def counting(path):
        calls.append(pathlib.Path(path))
        return real_load(path)

    monkeypatch.setattr(loader_mod, "load_dataset", counting)             # 直接调用
    monkeypatch.setattr(deps, "_CACHE", DatasetCache(loader=counting))   # 经由缓存

    order = [first] + [p for p in PAGE_1 if p != first]
    for path in order:
        assert client.get(path).status_code == 200, path
    assert len(calls) == 1, (
        f"页① 的四个端点合计加载了 {len(calls)} 次数据集 —— 有的接口绕开了缓存"
        f"（首个请求：{first}）"
    )



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
