"""空间场的几何与取值。

`/api/field/sections` 与 `/api/field/volume`（页③）也落在这个文件里，
但要先有管线缓存 —— 见下一份计划。
"""
from __future__ import annotations

from typing import Any

import numpy as np
from fastapi import APIRouter

from tfield import config as C
from tfield.field.arch import arch_height

router = APIRouter(tags=["field"])

#: 拱线折线的点数。121 点 → 每 0.0175 m 一段：屏幕上一像素以内，
#: 而 JSON 只有两百多个数。**点数由后端定**，前端不生成几何。
ARCH_SAMPLES = 121


@router.get("/field/arch")
def get_arch() -> dict[str, Any]:
    """拱形轮廓与三座棚的 y。

    **前端不许自己算这条线。** 拱是 `z(x) = √(R² − (x−Xc)²) + K`，
    常数住在 `tfield.config` 里；在前端重抄一遍公式，抄错一个常数
    画出来的就不是这座棚，而且它看起来仍然像一条拱 —— 不会报错。
    测试拿 `arch_height` 与本接口逐位对（后端库就是那个 oracle）。

    ⚠️ 这条线**不会**产生非有限值：`arch_height` 里 `np.maximum(inner, 0.0)`
    把负的根号内挡成 0，所以任何 x 上都是有限的。前端可直接画，
    不必像 `layer-timeheight` 那样担心 null。
    """
    x = np.linspace(C.SHED_X_MIN, C.SHED_X_MAX, ARCH_SAMPLES)
    z = arch_height(x)
    return {
        "x_min": float(C.SHED_X_MIN),
        "x_max": float(C.SHED_X_MAX),
        "z_max": float(C.SHED_Z_MAX),
        "max_measured_z": float(C.MAX_MEASURED_Z),
        "arch": [[float(a), float(b)] for a, b in zip(x, z)],
        "sheds": [{"id": s, "y": float(C.SHED_Y[s])} for s in C.SHED_ORDER],
    }
