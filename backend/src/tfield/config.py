"""全局常量：拱形几何、测点布局、棚位、位置二分、兜底参数。

**模型参数不在这里** —— 它们来自 CalibrationBundle（见 calibration.py）。
本文件里的 FALLBACK_* 只在尚未标定时使用，界面上必须标注「未标定」。

不要从这里 import 任何 tfield 子模块：models/idw.py 要 import 本文件，
反向依赖会成环。
"""
from __future__ import annotations

from typing import Final

# ── 拱形几何（由图纸拟合）──
# z(x) = sqrt(R² − (x − XC)²) + K；拱脚在 z ≈ 0.4535，不是 0
ARCH_R: Final = 1.0761
ARCH_XC: Final = 1.0517
ARCH_K: Final = 0.2256
SHED_X_MIN: Final = 0.0
SHED_X_MAX: Final = 2.1
SHED_Z_MAX: Final = 1.3017          # = ARCH_K + ARCH_R，拱顶

# ── 测点布局（切面内）── 键名对应 xlsx 列名中的一段，不可随意改
SENSOR_LAYOUT: Final[dict[str, tuple[float, float, str]]] = {
    "x0.15_z0.4": (0.15, 0.4, "z0.4"),
    "x0.4_z0.7": (0.40, 0.7, "z0.7"),
    "x0.8_zH(0.80)-0.20": (0.80, 1.1, "ztop"),
    "x1.05_z0.4": (1.05, 0.4, "z0.4"),
    "x1.05_z0.7": (1.05, 0.7, "z0.7"),
    "x1.3_zH(1.30)-0.20": (1.30, 1.1, "ztop"),
    "x1.7_z0.7": (1.70, 0.7, "z0.7"),
    "x1.95_z0.4": (1.95, 0.4, "z0.4"),
}
MAX_MEASURED_Z: Final = 1.10        # 最高测点；其上是拱顶下的「无测量带」

# ── 棚位（棚长方向 y，单位 m）──
SHED_ORDER: Final = ("p1", "p2", "p3")
SHED_Y: Final = {"p1": 3.0, "p2": 9.0, "p3": 15.0}

# ── 位置二分（结构性，永不重选；见设计文档 §7.1）──
TUNING_POSITIONS: Final = ("x0.15_z0.4", "x1.05_z0.4", "x0.4_z0.7", "x0.8_zH(0.80)-0.20")
REPORT_POSITIONS: Final = ("x1.95_z0.4", "x1.05_z0.7", "x1.7_z0.7", "x1.3_zH(1.30)-0.20")

# ── 数据契约 ──
DATA_FILENAME: Final = "人参棚_多棚温湿度_气象时间对齐数据集.xlsx"
SHEET_MAIN: Final = "建模对齐数据"
SHEET_QUALITY: Final = "插值标记"
SHEET_DICT: Final = "测点字典"
SHEET_NOTES: Final = "处理说明"
SHEET_FIELDS: Final = "字段说明"
EXPECTED_ROWS: Final = 1308
EXPECTED_COLS: Final = 52
EXPECTED_SPACING_S: Final = 300.0
EXPECTED_N_SENSORS: Final = 24
EXPECTED_FIXED_ROWS: Final = (60, 348, 636, 924, 1212)

COL_TIMESTAMP: Final = "timestamp"
BG_TEMP: Final = "bg_temp_C"
BG_RH: Final = "bg_rh_pct"
BG_LIGHT: Final = "bg_light"
VAR_TEMP: Final = "temp_C"
VAR_RH: Final = "rh_pct"


def sensor_columns(shed: str, pos: str) -> tuple[str, str]:
    """返回 (温度列名, 湿度列名)。"""
    prefix = f"{shed}_{pos}"
    return f"{prefix}_{VAR_TEMP}", f"{prefix}_{VAR_RH}"


# ── 特征组 ──
DEFAULT_FEATURE_GROUPS: Final = ("coord", "zbasis", "meteo", "interaction")

# ── 兜底参数（未标定时使用；界面上必须标注「未标定」）──
# 刻意避开旧口径 (power=1, lx=1.0, lz=0.12) —— 实测那是整片扫描区最差的一角。
# 这几个值**不是最优**，只是「不在坏角上」的兜底；真正取值见标定包。
FALLBACK_LX: Final = 2.0
FALLBACK_LY: Final = 1.0
FALLBACK_LZ: Final = 0.12
FALLBACK_POWER: Final = 2.0
FALLBACK_CROSS_SHED: Final = True

FALLBACK_TREND_KIND: Final = "xgboost"
FALLBACK_TREND_PARAMS: Final = {
    "max_depth": 4,
    "learning_rate": 0.08,
    "n_estimators": 300,
    "random_state": 0,
    "n_jobs": -1,
    "tree_method": "hist",
    "verbosity": 0,
}
