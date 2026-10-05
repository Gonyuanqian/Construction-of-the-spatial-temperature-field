"""实时帧接进时间轴：时间轴访问器 + append_live_frame。

⚠️ 这个文件用一个**只够用的假数据集**（12 帧），不读那个 1308 × 52 的 xlsx：
`fit` 在 24 × 12 = 288 行的长表上跑，整组测试是秒级的，
而它要验的性质（旧帧逐位不变、幂等、乱序抛错）与数据集的规模无关。
真数据集上的验收在 `tests/test_api_live.py`。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tfield import config as C
from tfield.data.loader import required_sensor_columns
from tfield.data.types import Dataset, FixReport, SensorPos
from tfield.features import build_features
from tfield.pipeline import FieldPipeline, PipelineConfig


def tiny_dataset(n_times: int = 12) -> Dataset:
    """一份最小可用的数据集：必要的列齐、时间戳 5 分钟一格、无修复。"""
    ts = pd.date_range("2026-07-23 11:00:00", periods=n_times, freq="5min")
    cols: dict[str, np.ndarray] = {
        C.COL_TIMESTAMP: ts.to_numpy(),
        C.BG_TEMP: np.linspace(20.0, 30.0, n_times),
        C.BG_RH: np.full(n_times, 60.0),
        C.BG_LIGHT: np.tile([0.0, 800.0], n_times // 2 + 1)[:n_times],
    }
    rng = np.random.default_rng(0)
    for col in required_sensor_columns():
        cols[col] = 20.0 + rng.normal(0.0, 0.5, n_times)
    wide = pd.DataFrame(cols).set_index(C.COL_TIMESTAMP, drop=False)
    quality = pd.DataFrame({
        C.COL_TIMESTAMP: ts.to_numpy(),
        "p1_p1_temp_C": np.zeros(n_times, dtype=int),
    })
    layout = {k: SensorPos(x=v[0], z=v[1], layer=v[2])
              for k, v in C.SENSOR_LAYOUT.items()}
    return Dataset(wide=wide, layout=layout, sheds=dict(C.SHED_Y), quality=quality,
                   fix=FixReport(n_rows=n_times, fixed_indices=(),
                                 monotonic_before=True, monotonic_after=True,
                                 spacing_seconds=300.0, gaps=()),
                   signature="tiny0000", _dict_layout={})


@pytest.fixture(scope="module")
def tiny() -> Dataset:
    return tiny_dataset()


def test_不追加时_时间轴与数据集逐位相同(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    assert pipe.n_times == len(tiny.wide)
    assert pipe.timestamps() == list(pd.to_datetime(tiny.wide[C.COL_TIMESTAMP]))


def test_time_at_给的是那一帧的时间(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    assert pipe.time_at(0) == pd.Timestamp("2026-07-23 11:00:00")
    assert pipe.time_at(pipe.n_times - 1) == pd.Timestamp("2026-07-23 11:55:00")


def test_time_at_越界抛_而不是返回_none(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    with pytest.raises(IndexError):
        pipe.time_at(pipe.n_times)
    with pytest.raises(IndexError):
        pipe.time_at(-1)


def test_没有实时帧时_n_live_是零(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    assert pipe.n_live == 0
