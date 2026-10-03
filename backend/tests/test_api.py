"""API 层的契约。

走 TestClient（进程内），不起真服务器 —— 契约测试不该依赖端口与进程管理。
真起服务器是 Task 6 的端到端验收。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api.main import create_app            # noqa: E402
from api import paths                      # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_数据集接口报得出身份(client):
    r = client.get("/api/dataset")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signature"] and len(body["signature"]) == 16
    assert body["n_times"] == 1308
    assert body["n_columns"] == 52
    assert set(body["sheds"]) == {"p1", "p2", "p3"}
    assert body["sheds"]["p2"] == 9.0
    assert len(body["positions"]) == 8
    # 用集合而不是下标：字典的插入顺序是 loader 的实现细节，
    # API 从没承诺过顺序，拿 [0] 断言会把「换了个遍历写法」变成测试失败。
    # 这 8 个 id 来自 C.SENSOR_LAYOUT 的键，含三个带括号的 ztop 点。
    assert {p["id"] for p in body["positions"]} == {
        "x0.15_z0.4", "x0.4_z0.7", "x0.8_zH(0.80)-0.20", "x1.05_z0.4",
        "x1.05_z0.7", "x1.3_zH(1.30)-0.20", "x1.7_z0.7", "x1.95_z0.4",
    }
    assert all(set(p) == {"id", "x", "z", "layer"} for p in body["positions"])
    # ztop 点的 z 是 1.1（MAX_MEASURED_Z），不是拱高 —— 别把层名当高度
    top = next(p for p in body["positions"] if p["layer"] == "ztop")
    assert top["z"] == 1.1

    assert body["time_start"] == "2026-07-23T11:00:00"
    assert body["time_end"] == "2026-07-27T23:55:00"


def test_数据集接口报出时间戳修复(client):
    """时间轴修复的 5 行（16:00 被写成次日 00:00）必须原样透出来，
    否则 ① 页的「六项校验」就没有数据可报。"""
    r = client.get("/api/dataset")
    fix = r.json()["fix"]
    assert fix["n_rows"] == 1308
    assert fix["fixed_indices"] == [60, 348, 636, 924, 1212]
    assert fix["monotonic_before"] is False    # 不修就是不单调，这正是不修不行的理由
    assert fix["monotonic_after"] is True
    assert fix["spacing_seconds"] == 300.0     # 5 分钟采样
    assert fix["n_gaps"] == 0


def test_端口配置是_8503_不是别的():
    """Review Focus #5：不许悄悄落到别的端口上。"""
    assert paths.API_PORT == 8503


def test_configs_是绝对路径():
    """Ruling：API 层不能用依赖 CWD 的相对路径。"""
    assert paths.CONFIGS.is_absolute()
    assert paths.CONFIGS.name == "configs"
    assert paths.CONFIGS.parent.name == "backend"


def test_数据集不存在时报_404_而不是_500(client, monkeypatch):
    monkeypatch.setattr(paths, "dataset_path",
                        lambda: pathlib.Path("C:/definitely/not/here.xlsx"))
    r = client.get("/api/dataset")
    assert r.status_code == 404
    assert "数据集不存在" in r.json()["detail"]


def test_dist_不存在时应用照样起得来(tmp_path, monkeypatch):
    """Review Focus #5 的近亲：静态托管的守卫。

    StaticFiles 在目录不存在时**构造就抛错**。若不加守卫，一个没跑过
    npm run build 的人连 /api/health 都调不到 —— 症状是「后端起不来」，
    而真正的原因在前端没构建。这条钉住那个守卫。
    """
    monkeypatch.setattr(paths, "DIST", tmp_path / "并不存在的 dist")
    app = create_app()                       # 不抛异常
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}


def test_dist_存在时根路径返回_index_html(tmp_path, monkeypatch):
    """生产形态：一个进程同时供 API 与前端（spec §二）。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>温度场</h1>", encoding="utf-8")
    monkeypatch.setattr(paths, "DIST", dist)
    app = create_app()
    c = TestClient(app)
    assert "温度场" in c.get("/").text
    # 挂载点在最后注册，不许把 /api 吃掉
    assert c.get("/api/health").json() == {"status": "ok"}
