"""实时模式的七条接口。

**契约**：载荷装配**不在这个文件里** —— `frame` 与 `volume` 调的是
`routes.field.sections_payload` / `volume_payload`，也就是页③ 用的那两个函数。
在这里重拼一份就等于把「三格共享色标」「无测量带的下标」「1/dy 混合出来的
断面算不算实测」这些规则实现第二遍（硬约束 1）。

**status 是纯读**：不 append、不建管线。帧的 append 发生在 `frame` / `volume` /
`next` 里 —— 校验完帧号才动手。于是「status 永远轻」从一句承诺变成
`test_没准备之前_status_字段是_idle_且不动管线` 钉着的一条性质，
而且没有一个 GET 带副作用。

**帧号 n 与 `t_index` 不是一回事**：`n` 是留出段的下标（0..143），
`t_index` 是**管线时间轴**上的下标（1164..1307）。转接在 `LiveSource.t_index_of`
里，一个地方做完 —— 这个文件里凡是要算场的地方都拿 `advance_to(n)` 的返回值，
不自己写 `+ 1164`。
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from tfield import config as C

from .. import live
from .field import (DEFAULT_PRESET, _check_preset, _check_volume_size, _check_y_range,
                    _y_plane_count, sections_payload, volume_payload)

router = APIRouter(tags=["live"])


def _f(v: Any) -> float | None:
    """非有限浮点翻成 None。`JSONResponse` 走 `allow_nan=False`，
    一个 NaN 就是 HTTP 500 而不是 null。"""
    f = float(v)
    return f if math.isfinite(f) else None


def _require_ready(src: live.LiveSource) -> None:
    if src.pipeline is None:
        raise HTTPException(400, "实时源还没准备好，先 POST /api/live/prepare")


def _require_walked(src: live.LiveSource, n: int) -> int:
    """帧号必须落在 `0..cursor`。

    ⚠️ **不悄悄拿当前帧顶替**：那会让「还没走到」看起来像「就是这一帧」，
    而这一屏最不能错的就是「现在演的是第几帧」。
    """
    cur = src.cursor()
    if not 0 <= n <= cur:
        raise HTTPException(
            400, f"实时源现在到第 {cur} 帧，取不到第 {n} 帧。先 POST /api/live/next 走过去。")
    return n


@router.get("/live/status")
def get_status() -> dict[str, Any]:
    """状态。**永不失败、永不触发布管线、永不 append。**"""
    src = live.get_live_source()
    return {
        "state": src.state,
        "running": bool(src.running),
        "cursor": int(src.cursor()),
        "total": int(src.total),
        "interval_s": float(live.LIVE_INTERVAL_S),
    }


@router.post("/live/prepare")
def post_prepare() -> dict[str, Any]:
    """建实时源自己的那份管线。幂等；**同步**，几十秒。"""
    seconds = live.get_live_source().prepare()
    return {"state": "ready", "seconds": float(seconds)}


@router.post("/live/start")
def post_start(from_n: int | None = Query(None, description="从第几帧开始")) -> dict[str, Any]:
    src = live.get_live_source()
    _require_ready(src)
    try:
        src.start(from_n)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return get_status()


@router.post("/live/pause")
def post_pause() -> dict[str, Any]:
    src = live.get_live_source()
    src.pause()
    return get_status()


@router.post("/live/next")
def post_next() -> dict[str, Any]:
    """手动前进一格。**上篇的规格里没有这一条** —— 自动与手动两档都要，
    没有它手动那一档就没接口。
    """
    src = live.get_live_source()
    _require_ready(src)
    try:
        src.next_frame()
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return get_status()


@router.get("/live/frame/{n}")
def get_frame(
    n: int,
    preset: str = Query(DEFAULT_PRESET, description="网格档位"),
    monotonic: bool = Query(True, description="是否施加竖直软单调投影"),
) -> dict[str, Any]:
    src = live.get_live_source()
    _require_ready(src)
    _require_walked(src, n)
    _check_preset(preset)                     # 参数坏就别走帧
    # ⚠️ `t_index` **不是 n** —— 实时帧接在训练段尾部（第 0 帧是 1164）。
    # 拿 n 当 t_index 不报错，只是取到训练段那一帧的场，而 `frame.time`
    # 写的是留出段的时间。`t_index_of` 那儿的注释把代价写全了。
    t_index = src.advance_to(n)
    payload = sections_payload(src.pipeline, t_index=t_index, preset=preset,
                               monotonic=monotonic)
    row = src.frame(n)
    payload["frame"] = {
        "n": int(n),
        "time": str(pd.Timestamp(row[C.COL_TIMESTAMP])),
        "bg_temp": _f(row[C.BG_TEMP]),
        "bg_rh": _f(row[C.BG_RH]),
        "bg_light": _f(row[C.BG_LIGHT]),
        "sensor_temps": src.sensor_temps(n),
    }
    payload["live"] = {
        "cursor": int(src.cursor()),
        "running": bool(src.running),
        "interval_s": float(live.LIVE_INTERVAL_S),
        "total": int(src.total),
    }
    return payload


@router.get("/live/volume/{n}")
def get_volume(
    n: int,
    preset: str = Query(DEFAULT_PRESET, description="网格档位"),
    monotonic: bool = Query(True, description="是否施加竖直软单调投影"),
    y_step: float = Query(0.5, description="沿棚长 y 的切片间隔 / m"),
    y_min: float = Query(0.0, description="y 的起点 / m"),
    y_max: float = Query(18.0, description="y 的终点 / m"),
) -> dict[str, Any]:
    """约 1.2 秒（与 `/api/field/volume` 同量级）—— 几十秒是 **fit** 的量级，
    那是 `prepare` 的事。
    """
    src = live.get_live_source()
    _require_ready(src)
    _require_walked(src, n)
    grid = _check_preset(preset)
    _check_y_range(y_min, y_max, y_step)
    _check_volume_size(grid.nx, grid.nz, _y_plane_count(y_min, y_max, y_step))
    t_index = src.advance_to(n)               # 同上：**不是 n**
    payload = volume_payload(src.pipeline, t_index=t_index, preset=preset, monotonic=monotonic,
                             y_step=y_step, y_min=y_min, y_max=y_max, grid=grid)
    payload["frame"] = {"n": int(n), "time": str(pd.Timestamp(src.frame(n)[C.COL_TIMESTAMP]))}
    payload["live"] = {
        "cursor": int(src.cursor()),
        "running": bool(src.running),
        "interval_s": float(live.LIVE_INTERVAL_S),
        "total": int(src.total),
    }
    return payload
