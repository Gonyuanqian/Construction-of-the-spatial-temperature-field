"""页② 第一段：特征值的构造。

这一段的产出是一张表 —— 但表里的**列名不是这里写的**，
是从 `tfield.features.add_feature_groups` 那里问出来的。
手抄一份列名的话，将来有人加一个特征，界面上的表会静默过期，
而它看起来还是对的。
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter

from tfield import config as C
from tfield.features import add_feature_groups

from .. import ported

router = APIRouter(tags=["features"])

#: 只为了问出「每一组会产出哪些列名」而存在的一行零。
#: **它不是数据，从不进模型** —— 与 `app/app.py:420` 的 `_ZERO_LONG` 同一个手法。
_ZERO_LONG = pd.DataFrame({k: [0.0] for k in
                           ("x", "y", "z", "bg_temp", "bg_rh", "bg_light",
                            "hour", "frac_day")})

#: 两条「刻意没做的事」。与 `tfield/features.py` 的模块说明同源，
#: 有测试盯着那边还在（`test_api_train.py::test_两条不加特征的说明在`）。
NOTES = (
    "不加滞后特征：本版是重建任务，同时刻的气象量已知。",
    "不加测点湿度：目标点的湿度同样是未知量，不能拿来当输入。",
)


@router.get("/features")
def get_features() -> dict[str, Any]:
    """四组特征各产出哪些列，以及每组在说什么。"""
    groups = []
    for g in C.DEFAULT_FEATURE_GROUPS:
        cols = [str(c) for c in add_feature_groups(_ZERO_LONG, (g,)).columns]
        groups.append({
            "group": g,
            "columns": cols,
            "n_columns": len(cols),
            "what": ported.FEATURE_GROUP_WHAT.get(g, ""),
        })
    union: list[str] = []
    for g in groups:
        for c in g["columns"]:
            if c not in union:
                union.append(c)
    return {
        "default_groups": list(C.DEFAULT_FEATURE_GROUPS),
        "groups": groups,
        "all_columns": union,
        #: 全列清单的列数。**必须由后端报**：前端 `all_columns.length` 是前端在做
        #: 计数，撞「前端不做任何数值计算」；而「各组 n_columns 之和」与「并集长度」
        #: 组分一旦重叠就会静默不一致。并集长度只有这里一个真源。
        "n_all_columns": len(union),
        "notes": list(NOTES),
    }
