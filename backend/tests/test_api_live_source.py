"""页⑤ 的两个数据源出口（规格书 2026-10-16 §五、§九）。

⚠️ 这个文件**不读交付数据集**：样本一律由 `synthetic_dataset` 现造。
真正「重启后页⑤ 照样能演」那条验收在 Task 4 末尾加进来，它才需要真数据。
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "scripts")]

from api import deps, paths                       # noqa: E402

BEFORE = pd.date_range("2026-07-27 11:30", periods=6, freq="5min")   # 训练那半
AFTER = pd.date_range("2026-07-27 12:00", periods=4, freq="5min")    # 实时那半


@pytest.fixture
def live_files(synthetic_dataset, tmp_path, monkeypatch):
    """把 `paths.LIVE_*` 指到现造的两份文件上。

    ⚠️ 用 `monkeypatch.setattr(paths, "LIVE_TRAIN", …)` 而不是改 `paths` 里的
    常量 —— `deps` 那两条出口必须**每次调用时**取属性（见 §5.2），改常量就测
    不出这件事了。
    """
    train = synthetic_dataset(BEFORE, name="train.xlsx")
    live = synthetic_dataset(AFTER, name="live.xlsx")
    monkeypatch.setattr(paths, "LIVE_TRAIN", train)
    monkeypatch.setattr(paths, "LIVE_FRAMES", live)
    deps.reset_cache()
    yield train, live
    deps.reset_cache()


def test_两个出口读的是各自那个文件(live_files):
    assert len(deps.live_train_dataset().wide) == 6
    assert len(deps.live_playback_dataset().wide) == 4
    assert deps.live_train_dataset().wide.index[0] == pd.Timestamp("2026-07-27 11:30")
    assert deps.live_playback_dataset().wide.index[0] == pd.Timestamp("2026-07-27 12:00")


def test_两个出口都走同一个缓存(live_files):
    """`get_dataset()` 是本项目数据集的唯一入口，不另开一套判定。"""
    assert deps.live_train_dataset() is deps.live_train_dataset()
    assert deps.live_playback_dataset() is deps.live_playback_dataset()
    assert deps.live_train_dataset() is not deps.live_playback_dataset()


def test_文件不在时抛_FileNotFoundError(live_files, monkeypatch, tmp_path):
    """**让它抛，不要在这里吞。** 翻译成人话是 `api/main.py` 的事（Task 5）。"""
    monkeypatch.setattr(paths, "LIVE_FRAMES", tmp_path / "缺.xlsx")
    with pytest.raises(FileNotFoundError):
        deps.live_playback_dataset()


def test_没有当前数据集时也能问出用哪一份模型(live_files, current_model):
    """`live_train_dataset()` 当轴，`_CURRENT` 指到空 —— 页⑤ 重启后的那一刻。

    ⚠️ 这条**今天会红**：`current_bundle()` 内部第一句就是 `get_train_dataset()`，
    没有当前数据集时抛 `NoDatasetError`，页⑤ 的模型门跟着整页空掉。
    """
    deps.clear_current_dataset()
    deps.reset_cache()
    got = deps.current_bundle(ds=deps.live_train_dataset())
    assert got.bundle is not None, "库里有当前模型，却问不出用哪一份"
    assert got.source == "library"


def test_不传_ds_时行为一个字不变():
    """空态下老调用点照旧抛 —— 页③ 的语义没有被这次加法偷换。"""
    deps.clear_current_dataset()
    deps.reset_cache()
    with pytest.raises(deps.NoDatasetError):
        deps.current_bundle()
