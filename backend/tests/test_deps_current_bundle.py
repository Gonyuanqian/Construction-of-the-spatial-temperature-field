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

import conftest                                              # noqa: E402
from api import deps, jobs, models_store, paths            # noqa: E402


def _real_bundle():
    """交付数据集训练段那一份真包，**已重签成本机指纹**。**只读**。

    ⚠️ 不能图省事写 `sorted(paths.CONFIGS.glob("bundle_*.json"))[0]`：本机盘上
    有**四份**包，排序第一的是 `bundle_0066856dc40a8bbc-…`（**另一份数据集**
    标的）；本机取到它、别人的克隆里取到的是交付那一份 —— 同一个文件在两台
    机器上测的是两份不同的包。取错那一份，`current_bundle()` 会（**正确地**）
    判它「与训练段对不上」而退回库里 —— 于是这个文件里的每一条测的都是
    「对不上」，包括那三条本该测「刚跑完的那一份」的。红/绿都还在，测的东西
    换了，而没有一个字提示。

    ⚠️ 指纹为什么非要在夹具里重签一次，见 `conftest._delivered_bundle`。
    """
    return conftest.delivered_train_bundle()


def _other_bundle():
    """一份**为别的数据集标的**包。**只读**。

    ⚠️ 是**合成**的（拿交付那份换个签名），不是从盘上找一份别人的 —— 盘上
    有没有别的包取决于谁在这台机器上跑过标定（本机那两份 `0066856dc40a8bbc-…`
    与 `3fbf0c203b7d1b1f-…` 就没进仓库），别人的克隆里没有。

    ⚠️ 用它而不是把库里那行的 `dataset_sig` 改掉：**行与包必须一起变**。
    `current_bundle()` 从行上读、`_build_pipeline` 从包上读，只改一处就会造出
    一个线上不可能出现的状态（行说是 A、包说是 B），测的东西就换了。
    换的是**这一个包对象**，而 `save_model` 把它的签名抄进行里、把整包写进
    LONGTEXT —— 所以行与包是一起变的。
    """
    return conftest.bundle_for_another_dataset()


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


def test_库里的模型就是为当前数据标的时_没有那句话(clean, db):
    """对得上时 `mismatch_note` 是**空串**，不是 None（与 `ModelRow.why` 同一条房规）。

    这一条钉的是「别把三个状态压成两个」：没模型、借来的、本地的，三档。
    """
    ds = deps.get_train_dataset()
    models_store.save_model("本地的", _real_bundle(), ds, "f.xlsx")
    got = deps.current_bundle()
    assert got.source == "library"
    assert got.mismatch_note == ""


def test_库里那一份是为别的数据标的时_照用并如实报出来(clean, db):
    """⭐ 2026-10-10 用户裁定：「只要是模型库中有模型，就能选择模型库中的
    任意一个模型来构建，而不是绑定数据集。」

    原先库里那一档也走 `_usable`，数据集签名对不上就**整份丢掉**、退回兜底
    参数 —— 于是「库里有模型、页③⑤ 却说没有可用的模型」，而用户手上那份模型
    是好的，只是文件名或 mtime 变了（签名里掺了 mtime，`loader.py:29`）。
    现在照用，把实情报出去，判定权交给用户。
    """
    ds = deps.get_train_dataset()
    other = _other_bundle()
    row = models_store.save_model("别处标的", other, ds, "别人家的棚.xlsx")

    got = deps.current_bundle()
    assert got.source == "library", "用户点了它当当前模型，就该用它"
    assert got.bundle is not None, "对不上数据集不该再把它丢掉"
    assert got.bundle.dataset_sig == other.dataset_sig, "用错了那一份"
    assert got.mismatch_note, "借来的那一份必须如实报出来"
    assert row.id == models_store.current_id()


def test_库里那一份的特征组对不上时_仍然不许当当前模型(clean, db):
    """⭐ 2026-10-10 Ruling R1：数据集那一轴放行，**特征组那一轴仍然硬拦**。

    那不是「哪一份数据」的问题，是**输入类型**的问题：`_build_pipeline` 用的是
    传进来的 `groups` 去 `build_features`，拿另一组特征拟出来的矩阵去配这份
    参数，要么尺寸对不上当场炸，要么静默画错。

    ⚠️ 与上一条合起来看才完整：**放行的只有一轴**。只测上一条的话，把整个
    闸门拆掉也会全绿。
    """
    ds = deps.get_train_dataset()
    row = models_store.save_model("别组特征标的", _real_bundle(), ds, "f.xlsx")
    conn = models_store.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE model SET groups_sig = %s WHERE id = %s",
                        ("00000000", row.id))
        conn.commit()
    finally:
        conn.close()
    got = deps.current_bundle()
    assert got.bundle is None, "特征组对不上的那一份不许当当前模型"
    assert got.source is None
