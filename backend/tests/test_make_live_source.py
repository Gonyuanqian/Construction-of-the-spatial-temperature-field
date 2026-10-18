"""切分命令：`configs/live/` 那两份文件是怎么来的（规格书 §四、§9.1）。

⚠️ 全程用 `synthetic_dataset` 现造的样本，**不读交付数据集** ——
那份文件不进仓库，而这条命令的正确性不该依赖它在不在。
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]

from make_live_source import LIVE_NAME, TRAIN_NAME, make_live_source  # noqa: E402
from tfield import config as C                                       # noqa: E402
from tfield.data.loader import load_dataset                          # noqa: E402

#: 10 行、5 分钟一格，跨过 2026-07-27 12:00 那个切点：前 6 行训练、后 4 行实时。
TIMES = pd.date_range("2026-07-27 11:30", periods=10, freq="5min")


def test_切出来的两份不重不漏_并集就是源(synthetic_dataset, tmp_path):
    src = synthetic_dataset(TIMES)
    out = tmp_path / "live"

    n_train, n_live = make_live_source(src, out)

    assert (n_train, n_live) == (6, 4)
    train = load_dataset(out / TRAIN_NAME)
    live = load_dataset(out / LIVE_NAME)
    assert train.wide.shape[1] == live.wide.shape[1] == 52
    # 并集 = 源文件那一串时刻，而且严格递增（不靠 mask 自证，靠读回来的值）
    both = list(train.wide[C.COL_TIMESTAMP]) + list(live.wide[C.COL_TIMESTAMP])
    assert both == list(TIMES)
    assert train.wide[C.COL_TIMESTAMP].max() < live.wide[C.COL_TIMESTAMP].min()
    # 两份各自的「测点字典」都读得出坐标：模型徽章靠的正是这一点
    assert train.dict_layout() and live.dict_layout()


def test_八小时偏移行落在切点上也能切干净(synthetic_dataset, tmp_path):
    """源数据里每天 16:00 被写成次日 00:00（+8 小时），共 5 行。

    这里把那一行**恰好放在切点上（12:00）**：修复判据需要「下一个邻居」才算
    得出该修成多少，而在未修的轴上切，它会带着 20:00 悄悄落进实时那一份。
    """
    times = list(TIMES)
    times[6] = times[6] + pd.Timedelta(hours=8)      # 12:00 → 20:00
    src = synthetic_dataset(times, name="offset.xlsx")
    out = tmp_path / "live"

    assert make_live_source(src, out) == (6, 4)

    for name in (TRAIN_NAME, LIVE_NAME):
        ds = load_dataset(out / name)
        assert ds.fix.fixed_indices == (), f"{name} 里还有没修好的行"
        assert ds.fix.monotonic_before is True, f"{name} 写出去的仍是没修的数"
    assert list(load_dataset(out / TRAIN_NAME).wide[C.COL_TIMESTAMP])[-1] \
        == pd.Timestamp("2026-07-27 11:55")
    assert list(load_dataset(out / LIVE_NAME).wide[C.COL_TIMESTAMP])[0] \
        == pd.Timestamp("2026-07-27 12:00")


def test_整份都在切点之前就拒绝_不写出一个空的实时文件(synthetic_dataset, tmp_path):
    early = list(pd.date_range("2026-07-27 11:30", periods=5, freq="5min"))
    src = synthetic_dataset(early, name="early.xlsx")
    out = tmp_path / "live"

    with pytest.raises(RuntimeError, match="实时"):
        make_live_source(src, out)


def test_整份都在切点之后就拒绝(synthetic_dataset, tmp_path):
    late = list(pd.date_range("2026-07-27 12:00", periods=5, freq="5min"))
    src = synthetic_dataset(late, name="late.xlsx")
    out = tmp_path / "live"

    with pytest.raises(RuntimeError, match="训练"):
        make_live_source(src, out)
