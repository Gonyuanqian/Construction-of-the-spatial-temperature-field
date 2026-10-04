"""真实响应体上的**上屏文案**守卫：禁用的连接符与 markdown 标记一个都不许漏。

**为什么需要它**（评审 R9 留的缺口）：前端那条六项扫描
（`frontend/src/routes.smoke.test.ts`）扫的是 **mock 载荷** —— mock 里
`checks: []`、`checks_note: ''`、`notes: []`，所以页① 与 features 由**真实后端**
产出的文案一条都没进扫描。后端唯一的同名守卫
（`test_api_train.py::test_上屏文案干净_...`）只扫 `/api/calibration`。

结果：下面这些字段**会上屏，却两条守卫都盖不到** ——
`/api/dataset` 的 `checks[].name/what/evidence` 与 `checks_note`、
`/api/dataset/timeseries` 的 `note`、`/api/dataset/layer-timeheight` 的
`source/x_label`、`/api/features` 的 `groups[].what/columns` 与 `notes`。

**扫的六项与 `test_api_train.py` 完全一致**：`"——"`、`"**"`、`` "`" ``、
`" · "`、`"→"`、`"↳"`。**不扫单个 `—`**：那是表格里「无值」的有意占位，
spec §8.5 禁的是两侧带空格的破折号。

**为什么要「非空 + 已知片段」断言**：真实文案当前是干净的，所以这条守卫
今天不会红 —— 它在空串上跑 `not in` 永远绿，那种守卫没有意义。所以先断言
抽出来的文本确实非空、且含有已知片段：提取口径一旦失效（字段改名、响应变空），
这条守卫自己先红，而不是变成一次静默的空过。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api.main import create_app                          # noqa: E402

#: 与 `test_api_train.py` 逐字一致。
BANNED = ("——", "**", "`", " · ", "→", "↳")

#: 每个端点「会上屏的纯文本字段」怎么抽。抽的是**响应体里的**那一份，
#: 不是后端源码里的字面量 —— 守卫要盯的是最终送到页面的东西。
_EXTRACTORS = {
    "/api/dataset": lambda b: (
        [c["name"] for c in b["checks"]]
        + [c["what"] for c in b["checks"]]
        + [c["evidence"] for c in b["checks"]]
        + [b["checks_note"]]
    ),
    "/api/dataset/timeseries": lambda b: [b["note"]],
    "/api/dataset/layer-timeheight": lambda b: [b["source"], b["x_label"]],
    "/api/features": lambda b: (
        [g["what"] for g in b["groups"]]
        + [c for g in b["groups"] for c in g["columns"]]
        + list(b["notes"])
    ),
}

#: 每个端点必须确实出现的一段已知文案。它证明上面的提取口径还咬得住真数据。
_REQUIRED_FRAGMENTS = {
    "/api/dataset": ("结构完整性", "时间轴", "缺失", "值域"),
    "/api/dataset/timeseries": ("棚温减背景", "后端"),
    "/api/dataset/layer-timeheight": ("实测棚温", "时刻"),
    "/api/features": ("场的基本骨架", "滞后", "湿度"),
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize("path", sorted(_EXTRACTORS))
def test_真实响应体上屏的文案干净(client, path):
    body = client.get(path).json()
    texts = _EXTRACTORS[path](body)
    joined = "".join(texts)

    # 有牙的前提：确有文本可扫。
    assert joined.strip(), f"{path} 没抽到任何上屏文本 —— 提取口径失效了，守卫成了空过"
    for frag in _REQUIRED_FRAGMENTS[path]:
        assert frag in joined, f"{path} 的文案里少了「{frag}」—— 提取口径与现实分家了"

    for s in texts:
        for bad in BANNED:
            assert bad not in s, f"{path} 的上屏文案里出现了被禁的 {bad!r}：{s!r}"
