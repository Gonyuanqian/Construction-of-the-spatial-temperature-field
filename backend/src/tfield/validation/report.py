"""端到端折外评估。

各区域证据强度不同（R4），所以报告按区域分列，不给单一数字：
- 切面内     实测   —— 0.031 ~ 0.042
- 断面之间   推导   —— 有日照 ≈0.09、无日照 ≈0.02
- 棚长端部   无依据 —— 只标注不定值，不给数字

evaluate 收的是**工厂函数**，不是训练好的管线：每一折都必须用那一折的排除集重新训练。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
import pandas as pd

from .. import config as C
from ..data.types import Dataset
from ..features import build_features
from ..pipeline import FieldPipeline
from .folds import Fold, fold_kind
from .metrics import metrics_row

_REGION_BY_KIND = {
    "position": "切面内",
    "section": "断面之间",
}


@dataclass(frozen=True)
class ABResult:
    mae_a: float        # A 组：被调过参的位置
    mae_b: float        # B 组：未参与选参的位置
    gap: float          # = mae_a − mae_b，调参带来的乐观偏差


@dataclass(frozen=True)
class EvalResult:
    metrics: pd.DataFrame
    per_point: pd.DataFrame
    ab: ABResult | None


def region_of(fold_name: str) -> str:
    """折名 → 区域标签。region 折保留块名（left/right/low/high）作为区域。"""
    return _REGION_BY_KIND.get(fold_kind(fold_name), fold_name)


def ab_from(rows: Sequence[dict]) -> ABResult | None:
    a = [r["mae"] for r in rows if r.get("group") == "A"]
    b = [r["mae"] for r in rows if r.get("group") == "B"]
    if not a or not b:
        return None
    ma, mb = float(np.mean(a)), float(np.mean(b))
    return ABResult(mae_a=ma, mae_b=mb, gap=ma - mb)


def evaluate(make_pipe: Callable[[], FieldPipeline], ds: Dataset,
             folds: Sequence[Fold], *,
             groups=C.DEFAULT_FEATURE_GROUPS, tag: str = "") -> EvalResult:
    """对每折重新训练并预测被留出的传感器。全部为折外结果。"""
    if isinstance(make_pipe, FieldPipeline):
        raise TypeError(
            "evaluate() 需要的是【工厂函数】（每折重新构造并训练），"
            "收到的是已构造的管线实例。传 lambda: FieldPipeline(cfg, ds)。"
        )

    fs = build_features(ds, groups)
    # ⚠️ 长度取**这一份数据集**的，不取 `C.EXPECTED_ROWS`。
    # 全量数据集上两者相同（1308），但留出之后在**训练段**上评估时
    # 训练段只有 1164 行 —— 写死就会让预测要走的那 1308 个时刻
    # 落到只有 1164 个元素的气象列上：不是崩溃，是一条形状错位的静默错误。
    ti = np.arange(len(ds.wide))
    rows: list[dict] = []
    per_point: list[dict] = []

    for fold in folds:
        pipe = make_pipe().fit(fs, ds, exclude=fold.test_sensors)
        coords = fs.coords[list(fold.test_sensors)]
        pred = pipe.predict_points(coords, ti)
        truth = np.stack([fs.y[fs.sensor_id == s] for s in fold.test_sensors])

        row = metrics_row(truth.ravel(), pred.ravel())
        row.update({"fold_kind": fold_kind(fold.name), "fold": fold.name,
                    "region": region_of(fold.name), "group": fold.group or "",
                    "n": int(truth.size), "tag": tag})
        rows.append(row)

        for i, sensor in enumerate(fold.test_sensors):
            shed, pos = ds.sensor_ids()[sensor][1], ds.sensor_ids()[sensor][2]
            per_point.append({
                "sensor_id": sensor, "shed": shed, "position": pos,
                "layer": ds.layout[pos].layer, "group": fold.group or "",
                "n": int(truth[i].size),
                **metrics_row(truth[i], pred[i]),
            })

    return EvalResult(metrics=pd.DataFrame(rows),
                      per_point=pd.DataFrame(per_point),
                      ab=ab_from(rows))
