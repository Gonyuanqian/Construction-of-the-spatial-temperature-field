"""宽表 → 时空长表 → 特征矩阵。

长表每行 = 一个 (传感器, 时刻) 对，共 24 × 1308 = 31392 行。
不加滞后特征（本版是重建任务，同时刻气象已知）。
不加测点湿度（目标点的湿度同样是未知量）。

add_feature_groups 是**训练与查询共用的唯一特征定义** —— FieldPipeline 在
任意空间点上查询趋势时必须走它，否则两边列定义漂移会静默出错。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from .data.types import Dataset

FEATURE_GROUPS = ("coord", "zbasis", "meteo", "interaction")


@dataclass(frozen=True)
class FeatureSet:
    X: pd.DataFrame
    y: np.ndarray
    coords: np.ndarray            # (24, 3) 传感器坐标 (x, y, z)
    sensor_id: np.ndarray         # (N,) 每行属于哪个传感器 0..23
    t_index: np.ndarray           # (N,) 每行属于哪个时刻 0..1307


def to_long(ds: Dataset) -> pd.DataFrame:
    """宽表 → 长表。列：sensor_id, t_index, x, y, z, layer, temp,
    bg_temp, bg_rh, bg_light, hour, frac_day。"""
    wide = ds.wide
    ts = pd.to_datetime(wide[C.COL_TIMESTAMP])
    n_t = len(wide)
    frames: list[pd.DataFrame] = []
    for shed_i, shed in enumerate(C.SHED_ORDER):
        for pos_k, pos in enumerate(C.SENSOR_LAYOUT):
            tcol, _ = C.sensor_columns(shed, pos)
            x, z, layer = C.SENSOR_LAYOUT[pos]
            frames.append(pd.DataFrame({
                "sensor_id": shed_i * 8 + pos_k,
                "t_index": np.arange(n_t),
                "x": x,
                "y": C.SHED_Y[shed],
                "z": z,
                "layer": layer,
                "temp": wide[tcol].to_numpy(float),
                "bg_temp": wide[C.BG_TEMP].to_numpy(float),
                "bg_rh": wide[C.BG_RH].to_numpy(float),
                "bg_light": wide[C.BG_LIGHT].to_numpy(float),
                "hour": ts.dt.hour.to_numpy(),
                "frac_day": (ts.dt.hour + ts.dt.minute / 60.0).to_numpy(),
            }, index=np.arange(n_t)))
    return pd.concat(frames, ignore_index=True)


def add_feature_groups(long: pd.DataFrame, groups=C.DEFAULT_FEATURE_GROUPS) -> pd.DataFrame:
    """按组拼特征列。列顺序确定，训练与查询共用。"""
    out = pd.DataFrame(index=long.index)
    if "coord" in groups:
        out["x"] = long["x"]
        out["y"] = long["y"]
        out["z"] = long["z"]
    if "zbasis" in groups:
        out["z2"] = long["z"] ** 2
        out["z3"] = long["z"] ** 3
    if "meteo" in groups:
        out["bg_temp"] = long["bg_temp"]
        out["bg_rh"] = long["bg_rh"]
        out["bg_light"] = long["bg_light"]
        out["hour"] = long["hour"]
        out["frac_day"] = long["frac_day"]
    if "interaction" in groups:
        out["bg_temp_x_z"] = long["bg_temp"] * long["z"]
        out["bg_light_x_z"] = long["bg_light"] * long["z"]
        out["bg_temp_x_light"] = long["bg_temp"] * long["bg_light"]
    return out


def build_features(ds: Dataset, groups=C.DEFAULT_FEATURE_GROUPS) -> FeatureSet:
    long = to_long(ds)
    X = add_feature_groups(long, tuple(groups))
    coords = np.array(
        [[C.SENSOR_LAYOUT[pos][0], C.SHED_Y[shed], C.SENSOR_LAYOUT[pos][1]]
         for shed in C.SHED_ORDER for pos in C.SENSOR_LAYOUT],
        dtype=float,
    )
    return FeatureSet(
        X=X,
        y=long["temp"].to_numpy(float),
        coords=coords,
        sensor_id=long["sensor_id"].to_numpy(int),
        t_index=long["t_index"].to_numpy(int),
    )
