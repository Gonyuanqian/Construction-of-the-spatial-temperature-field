"""模型库的四条路由（规格书 §5.2）。

**这个模块不碰数据集缓存、不建管线** —— 它读写的是库。兼容性判定要问
`deps.get_train_dataset()` 拿当前训练段的签名（那是「现在在用的是哪一份」
唯一的地方），也仅此而已。**没有当前数据集时**（2026-10-16 起）改用页⑤ 自己
那份 `configs/live/train.xlsx` —— 页⑤ 已经不依赖「当前数据集」了，它的模型门
不能还挂在同一个指针上。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from tfield import config as C
from tfield.calibration import groups_signature

from .. import deps, jobs, models_store, paths, ported
from ..errors import NoDatasetError
from .calibration import _jsonable

router = APIRouter(tags=["models"])

#: 请求体形状不对时给的提示。与 `calibration.py` 那两句同一个手法：
#: 报的是一句话，前端 `client.ts` 直接 `String(body.detail)` 印出来。
_NAME_HINT = '请求体要长成 {"name": "棚里那套"} 这样。'

#: 名字的长度上限。**等于列宽 `VARCHAR(120)`**：比它长的名字在严格模式下
#: 会被 MySQL 报 1406（一个 500），在这里先拦成一句人话。
_MAX_NAME = 120

#: 没有数据集时，一行**没有成品**的模型要说的那句话。
#:
#: ⚠️ 这一档只在**没有数据集**时出现（规格书 D6）。有数据集时 `compatible`
#: 一个字都没改 —— 特征组对不上是**输入类型**对不上，成品让**参数**不再依赖
#: 数据，没让特征列不依赖。
_NO_ARTIFACT_WHY = "这一条还没有成品，先导入数据集才能用"


def _compat(row: models_store.ModelRow, ds, current_file: str) -> deps.ModelFit:
    """这一行**对得上**当前训练段吗；对不上时说是哪一轴。

    ⚠️ **判定只有一处（`deps.model_fit`），这里不许自己比**（2026-10-10 用户
    裁定「模型不绑数据集」）。原先这一份只看数据集签名与文件名，而构场那条路
    上的 `deps._usable` **还比特征组** —— 于是一行按别的特征组标出来的模型，
    列表说「能用」，选它当当前模型却会被丢开、退回兜底参数，屏上一个字不提。
    两套定义不会报错，只会慢慢漂。

    ⚠️ 比较用的特征组是**当前那一组**（`C.DEFAULT_FEATURE_GROUPS`）而不是行上
    那一列的名字 —— 库里只有 `groups_sig` 这个 8 字符的签名，名字早就没了。
    两者本该是同一件事（`models.py:307` 就是把 `bundle.groups_sig` 写进去的）。

    ⚠️ 分两种理由不是措辞讲究：签名里掺了文件的 **mtime**，所以「换了一份数据集」
    与「同一个文件原地重存过一次」都会让签名对不上，而后者用户根本没换数据 ——
    只说「数据来源不同」，他会去重新导入一份，然后发现还是不行。

    返回整个 `ModelFit` 而不是一个布尔：两轴各自是个独立的事实，而屏上要的是
    **三档**（用不了 / 本地的 / 借来的）。压成一个布尔就只剩两档，第三档要靠
    前端去猜 `why` 为什么非空 —— 那是把判据搬到另一门语言里重写一遍。
    """
    return deps.model_fit(
        dataset_sig=row.dataset_sig, groups_sig=row.groups_sig,
        ds=ds, current_groups_sig=groups_signature(tuple(C.DEFAULT_FEATURE_GROUPS)),
        data_file=row.data_file, current_file=current_file)


@router.get("/models")
def list_models() -> dict[str, Any]:
    """列表。每行附 `compatible` / `borrowed` / `why`（相对**当前**数据集判定）。

    `compatible` = **能拿来构场**，只看特征组那一轴（用户裁定：模型不绑数据集，
    库里有就能挑）。`borrowed` = 能用、但这一份的参数**不是**为当前这份数据标
    的 —— 两轴各自的独立事实，屏上因此有三档：用不了 / 本地的 / 借来的。

    ⚠️ **没有数据集时不再 409**（规格书 D5）。这一格原先每次都要
    `deps.get_train_dataset()`，于是「模型库」这个动作在没有数据集时整页打不开 ——
    而「库里有哪些模型」这件事**本来就不需要数据集**。降级之后，能不能用成了
    **这一行自己的性质**：有没有成品。
    """
    try:
        ds = deps.get_train_dataset()
        current_file = deps.current_dataset_path().name
    except NoDatasetError:
        # 2026-10-16：没有当前数据集时，判定轴换成页⑤ **自己的**训练段。
        # 理由：页⑤ 从这一天起不依赖「当前数据集」，而它的模型门是
        # `usableModels(...).length > 0`（只看 `compatible`）—— 不接这一步，
        # 闸门放行了，用户还是被另一张卡挡在门外。
        try:
            ds = deps.live_train_dataset()
            current_file = paths.LIVE_TRAIN.name
        except (NoDatasetError, FileNotFoundError):
            ds, current_file = None, None

    mid = models_store.current_id()
    rows: list[dict[str, Any]] = []
    for row in models_store.list_models():
        d = row.to_dict()
        if ds is None:
            d["compatible"] = row.has_artifact
            d["borrowed"] = False
            d["why"] = "" if row.has_artifact else _NO_ARTIFACT_WHY
        else:
            fit = _compat(row, ds, current_file)
            d["compatible"] = fit.same_groups
            # ⚠️ 用不了的行**不叫借来的**：那是「能借来用、但不是这份数据标的」的
            # 意思。两轴都不对时两个标一起挂上去，读的人得先自己判哪个说了算。
            d["borrowed"] = fit.same_groups and not fit.same_data
            d["why"] = fit.why
        d["is_current"] = row.id == mid          # 以 current_id 为准，不读那一列
        rows.append(d)
    return {
        "rows": rows,
        "current_id": mid,
        # ⚠️ 没有数据集时是 `None`，**不是空串**：空串与「数据集的文件名恰好是
        # 空」在屏上长得一样，而前端要拿它决定「在比的是哪一份」那句话写不写。
        "dataset_file": current_file,
        "dataset_sig": None if ds is None else ds.signature,
    }


@router.get("/models/{model_id}")
def get_model(model_id: int) -> dict[str, Any]:
    """详情：参数、效果、搜索区间。**不含逐测点表，也不含 trials 逐条。**

    不带 trials 是量级问题（794 KB 的大头在屏上没地方放，也没有这个需求）；
    不带逐测点表是**用户已经裁定过的事** —— 他刚把页② 那张逐点误差表撤掉
    （「没必要展示」），详情页再摆一张就是同一个东西换个地方（规格书 §6.1）。
    """
    row = models_store.get_model(model_id)
    if row is None:
        raise HTTPException(status_code=404, detail="没有这个模型")
    bundle = models_store.load_bundle(model_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="这个模型的参数读不出来了")
    return {
        **row.to_dict(),
        # ⚠️ 与 `saved_at` **不是一回事**：那是用户点保存的时刻，这个是标定
        # 跑完的时刻。平时只差几秒，语义不同 —— 页上写「保存于」。
        "created_at": bundle.created_at,
        "tool_version": bundle.tool_version,
        "feature_groups": list(bundle.feature_groups),
        "trend_kind": bundle.trend_kind,
        "trend_params": dict(bundle.trend_params),
        "metric": {"lx": bundle.metric.lx, "ly": bundle.metric.ly,
                   "lz": bundle.metric.lz, "power": bundle.metric.power},
        "cross_shed": bool(bundle.cross_shed),
        "tuned_keys": list(bundle.tuned_keys),
        "folds": list(bundle.folds),
        "metrics": [
            {k: (str(v) if k in ("fold", "region", "group", "tag", "fold_kind")
                 else _jsonable(v))
             for k, v in r.items()}
            for r in bundle.metrics.to_dict(orient="records")
        ],
        # ab 里三个数是从包里来的浮点，同样要过 `_jsonable` 那道 `_finite`
        # （NaN 会让 `allow_nan=False` 的 JSONResponse 当场 500）。
        "ab": ({k: _jsonable(v) for k, v in bundle.ab.items()}
               if bundle.ab is not None else None),
        "plateau": [{"dim": k, "lo": ported.fmt_value(lo), "hi": ported.fmt_value(hi)}
                    for k, (lo, hi) in bundle.search.plateau.items()],
        "best": {k: _jsonable(v) for k, v in bundle.search.best.items()},
        "n_trials": int(bundle.search.n_trials),
        "seed": int(bundle.search.seed),
    }


@router.post("/models", status_code=201)
def save_model(body: Any = Body(None)) -> dict[str, Any]:
    """把**刚跑完的那一次**存进库，并置为当前（规格书 D7）。

    **前端只发一个名字。** 落库的那一份是从 job 对象上取的，不走浏览器搬
    794 KB —— 也不给前端一个「我随便发一份包上来」的口子。

    409 而不是 422 的分界：请求本身没错（名字是好的），是**现在不能做这件事**
    —— 手上没有刚跑完的那一份。也不许「凭当前模型再造一行」：那就成了
    「保存」一个已经保存过的东西，而库里会多出一行谁都分不清的副本。

    ⚠️ 形参写 `Any` 而不是 `dict[str, Any]`：写了 `dict` 之后 FastAPI 自己
    就会把数组 / 字符串这一类请求体拦成 422，下面那句 `_NAME_HINT` 便成了
    **够不到的死代码**。与 `calibration.py` 的 `post_diagnostics` 同一个写法。
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail=_NAME_HINT)
    raw = body.get("name")
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(status_code=422, detail="模型名字不能是空的。")
    name = raw.strip()
    if len(name) > _MAX_NAME:
        raise HTTPException(status_code=422,
                            detail=f"模型名字最多 {_MAX_NAME} 个字。")

    got = deps.current_bundle()
    if got.source != "unsaved" or got.bundle is None:
        raise HTTPException(
            status_code=409,
            detail="手上没有刚跑完的模型。先到「模型训练」那一页跑一次标定。")

    ds = deps.get_train_dataset()
    file = deps.current_dataset_path().name
    # ⚠️ **在这一句拿管线**：`deps.get_pipeline()` 走 `current_bundle()`，
    # 而此刻「当前那一份」就是刚跑完、还没保存的那一份（unsaved 档），
    # 于是它正是要固化的这份模型的管线。放在 `save_model` 之后拿，
    # 拿到的就是**刚写进去那一行**的管线，而不是这份。
    pipe = deps.get_pipeline()
    row = models_store.save_model(name, got.bundle, ds, file,
                                  artifact=pipe.capture().to_bytes())
    jobs.retire_result()      # ← 保存成功即退场（规格书 §5.4）
    return row.to_dict()


@router.post("/models/{model_id}/current")
def set_current(model_id: int) -> dict[str, Any]:
    """设为当前。**顺手把「刚跑完那一份」摘掉。**

    不摘的话第一顺位永远命中它，用户刚点的这个模型在页③ 上一动不动，
    而屏上没有一个字提示这件事。规格书 §5.4 只写了「保存」与「再跑一次」
    两个退场条件；这一条是第三个，同一条理由。
    """
    if models_store.get_model(model_id) is None:
        raise HTTPException(status_code=404, detail="没有这个模型")
    models_store.set_current(model_id)
    jobs.retire_result()
    return {"id": model_id, "is_current": True}
