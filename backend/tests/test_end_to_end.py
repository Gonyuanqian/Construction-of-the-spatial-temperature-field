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
    """页① 打四个接口。第一次要读 xlsx（2.7–3.3 s），之后不该再读。"""
    import time

    client.get("/api/dataset")            # 预热，保证缓存里有了
    t0 = time.time()
    for path in PAGE_1:
        client.get(path)
    elapsed = time.time() - t0
    assert elapsed < 1.5, f"四个接口花了 {elapsed:.2f} s —— 缓存没吃上"
