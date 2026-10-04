"""页① 的三条图形数据接口。

这一组测试里最重要的**不是**形状，是两条：
(1) 拱线必须与 `tfield.field.arch` **逐位相等** —— 后端库就是那个 oracle，
    前端不许自己算拱（算错了不会报错，只会画出一个不是这座棚的棚）；
(2) 响应体里不许出现 `NaN` / `Infinity` 字面量 —— Starlette 的 JSONResponse
    用 allow_nan=False，真出现了会变成 500，而错误发生在序列化阶段，
    看起来像框架故障（Review Focus #1）。
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api.main import create_app                          # noqa: E402
from tfield import config as C                           # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _assert_no_nan_tokens(resp):
    """原始响应体里不许出现这三个字面量。"""
    text = resp.text
    for tok in ("NaN", "Infinity", "-Infinity"):
        assert tok not in text, f"响应体里出现了 {tok} —— 那是非法 JSON，真发出去就是 500"


# ── Starlette 的限制本身 ──

def test_Starlette_拒绝_NaN_这条限制是真的():
    """Review Focus #1。这不是我们的代码，是一条**踩上去才知道**的环境事实。

    把它钉成测试的理由：页③ 的拱外 NaN 一定会撞上它。到那时，
    这条测试会立刻告诉人「不是你哪里写错了，是这个限制」。
    """
    from starlette.responses import JSONResponse
    with pytest.raises(ValueError):
        JSONResponse({"v": float("nan")})
    with pytest.raises(ValueError):
        JSONResponse({"v": [1.0, math.inf]})


# ── 拱线 ──

def test_拱线与后端库逐位相等(client):
    r = client.get("/api/field/arch")
    assert r.status_code == 200
    _assert_no_nan_tokens(r)
    body = r.json()

    from tfield.field.arch import arch_height
    xs = np.array([p[0] for p in body["arch"]], dtype=float)
    zs = np.array([p[1] for p in body["arch"]], dtype=float)
    assert np.array_equal(zs, arch_height(xs)), "拱线不是后端库算的那条"
    assert body["x_min"] == C.SHED_X_MIN and body["x_max"] == C.SHED_X_MAX
    assert body["z_max"] == C.SHED_Z_MAX
    assert body["max_measured_z"] == C.MAX_MEASURED_Z == 1.10
    # 拱脚落在 z ≈ 0.4535（spec §七 V7 那条几何）
    assert body["arch"][0][1] == pytest.approx(0.4535, abs=1e-3)
    assert [s["id"] for s in body["sheds"]] == list(C.SHED_ORDER)
    assert [s["y"] for s in body["sheds"]] == [C.SHED_Y[s] for s in C.SHED_ORDER]


# ── 时序 ──

def test_时序接口的两格数据齐全(client):
    r = client.get("/api/dataset/timeseries")
    assert r.status_code == 200
    _assert_no_nan_tokens(r)
    b = r.json()

    assert b["n_times"] == 1308
    assert len(b["time"]) == 1308
    assert len(b["bg_temp"]) == 1308
    assert len(b["sensors"]) == 24 and len(b["detrended"]) == 24
    assert len(b["shed_mean"]) == 3 and len(b["detrended_mean"]) == 3
    assert all(len(v) == 1308 for v in b["sensors"].values())
    assert all(len(v) == 1308 for v in b["detrended"].values())
    assert set(b["shed_mean"]) == set(C.SHED_ORDER)


def test_减背景是后端算的且与实测自洽(client):
    """Review Focus #4：前端不许做这个减法。

    这里验的是**后端减对了**：detrended == 棚温 − 背景。前端那边另有一条测试，
    喂一份「两者故意不一致」的假数据，页面必须显示后端给的那个。
    """
    b = client.get("/api/dataset/timeseries").json()
    for key, series in b["detrended"].items():
        raw = b["sensors"][key]
        for i in (0, 300, 700, 1307):
            assert series[i] == pytest.approx(raw[i] - b["bg_temp"][i], abs=1e-9)
    assert b["detrended_domain"] == [-3.0, 3.0]
    # 那句说明必须在：它是「减法发生在后端」这件事的书面凭据
    assert "后端" in b["note"] and "减法" in b["note"]


def test_棚间均值是后端算的(client):
    b = client.get("/api/dataset/timeseries").json()
    for shed, series in b["shed_mean"].items():
        cols = [v for k, v in b["sensors"].items() if k.startswith(f"{shed}|")]
        assert len(cols) == 8
        for i in (0, 1307):
            assert series[i] == pytest.approx(
                sum(c[i] for c in cols) / len(cols), abs=1e-9)


# ── 时间 × 高度 ──

def test_时间高度热图用实测值且分层正确(client):
    r = client.get("/api/dataset/layer-timeheight")
    assert r.status_code == 200
    _assert_no_nan_tokens(r)
    b = r.json()

    assert b["step"] >= 1
    assert b["n_columns"] == len(b["time"])
    assert set(b["sheds"]) == set(C.SHED_ORDER)
    for shed, d in b["sheds"].items():
        # 四行：z0.4 / z0.7 各三点合成一行，拱顶两点高度相同、x 不同，分开列
        assert d["labels"] == ["z0.4", "z0.7", "zH(0.80)", "zH(1.30)"], shed
        assert d["z"] == [0.4, 0.7, 1.1, 1.1]
        assert len(d["values"]) == 4
        assert all(len(row) == b["n_columns"] for row in d["values"])


def test_时间高度热图的值就是实测温度(client):
    """这条测试是「用实测不用预测」这句话的凭据。

    取该棚 z0.7 那一层 —— 它的三个测点在原表里是现成的列，
    逐点对一遍，热图里那一行必须等于它们**实测值**的均值。
    若哪天有人把它改回 `pipe.predict_points`，这条立刻红。
    """
    from tfield.data.loader import load_dataset, test_data_path
    b = client.get("/api/dataset/layer-timeheight").json()
    ds = load_dataset(test_data_path())
    cols = ["p1_x0.4_z0.7_temp_C", "p1_x1.05_z0.7_temp_C", "p1_x1.7_z0.7_temp_C"]
    for c in cols:
        assert c in ds.wide.columns, f"{c} 不在了 —— 测点表变过了，这条测试要跟着改"
    row = b["sheds"]["p1"]["labels"].index("z0.7")
    # 用抽稀后的列号回推原表行号
    idx = [i * b["step"] for i in range(b["n_columns"])]
    for j in (0, 1, b["n_columns"] - 1):
        expect = float(ds.wide[cols].to_numpy(float)[idx[j]].mean())
        assert b["sheds"]["p1"]["values"][row][j] == pytest.approx(expect, abs=1e-9)


def test_响应可以直接被_json_dumps_出来(client):
    """最后一道：拿标准库再序列化一遍，NaN 会在这里现形。"""
    for path in ("/api/field/arch", "/api/dataset/timeseries",
                 "/api/dataset/layer-timeheight"):
        r = client.get(path)
        # 先断言 200：否则 404 的 `{"detail": ...}` 本身就能被序列化，
        # 这条测试会在接口还没实现时**空过** —— 它要验的是响应体，不是错误体。
        assert r.status_code == 200, path
        json.dumps(r.json(), allow_nan=False)      # 抛错就是有 NaN
