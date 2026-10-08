"""`deps.current_bundle()`：全站唯一一处回答「这次用哪一份模型」。

三档优先级与它俩的退场条件（规格书 §5.4）：
  1. 本次会话刚跑完、还没入库的那一份 → "unsaved"
  2. 否则库里的当前模型，与当前训练段对得上 → "library"
  3. 都没有 → (None, None)

⚠️ 第 1 条压在第 2 条上面，所以它必须有退场条件 —— 否则「未入库」那一份
会**永远**压着库里的当前模型，而用户在库列表里换模型时页③ 一动不动。
"""
from __future__ import annotations

import pathlib
import sys
import threading

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api import deps, jobs, models_store, paths            # noqa: E402
from tfield.calibration import load_bundle                 # noqa: E402


def _real_bundle():
    """一份**与当前训练段对得上**的真包。**只读**，不改盘上任何东西。

    ⚠️ 不能图省事写 `sorted(paths.CONFIGS.glob("bundle_*.json"))[0]`。盘上有
    **四份**历史包，按文件名排序第一的是 `bundle_0066856dc40a8bbc-…`，那是
    **另一份数据集**标的；当前交付的这一份是 `6145fa9261e89f1b-…`。
    取错那一份，`current_bundle()` 会（**正确地**）判它「与训练段对不上」而
    退回库里 —— 于是这个文件里的每一条测的都是「对不上」，包括那三条本该
    测「刚跑完的那一份」的。红/绿都还在，测的东西换了，而没有一个字提示。
    """
    want = deps.get_train_dataset().signature
    for p in sorted(paths.CONFIGS.glob("bundle_*.json")):
        b = load_bundle(p)
        if b is not None and b.dataset_sig == want:
            return b
    raise AssertionError(f"盘上没有与 {want} 对得上的包 —— 这个文件没有可用的样本")


@pytest.fixture()
def clean():
    jobs.clear()
    deps.set_current_dataset(paths.dataset_path())
    deps.reset_cache()
    yield
    jobs.clear()


@pytest.fixture()
def db(models_db):
    """空表；库名由 `tests/conftest.py` 钉在 `tfield_models_test` 上。

    与本仓 `test_models_store.py` 那个同名夹具是同一件事、同一个来源。
    """
    return models_db


def _finished(bundle):
    """造一个「跑完了、有结果」的 job，**不真跑搜索**。

    ⚠️ 那道门闩（`gate`）是承重的，不是花架子。执行器是**单线程池**，而
    `work` 卡在 `gate.wait()` 上，所以 `jobs.finish(...)` 一定**先于**
    `_run` 里那句「跑完了却没有结论」的兜底判断发生。不放门闩的话两边抢
    同一个 job：`_run` 先把状态定成 `failed` 并摘掉 `_CURRENT`，测试随后
    读到 `None` —— 而它红起来的样子像「`current_bundle` 写错了」，离真正
    的原因很远。

    ⚠️ 也**不许**图省事写成 `jobs.submit(cj._work)`：那会真的跑一次标定，
    四十次试验乘四折，分钟级。
    """
    gate = threading.Event()

    def work(job):
        gate.wait(5)

    job = jobs.submit(work)
    job.result = bundle
    jobs.finish(job, jobs.DONE)
    gate.set()
    return job.id


def test_什么都是空的时候给_None(clean, db):
    got = deps.current_bundle()
    assert got.bundle is None
    assert got.source is None


def test_刚跑完还没入库时给的是那一份(clean, db):
    _finished(_real_bundle())
    got = deps.current_bundle()
    assert got.source == "unsaved"
    assert got.bundle is not None
    assert got.bundle.dataset_sig == _real_bundle().dataset_sig


def test_摘掉之后轮到库里的当前模型(clean, db):
    """保存成功即退场（规格书 §5.4）—— 这一条是那个退场条件的钉子。"""
    ds = deps.get_train_dataset()
    row = models_store.save_model("库里的", _real_bundle(), ds, "f.xlsx")

    _finished(_real_bundle())
    assert deps.current_bundle().source == "unsaved"

    jobs.retire_result()
    got = deps.current_bundle()
    assert got.source == "library"
    assert got.bundle is not None
    assert got.bundle.dataset_sig == ds.signature
    assert row.id == models_store.current_id()


def test_未入库的那一份数据集对不上时_退回库里(clean, db):
    """⭐ 规格书 §5.4 的退场条件写的是「保存」与「再跑一次」，但顺序上
    更硬的一条是**对不上就跳过**：拿一份为别的数据集标的参数给这一份构场，
    屏上会是一个看着完全正常、其实全错的场。"""
    import dataclasses

    _finished(dataclasses.replace(_real_bundle(), dataset_sig="别的一份数据集"))
    assert deps.current_bundle().source is None, "对不上的那一份不许当当前模型"


def test_特征组对不上的包不许当当前模型(clean, db):
    """⭐ Review Focus 3。

    规格书 §5.5 说库内特征组是个常量，所以只比数据集签名也够 —— 但那句话
    **依赖页② 把特征组写死**（`calibration_jobs.py`）。哪一天页② 允许挑
    特征组，少了这一比，页③ 就会拿按 A 组特征搜出来的参数去跑 B 组特征，
    而屏上看起来完全正常。多比一个字符串，把那条路堵在门口。
    """
    import dataclasses

    _finished(dataclasses.replace(_real_bundle(), feature_groups=("coord",)))
    assert deps.current_bundle().source is None


def test_再跑一次训练_上一份就退场了(clean, db):
    """新的 job 一提交，`jobs._CURRENT` 就指过去了，而新 job 的 result 是 None。

    ⚠️ 第二次提交可以用一句立刻返回的空活：它只需要把 `_CURRENT` 换掉，
    跑成什么状态都无所谓 —— `done` 以外的任何状态都让 `unsaved_bundle()`
    给 None。
    """
    _finished(_real_bundle())
    assert deps.current_bundle().source == "unsaved"

    jobs.submit(lambda j: None)                # 又跑一次
    assert deps.current_bundle().source is None
