"""从 `app/app.py` 移植过来的、与 streamlit 无关的纯函数与文案。

**这不是新写的逻辑。** spec 2026-10-03 §五.5 已定：页① 的数据检查现在住在
`app/app.py:174`，Vue 侧不能 import 它（那个模块顶层 import streamlit），
`tfield` 又不能塞（会与真源永久漂移）。所以照原样移植一份到 API 层。

⚠️ **API 层从此多了一个跟 `app/app.py` 平行的漂移面。**
它靠 `tests/test_ported.py` 里的**源码文本比对**盯着，不靠自觉：
`check_missing` 是逐字对，两条内联检查对字符串片段。
那个测试红了不代表代码错，代表两边分了家 —— 那时候要决定的是「以哪边为准」。

⚠️ 别跟管线里的「六项校验」混（`app/app.py:1687` 那一套：缺失/冻结/越界/跨棚/质检/时间对齐）。
那是数据质量闸门，跟这里的检查表是两件不同的东西。
"""
from __future__ import annotations

from typing import NamedTuple

import pandas as pd

# ── 检查表 ──


class CheckRow(NamedTuple):
    """数据检查表的一行。evidence 是给人看的证据（列名 + 时刻）。"""
    no: int
    name: str
    what: str
    status: str
    evidence: str


#: 页① 保留的三项。用户定的：只列最重要的几项。
KEPT = ("结构完整性", "时间轴", "缺失")

#: 后端照算、但**没有放进页①** 的五项。
#: 「卡死」这一项真会提示传感器故障 —— 所以 `checks_note()` 必须点它的名。
DROPPED = ("值域", "卡死", "跨棚离群", "质量标记", "对齐")


def check_missing(wide: pd.DataFrame) -> CheckRow:
    """逐列缺失计数 —— 不静默插补。"""
    counts = wide.isna().sum()
    bad = counts[counts > 0]
    if bad.empty:
        ev = f"{wide.shape[0]} 行 × {wide.shape[1]} 列，缺失 0"
        return CheckRow(3, "缺失", "逐列缺失计数，不静默插补", "ok", ev)
    top = "、".join(f"{c}×{int(n)}" for c, n in bad.head(5).items())
    return CheckRow(3, "缺失", "逐列缺失计数，不静默插补", "warn",
                    f"{len(bad)} 列有缺失：{top}")


def dataset_checks(ds) -> list[CheckRow]:
    """页① 的三条检查，固定顺序。

    第 3 条不预先编数：界面上显示的就是这里现算出来的证据。
    前两条的证据串与 `app/app.py` **同源**（见模块头的漂移说明）。
    """
    return [
        CheckRow(1, "结构完整性", "必需 sheet 与列是否齐；缺列明确报错不猜",
                 "ok", f"宽表 {ds.wide.shape[0]} × {ds.wide.shape[1]}，"
                       f"layout {len(ds.layout)} 个点位，棚 {list(ds.sheds)}"),
        CheckRow(2, "时间轴", "单调、无重复、等间隔 300 s；已知缺陷已幂等修复",
                 "ok", f"等间隔 {ds.fix.spacing_seconds:.0f} s，"
                       f"修复 {len(ds.fix.fixed_indices)} 行"
                       f"（{'、'.join(str(i) for i in ds.fix.fixed_indices)}），"
                       f"其余断点 {len(ds.fix.gaps)} 处"),
        check_missing(ds.wide),
    ]


def checks_note() -> str:
    """被砍掉的那几项去哪了。**这句话不能省** —— 不写就等于它们不存在。

    ⚠️ 原文用的是带空格的破折号，但这段文案会进响应体、由前端直接渲染，
    属于 Ruling P2 的「用户可见字符串」；破折号在那里是禁用连接符，
    所以改成「；」。句意未变。
    """
    return ("这一页只列三项：判断「这份数据能不能用」所必需的那三项。"
            f"其余 {len(DROPPED)} 项（{'、'.join(DROPPED)}）后端照算，"
            "只是没有铺在页面上；八项平铺会让人一眼扫过、什么也没记住。")


# ── 文案与格式化（页② 用）──

#: 四组特征各自在说什么。与 `app/app.py:411` 同源。
FEATURE_GROUP_WHAT = {
    "coord": "场的基本骨架：棚长、棚位、高度",
    "zbasis": "竖直方向的结构（温度沿高度的弯折）",
    "meteo": "时刻的外部条件",
    "interaction": "坐标 × 气象：辐照下拱内分层的形态",
}


def fmt_value(v) -> str:
    """参数值的显示口径。与 `app/app.py:_fmt` 同源。

    `0.005` 必须显示成 `0.005` 而不是 `0.005000000000000001` ——
    这也是为什么它不交给前端：那是数值格式化，前端不做（spec §六 硬约束 1）。

    它**永远**返回字符串，所以哪怕传进来的是 NaN/Inf，落进响应体也是
    `"nan"` / `"inf"` 这样的字符串，不会触发 `JSONResponse(allow_nan=False)`
    的 ValueError。简言之：格式化本身就是这道非有限值的闸门。
    """
    if isinstance(v, bool):
        return "开" if v else "关"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)
