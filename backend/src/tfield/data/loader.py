"""读取对齐数据集，组装成只读 Dataset。"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config as C
from .timestamp import repair_axis
from .types import Dataset, SensorPos


def test_data_path() -> Path:
    """仓库根下的数据集路径（供测试与脚本共用）。"""
    return Path(__file__).resolve().parents[3] / C.DATA_FILENAME


# 名字以 test_ 开头是沿用的接口名（八个测试模块 import 它）。pytest 会把
# import 进测试模块的 `test_*` 当成用例收集并告警「测试函数不应有返回值」。
# 它是助手，不是用例 —— 关掉收集，而不是在每个测试文件里改名。
test_data_path.__test__ = False        # type: ignore[attr-defined]


def dataset_signature(path: str | Path) -> str:
    """按「绝对路径 + mtime + 大小」取身份。原地改文件也会变。"""
    p = Path(path).resolve()
    st = p.stat()
    raw = f"{p}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


#: 留出切点：晚于等于它的行被留出给实时模式。
#:
#: ⚠️ **naive 时间戳**。数据集的 `timestamp` 列实测是 `datetime64[us]`、
#: `tzinfo=None`；带时区的切点会在下面那一步比较里直接抛，
#: 而不是安静地切错 —— 但那也要写测试钉住，别指望它。
HOLDOUT_CUTOFF: pd.Timestamp = pd.Timestamp("2026-07-27 12:00:00")


@dataclass(frozen=True)
class Holdout:
    """一次留出切分的结果。"""

    train: Dataset          # 训练段：带派生签名，模型与构场只看它
    live: pd.DataFrame      # 留出段宽表（含 timestamp 列，索引已重置为 0..n-1）


def derived_signature(sig: str, cutoff: pd.Timestamp) -> str:
    """由文件签名派生出「训练段」的签名。

    `Dataset.signature` 是**文件级**的（路径 | mtime | 大小），而训练段不是文件。
    没有派生签名，训练段与全量就共用一个身份 —— 缓存键（`PipelineCache.key_of`）
    与标定包文件名（`bundle_<sig>_<groups>.json`）会撞车，两个不同的数据集
    用同一个名字。

    ⚠️ 格式里**不许有冒号**：签名要进 Windows 文件名。
    """
    return f"{sig}-h{pd.Timestamp(cutoff):%Y%m%dT%H%M}"


def split_holdout(ds: Dataset,
                  cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> Holdout:
    """按时间戳把数据集切成「训练段（< cutoff）」与「留出段（>= cutoff）」。

    两条规矩：

    1. **逐行掩码，不靠索引的 label 切片**。`wide` 的索引是 `repair_axis` 修过的
       （实测 `monotonic_before=False`、5 行序号被修复）。修复之后它确实单调无重复，
       但**不赌它** —— 一条掩码在任何时候都对。
    2. **`wide` 与 `quality` 同步切**。质检列是逐行的，错位不会报错，
       只会把 A 行的标记贴到 B 行上。

    `fix` 字段原样带过去：它描述的是这份数据「从哪来」，摘要与切片都不改变它。
    """
    cut = pd.Timestamp(cutoff)
    ts = pd.to_datetime(ds.wide[C.COL_TIMESTAMP])
    keep = (ts < cut).to_numpy()
    i_train = np.flatnonzero(keep)
    i_live = np.flatnonzero(~keep)

    train = replace(ds,
                    wide=ds.wide.iloc[i_train],
                    quality=ds.quality.iloc[i_train],
                    signature=derived_signature(ds.signature, cut))
    live = ds.wide.iloc[i_live].reset_index(drop=True)
    return Holdout(train=train, live=live)


def required_sensor_columns(layout=None, sheds=None) -> list[str]:
    layout = C.SENSOR_LAYOUT if layout is None else layout
    sheds = C.SHED_ORDER if sheds is None else sheds
    out: list[str] = []
    for shed in sheds:
        for pos in layout:
            out.extend(C.sensor_columns(shed, pos))
    return out


def check_sensor_columns(df: pd.DataFrame, *, layout=None, sheds=None) -> None:
    """缺列时明确报错并指出缺了哪些 —— 不要静默产生 NaN 后被当成有效数据。"""
    need = [C.COL_TIMESTAMP, C.BG_TEMP, C.BG_RH, C.BG_LIGHT,
            *required_sensor_columns(layout, sheds)]
    missing = [c for c in need if c not in df.columns]
    if missing:
        head = missing[:6]
        more = f" …（共 {len(missing)} 列）" if len(missing) > 6 else ""
        raise KeyError(f"缺失列：{head}{more}")


# 「测点字典」里拱顶下两个测点的高度写的是符号式（如 `H(0.80)-0.20`），
# 原始设备通道描述同样写符号，整张表里没有对应的数字。
_Z_FORMULA = re.compile(r"^H\(\s*([0-9.]+)\s*\)\s*-\s*([0-9.]+)$")


def _arch_height(x: float) -> float:
    """拱高 z(x) = sqrt(R² − (x − XC)²) + K。

    Task 10 会有公开的 `arch_height`；这里为了把符号高度解析成数字，需要一个
    等价表达式。它只读 config 里的几何常数，所以两处不会各有一套数字。
    """
    return math.sqrt(C.ARCH_R ** 2 - (x - C.ARCH_XC) ** 2) + C.ARCH_K


def _coerce_z(raw: object, x: float) -> float:
    """把「高度坐标(m)」单元格变成浮点数。

    多数测点是数字；拱顶下两个是符号式 `H(a)-b`（拱高减 b 米），按公式求值。
    解析不了就让它以 ValueError 暴露，而不是静默填一个 0。
    """
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    text = str(raw).strip()
    m = _Z_FORMULA.match(text)
    if m:
        return _arch_height(float(m.group(1))) - float(m.group(2))
    return float(text)


def _parse_dict_layout(path: Path) -> dict[str, SensorPos]:
    """从「测点字典」sheet 读出每个测点的 (x, z)。"""
    d = pd.read_excel(path, sheet_name=C.SHEET_DICT)
    out: dict[str, SensorPos] = {}
    for _, row in d.iterrows():
        name = str(row["变量名"])
        if not name.endswith(f"_{C.VAR_TEMP}"):
            continue
        pos = name[: -len(f"_{C.VAR_TEMP}")]              # 去掉 "_temp_C"
        head, _, tail = pos.partition("_")
        if head in C.SHED_ORDER:
            pos = tail                                    # 去掉 "p1_"
        if pos not in C.SENSOR_LAYOUT:
            continue
        x = float(row["水平坐标(m)"])
        out[pos] = SensorPos(x=x,
                             z=_coerce_z(row["高度坐标(m)"], x),
                             layer=C.SENSOR_LAYOUT[pos][2])
    return out


def load_dataset(path: str | Path) -> Dataset:
    path = Path(path)
    wide = pd.read_excel(path, sheet_name=C.SHEET_MAIN)
    quality = pd.read_excel(path, sheet_name=C.SHEET_QUALITY)
    check_sensor_columns(wide)

    idx, report = repair_axis(wide[C.COL_TIMESTAMP])
    wide = wide.copy()
    wide[C.COL_TIMESTAMP] = idx.to_numpy()
    wide = wide.set_index(C.COL_TIMESTAMP, drop=False)
    quality = quality.copy()
    quality[C.COL_TIMESTAMP] = idx.to_numpy()

    layout = {k: SensorPos(x=v[0], z=v[1], layer=v[2]) for k, v in C.SENSOR_LAYOUT.items()}
    return Dataset(
        wide=wide,
        layout=layout,
        sheds=dict(C.SHED_Y),
        quality=quality,
        fix=report,
        signature=dataset_signature(path),
        _dict_layout=_parse_dict_layout(path),
    )
