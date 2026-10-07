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


def _oof_folds(make_pipe: Callable[[], FieldPipeline], ds: Dataset,
               folds: Sequence[Fold],
               groups=C.DEFAULT_FEATURE_GROUPS,
               ) -> list[tuple[Fold, np.ndarray, np.ndarray]]:
    """逐折重新训练并预测被留出的传感器。**折外预测只有这一处循环。**

    产出 `(fold, truth, pred)`，两个数组都是 `(n_test_sensors, n_times)`。

    抽出来是因为本文件有两个消费者：`evaluate` 要它的**聚合**（逐折指标），
    `out_of_fold_predictions` 要它的**原始行**（散点、残差）。写成两份循环
    不会报错，只会让「折外预测」在这份代码里有两个定义，然后慢慢漂开。
    """
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

    out: list[tuple[Fold, np.ndarray, np.ndarray]] = []
    for fold in folds:
        pipe = make_pipe().fit(fs, ds, exclude=fold.test_sensors)
        coords = fs.coords[list(fold.test_sensors)]
        pred = pipe.predict_points(coords, ti)
        truth = np.stack([fs.y[fs.sensor_id == s] for s in fold.test_sensors])
        out.append((fold, truth, pred))
    return out


def evaluate(make_pipe: Callable[[], FieldPipeline], ds: Dataset,
             folds: Sequence[Fold], *,
             groups=C.DEFAULT_FEATURE_GROUPS, tag: str = "") -> EvalResult:
    """对每折重新训练并预测被留出的传感器。全部为折外结果。"""
    rows: list[dict] = []
    per_point: list[dict] = []

    for fold, truth, pred in _oof_folds(make_pipe, ds, folds, groups):
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


#: `out_of_fold_predictions` 的列。**顺序即契约** —— 加列要连测试一起改。
OOF_COLUMNS = ("sensor_id", "shed", "position", "layer", "group",
               "fold", "t_index", "truth", "pred")


def out_of_fold_predictions(make_pipe: Callable[[], FieldPipeline], ds: Dataset,
                            folds: Sequence[Fold], *,
                            groups=C.DEFAULT_FEATURE_GROUPS) -> pd.DataFrame:
    """逐折重新训练并预测被留出的传感器，返回**逐点逐时刻**的折外预测。

    列见 `OOF_COLUMNS`；行数 = 参与评估的测点数 × 时刻数。

    它只做一件事：把 `_oof_folds` 的两个数组摊平成长表，**不做任何聚合**
    —— 聚合是消费者的事（`evaluate` 聚成指标，页② 的诊断聚成分箱）。
    """
    chunks: list[pd.DataFrame] = []
    for fold, truth, pred in _oof_folds(make_pipe, ds, folds, groups):
        for i, sensor in enumerate(fold.test_sensors):
            shed, pos = ds.sensor_ids()[sensor][1], ds.sensor_ids()[sensor][2]
            chunks.append(pd.DataFrame({
                "sensor_id": sensor, "shed": shed, "position": pos,
                "layer": ds.layout[pos].layer, "group": fold.group or "",
                "fold": fold.name, "t_index": np.arange(truth[i].size),
                "truth": truth[i], "pred": pred[i],
            }))
    if not chunks:
        # 零折：给一张**列齐全**的空表。缺列会在调用方很远的地方炸。
        return pd.DataFrame({c: pd.Series(dtype=float) for c in OOF_COLUMNS})
    return pd.concat(chunks, ignore_index=True)
