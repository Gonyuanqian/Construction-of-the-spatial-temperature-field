"""移植件的契约 + **漂移守卫**。

`app/app.py` 依赖 streamlit，import 不进来（spec 2026-10-03 §五.5），
所以「两边是不是还一样」只能拿**源码文本**对。
这一组测试就是那个漂移面唯一的探针 —— 它红了不代表代码错，代表两边分了家。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import ported                                    # noqa: E402

OLD_PROJECT = BACKEND.parent.parent / "空间温度场的构建"
OLD_APP = OLD_PROJECT / "app" / "app.py"
API_PORTED = BACKEND / "api" / "ported.py"


def _extract(text: str, name: str) -> str:
    """从源码里抠出某个顶层函数的源码（含 docstring），到下一个顶层 def/class 为止。"""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"def {name}("))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("def ") or lines[i].startswith("class "):
            end = i
            break
    body = lines[start:end]
    while body and not body[-1].strip():
        body.pop()
    return "\n".join(body)


@pytest.mark.skipif(not OLD_APP.exists(), reason="旧项目不在旁边，跳过漂移守卫")
def test_check_missing_与_旧项目逐字相同():
    assert _extract(API_PORTED.read_text(encoding="utf-8"), "check_missing") == \
        _extract(OLD_APP.read_text(encoding="utf-8"), "check_missing")


@pytest.mark.skipif(not OLD_APP.exists(), reason="旧项目不在旁边，跳过漂移守卫")
def test_两条内联检查的文案与旧项目同源():
    """结构完整性与时间轴这两条没有独立函数，只能对字符串片段。

    片段取自 `app/app.py:dataset_checks`。改了那边的措辞、这边没跟，这条就红。
    """
    old = OLD_APP.read_text(encoding="utf-8")
    for frag in ("必需 sheet 与列是否齐；缺列明确报错不猜",
                 "单调、无重复、等间隔 300 s；已知缺陷已幂等修复",
                 'layout {len(ds.layout)} 个点位'):
        assert frag in old, f"旧项目里找不到这段文案：{frag!r} —— 两边漂了"


def test_保留三项且被砍的五项全部点名():
    """Review Focus #5：砍掉的项在界面上没有别的去处，必须自己说出来。"""
    assert ported.KEPT == ("结构完整性", "时间轴", "缺失")
    assert ported.DROPPED == ("值域", "卡死", "跨棚离群", "质量标记", "对齐")
    note = ported.checks_note()
    for name in ported.DROPPED:
        assert name in note, f"被砍掉的「{name}」没写进说明里 —— 它就凭空消失了"
    assert "卡死" in note          # 这一项真会提示传感器故障，最不该被悄悄砍掉


def test_fmt_value_把布尔说成开与关():
    assert ported.fmt_value(True) == "开"
    assert ported.fmt_value(False) == "关"
    assert ported.fmt_value(0.005) == "0.005"
    assert ported.fmt_value(10.0) == "10"


def test_特征组文案覆盖全部四组():
    from tfield.config import DEFAULT_FEATURE_GROUPS
    assert set(ported.FEATURE_GROUP_WHAT) == set(DEFAULT_FEATURE_GROUPS)
    assert all(v for v in ported.FEATURE_GROUP_WHAT.values())


def test_检查项在真实数据集上跑得出证据():
    from tfield.data.loader import load_dataset, test_data_path
    ds = load_dataset(test_data_path())
    rows = ported.dataset_checks(ds)
    assert [r.no for r in rows] == [1, 2, 3]
    assert [r.name for r in rows] == list(ported.KEPT)
    assert all(r.status in {"ok", "warn"} for r in rows)
    assert all(r.evidence for r in rows)
    # 结构完整性那一条报的是真实的宽表形状
    assert "1308" in rows[0].evidence and "52" in rows[0].evidence
    assert rows[2].name == "缺失" and "缺失 0" in rows[2].evidence
