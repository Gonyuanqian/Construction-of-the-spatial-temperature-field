"""页① 的数据预览出口：`GET /api/dataset/preview`。

它要回答的是四个统计数回答不了的那句话 ——「我导进来的确实是这份文件」。
所以要能看到行和列本身，而宽表只能由后端切好送过来（spec §六 硬约束 1）。

这一组里最要紧的两条：

(1) **列标签与切面图上的 B 编号同源。** 页① 现在把切面图与预览表并排摆
    在同一行上，整个左右分栏的意义就是「图上的 B3 就是表里的那一列」。
    两边各排各的编号不会报错，只会让人在两张图上读到两个 B3。
(2) **截断是明说的。** 接口同时给 `n_rows` 与 `n_times`，页面才写得出
    「前 500 行（共 1308 行）」。只给一个 `values` 数组的话，屏幕上看不出
    看到的是全部还是一段 —— 那种沉默比截断本身更坏。
"""
from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, paths                        # noqa: E402
from api.main import create_app                    # noqa: E402
from tfield import config as C                     # noqa: E402

N_TIMES = 1308


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _current_dataset():
    """空态成为默认之后，碰数据集的模块都得**显式声明**它测的是哪一份。

    与 `test_api_series.py` 的同名夹具逐字相同，理由见那一段：本仓有 12 处
    在测试里内联建 `TestClient`，改 `client` 夹具会漏掉它们，所以写成 autouse。
    """
    deps.set_current_dataset(paths.dataset_path())


@pytest.fixture(scope="module")
def xlsx() -> pd.DataFrame:
    """原文件，**独立读一遍**当 oracle。

    不用 `deps.get_dataset()`：那是被测代码正在用的那一份缓存对象，
    拿它当 oracle 等于让接口跟自己对答案。这里直接读盘。
    """
    return pd.read_excel(paths.dataset_path(), sheet_name=C.SHEET_MAIN)


def _preview(client: TestClient, query: str = "") -> dict:
    r = client.get(f"/api/dataset/preview{query}")
    # 先断言 200：否则错误体 `{"detail": ...}` 自己也能被 json 序列化，
    # 下面的用例会在接口还没实现时**空过**。
    assert r.status_code == 200, r.text
    return r.json()


def _assert_no_nan_tokens(resp) -> None:
    """原始响应体里不许出现这三个字面量。

    与 `test_api_series.py` 的同名助手同源。重复一份不是懒：它讲的是一条
    **环境事实**（Starlette 的 `JSONResponse(allow_nan=False)`），而这条
    出口给的是 500×25 个实测浮点里的一个切片 —— 缺失格子一定会撞上它，
    正是最该被验的那一种响应。
    """
    for tok in ("NaN", "Infinity", "-Infinity"):
        assert tok not in resp.text, f"响应体里出现了 {tok} —— 那是非法 JSON，真发出去就是 500"


# ── 列 ──

def test_列是背景加二十四个测点(client):
    b = _preview(client)
    labels = [c["label"] for c in b["columns"]]
    assert labels[0] == "背景温度"
    assert labels[1:] == [f"{s}·B{i}" for s in C.SHED_ORDER for i in range(1, 9)]


def test_列标签与数据集的测点编号同源(client):
    """标签里的 B 编号**必须**是 `_point_codes` 排出来的那一个。

    页① 图与表并排摆着，这一条就是「图上的 B3 与表里的 B3 是同一个点」
    这件事的唯一保障。
    """
    codes = client.get("/api/dataset").json()["point_codes"]
    for c in _preview(client)["columns"][1:]:
        shed = c["key"].split("_", 1)[0]
        pos = c["key"][len(shed) + 1: -len(f"_{C.VAR_TEMP}")]
        assert c["label"] == f"{shed}·{codes[pos]}", c


def test_列名是宽表里的列名_不是另起一套(client, xlsx):
    """`key` 是**文件里的列名**，所以表里任何一格都还追得回原文件那一列。

    列名若也换成人看的字，这张表就成了自成一体的东西 —— 对不上文件时，
    看的人没有第二条线索可用。
    """
    for c in _preview(client)["columns"]:
        assert c["key"] in xlsx.columns, c


def test_湿度与光照不进表(client):
    """本系统没有一处读湿度与光照。

    摆进来是 25 列变 49 列 —— 宽度翻倍，读到的东西不变。
    """
    keys = {c["key"] for c in _preview(client)["columns"]}
    assert C.BG_LIGHT not in keys
    assert not any(k.endswith(f"_{C.VAR_RH}") for k in keys)


# ── 行数：截断与它的边界 ──

def test_默认给前五百行(client):
    b = _preview(client)
    assert b["n_times"] == N_TIMES
    assert b["limit"] == 500
    assert b["n_rows"] == 500
    assert len(b["time"]) == 500
    assert len(b["values"]) == 500


@pytest.mark.parametrize("query,want", [
    ("?limit=100", 100),
    ("?limit=0", 0),          # 零行是合法请求，不是「没传」
    ("?limit=-5", 0),         # 负数按 0，不按默认的 500 —— 静默放大是另一种撒谎
    ("?limit=99999", N_TIMES),  # 超出按总行数；这份数据 1308 行，不另设魔法上界
])
def test_limit_被夹在零与总行数之间(client, query, want):
    b = _preview(client, query)
    assert b["limit"] == want, query
    assert b["n_rows"] == want, query
    assert len(b["values"]) == want, query
    assert len(b["time"]) == want, query


def test_limit_不是整数是_422(client):
    """`limit` 是 int 查询参数，不是字符串 —— 这一条钉死它的类型。"""
    assert client.get("/api/dataset/preview?limit=abc").status_code == 422


def test_零行时不塌(client):
    """空切片也要是一个**形状正确**的响应：列还在，说得出自己的形状。"""
    b = _preview(client, "?limit=0")
    assert b["columns"]
    assert b["values"] == []
    assert b["time"] == []


# ── 时间列 ──

def test_起点与数据集报的起点是同一行(client):
    b = _preview(client)
    assert b["time"][0] == client.get("/api/dataset").json()["time_start"]


def test_时间列严格递增(client):
    """这一条顺带说出「表里读到的轴是修过的那一条」。

    原始文件里第 60、348… 行被写成次日 00:00，修完才单调。表上若是原样，
    看的人会以为数据是乱的。
    """
    t = _preview(client)["time"]
    assert t == sorted(t) and len(set(t)) == len(t)


# ── 矩阵 ──

def test_每一格都能追回文件里的那一列(client, xlsx):
    """全列 × 首行/次行/末行逐位比对。

    这是整个文件里唯一一条拿**盘上的原文件**当 oracle 的用例 —— 其余都
    只验形状与来源。形状对而数错，在屏幕上看起来和对的一模一样。
    """
    b = _preview(client)
    for ci, c in enumerate(b["columns"]):
        col = xlsx[c["key"]]
        for ri in (0, 1, len(b["values"]) - 1):
            got = b["values"][ri][ci]
            want = col.iloc[ri]
            if pd.isna(want):
                assert got is None, f"{c['key']} 第 {ri} 行：缺失该印成 null，不是 {got!r}"
            else:
                assert got == pytest.approx(float(want)), f"{c['key']} 第 {ri} 行"


def test_每行的长度等于列数(client):
    b = _preview(client)
    assert all(len(row) == len(b["columns"]) for row in b["values"])


def test_响应体里没有非有限字面量(client):
    """缺失格子会是 NaN —— 它必须在序列化之前翻成 null（见 `_finite`）。"""
    r = client.get("/api/dataset/preview")
    assert r.status_code == 200
    _assert_no_nan_tokens(r)
    json.dumps(r.json(), allow_nan=False)
