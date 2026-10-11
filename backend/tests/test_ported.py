"""移植件的契约。

`api/ported.py` 是一份**移植件**：它的算法与文案照搬自另一份实现的应用层，
那一份不在这棵树上。于是这里钉的是它自己的契约 —— 保留哪三项、
被砍的五项都要点名、格式化的口径 —— 而不是「还跟来处一样」。
"""
from __future__ import annotations

import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import ported                                    # noqa: E402


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
