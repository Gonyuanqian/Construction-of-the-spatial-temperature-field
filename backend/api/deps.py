"""进程内的依赖：数据集缓存与管线缓存。

**为什么必须有**
    `load_dataset()` 读那个 1308 × 52 的 xlsx，实测 **0.96–1.00 秒**
    （三个全新进程各冷加载一次），没有任何缓存。
    页① 要打四个接口，一个都不缓存就是「打开一页等三四秒」。
    这是服务端问题 —— HTTP 无状态，每个请求重建一次数据集不可行。

**缓存键是什么**
    数据集的**文件身份** = (绝对路径, mtime_ns, 大小)，与 `dataset_signature`
    用的是同一组要素，但用途不同：签名回答「这个标定包属于谁」，
    这里回答「这份内存对象还对得上盘上的文件吗」。
    用户重新导出一次数据集 → mtime 与大小变 → 键变 → 自动重新加载，**不需要手动失效**。

    ⚠️ 不能拿 `Dataset` 自己当键：它是 frozen dataclass，但字段里有 DataFrame，不可哈希。

**为什么加锁**
    FastAPI 的同步端点跑在线程池里，两个请求可以同时到。
    锁保证「同一个文件只加载一次」这句话在并发下也成立 ——
    而且后到的那个线程**等前面那个装完就直接命中**，不是白等。
"""
from __future__ import annotations

import pathlib
import threading
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from tfield.artifact import ArtifactError, ArtifactVersionError, PipelineArtifact
from tfield.calibration import groups_signature
from tfield.data.loader import HOLDOUT_CUTOFF, Holdout, load_dataset, split_holdout
from tfield.data.types import Dataset
from tfield.features import build_features
from tfield.pipeline import FieldPipeline, PipelineConfig

from . import models_store, paths
from .errors import NoDatasetError

Capacity = int
FileKey = tuple[str, int, int]


class DatasetCache:
    """按文件身份缓存 Dataset。容量默认 4（一个演示里最多来回切几个数据集）。"""

    def __init__(self, *, loader: Callable[[pathlib.Path], Dataset] | None = None,
                 capacity: Capacity = 4) -> None:
        self._loader = loader or load_dataset
        self._capacity = int(capacity)
        # dict 保插入序 —— LRU 就靠这个：命中时 pop 再塞回去（提到队尾）
        self._items: dict[FileKey, Dataset] = {}
        self._lock = threading.Lock()
        self.n_loads = 0                 # 测试用它证明「真的只加载了一次」

    @staticmethod
    def key_of(path: pathlib.Path | str) -> FileKey:
        """文件的身份。文件不存在时**让它抛 FileNotFoundError** —— 路由层负责翻成 404。"""
        p = pathlib.Path(path)
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size)

    def get(self, path: pathlib.Path | str) -> Dataset:
        key = self.key_of(path)          # 先 stat（在锁外）：不存在就直接抛，不占锁
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items[key] = self._items.pop(key)      # 命中即提到队尾
                return hit

            # 加载放在锁里：并发时第二个线程等在这里，醒来就命中，
            # 不会出现「两个线程各 load 一遍」。
            ds = self._loader(pathlib.Path(path))
            self._items[key] = ds
            while len(self._items) > self._capacity:
                self._items.pop(next(iter(self._items)))     # 淘汰最久未用的
            self.n_loads += 1
            return ds


# ══════════════════════════ 管线缓存 ══════════════════════════
#: 管线身份 = (数据集签名, 特征组签名, 标定包 created_at)。
#: 三者任一变了就是**另一份**管线 —— 少一个维度，换了那份东西还会命中旧管线。
PipelineKey = tuple[str, str, str]

#: 未标定时的哨兵。**不用 None**：None 进不了 JSON 之外的语境也会让 `dict` 的键
#: 类型变成 `str | None`，而「没有包」与「包的空 created_at」本该是同一个键。
NO_BUNDLE = ""


#: 借来的那一份模型**在构场这一路上**要报的那句话（2026-10-10 用户裁定
#: 「模型不绑数据集」）。
#:
#: ⚠️ **只此一句**：页③ 那一栏、页⑤ 的图章说明、`/api/calibration` 的那一格，
#: 读的都是它。同一个事实在两处各写一句措辞，迟早会一处改了一处没改。
#: 带文件名的详细 why 是**列表行**的事（`model_fit`）—— 那里有 `data_file`，
#: 而这里手上只有包与数据集，说不出「是换了哪一份」。
_BORROWED_NOTE = "这一份模型的参数不是用当前这份数据标出来的 —— 参数照用，误差数不算它的成绩。"


#: 成品读不动时，屏上要多的那一句。**两种错两句不同的话**（规格书 D7/D8）——
#: 「格式我还不认识」要人做的是升级，而「字节坏了」要人做的是重新训一遍。
#: 合成一句，这两种处境就分不开了。
def _artifact_note(e: ArtifactError) -> str:
    if isinstance(e, ArtifactVersionError):
        return (f"这一条的成品读不动（格式是第 {e.found} 版，现在是第 "
                f"{e.expected} 版），已退回现训。")
    return "这一条的成品读不动（字节坏了），已退回现训。"


def _artifact_of(bundle) -> tuple[bytes | None, str]:
    """当前这一份模型该用的成品字节，以及读不动的理由。→ `(字节, 理由)`。

    ⚠️ **认包、不认「当前那一行」。** `_build_pipeline` 手上这份包可能是
    「刚跑完还没保存」的那一份（`current_bundle` 的 unsaved 档），它**没有行** ——
    这时库里「当前」那一行的成品是**另一个模型**的，装上去就是凭空换了一个模型，
    而屏上没有一个字会提示。用 `created_at` 判「手上这份包就是库里那一行」，
    那是 `PipelineCache` 已经在用的包身份（`deps.py:81`）。

    ⚠️ **不能用 `dataset_sig` + `groups_sig` 判**：重训一次得到的是同一份数据、
    同一组特征，两列全等 —— 于是刚跑完还没保存的那一份会被判成「就是库里那一行」，
    装上的是**上一次**的模型。

    ⚠️ 库里那一行读不动时**不在这里报**：这条路上从来读过它，
    为成品而新引入一次读，不该顺带新引入一种 500。真读不动时
    `current_bundle()` 会在同一个请求里自己抛（它读的是同一行）。

    ⚠️ **三句读库一起进同一个 try**（Review Focus 4 的另一半）：`current_id()`
    与 `artifact_of()` 早先漏在 try 外面，任一句抛出都会把「刚跑完还没保存」
    那一档本来好用的请求变成 500 —— 而那一档（`current_bundle` tier 1）到今天
    为止**根本不读库**，那正是 MySQL 挂掉时构场仍能出图的原因。读不动就当
    「这一条没有成品」，退回现训：慢，但对。
    """
    if bundle is None:
        return None, ""
    try:
        mid = models_store.current_id()
        if mid is None:
            return None, ""
        other = models_store.load_bundle(mid)
        if other is None or other.created_at != bundle.created_at:
            return None, ""
        raw = models_store.artifact_of(mid)
    except Exception:       # noqa: BLE001 —— 见上面那段：这条路上它从没读过库
        return None, ""
    if raw is None:
        return None, ""
    try:
        PipelineArtifact.from_bytes(raw)          # 只验，不在这里用
    except ArtifactError as e:
        return None, _artifact_note(e)
    return raw, ""


def _mark_calibrated(pipe: FieldPipeline, bundle, *,
                     mismatch_note: str = "",
                     artifact_note: str = "") -> FieldPipeline:
    """把「配置从哪来」写进管线**自己**身上。

    路由层据此照实标注（spec §七 V3：兜底参数「不是最优，只是不在坏角上」，
    与标定后的数**同折族、不同参数，不可直接比大小**）。写成管线的属性而不是
    一个查询函数，是为了让 `_build_pipeline` 的每条返回路径**不可能忘记**设它 ——
    忘记的后果是界面把兜底的数标成「已标定」，而这正是最不能错的一处标注。

    ⚠️ `mismatch_note` 走关键字、带默认空串：它是 2026-10-10 才有的**第三档**
    （「已标定」里再分「本地的」与「借来的」），原先的两档调用点只有两个位置
    参数，不该被逼着一起改。

    ⚠️ `artifact_note` 是**另一个格子**，不是 `mismatch_note` 的第二份用法。
    `frontend/src/design/copy.ts:225` 的 `calibratedLabel` 用「`mismatch_note`
    里有没有话」判「已标定（借来的）」—— 把成品的理由塞进那个格子，一份**本地**
    的模型会在屏上自称「借来的」。
    """
    pipe.calibrated = bundle is not None        # type: ignore[attr-defined]
    pipe.mismatch_note = mismatch_note          # type: ignore[attr-defined]
    pipe.artifact_note = artifact_note          # type: ignore[attr-defined]
    return pipe


def _borrowed(ds: Dataset, bundle) -> bool:
    """这一份包的参数**不是为这个训练段拟的**吗。

    ⚠️ 判据只看**数据集那一轴**（Ruling R1）：特征组那一轴对不上的包在
    `current_bundle` 就被拦在门外了，走不到这里。

    ⚠️ 比的是**包上**那一列，而 `current_bundle` 比的是**库的那一行上**那一列 ——
    两者是同一件事的两个副本（行上那份是保存时从包上抄的），只可能被手工改动
    弄分叉。手上有什么就比什么：这里只有包。

    ⚠️ 摘成函数是为了让这个判据**有一个便宜的落点**：它唯一的调用点在
    `_build_pipeline` 里，而那里一句 `fit()` 就是几十秒 —— 不摘出来，这个
    判据就只能靠一条 slow 用例捎带着验。判反了的后果是屏上给借来的模型盖
    「已标定（本地的）」的章：数的来历整个说反。
    """
    return bundle is not None and bundle.dataset_sig != ds.signature


def _build_pipeline(ds: Dataset, groups: tuple[str, ...], bundle) -> FieldPipeline:
    """有成品就装上（0.25 s），没有或读不动就现训（10~21 s）。

    未标定走 `PipelineConfig.fallback()`（**不是最优，只是不在坏角上**）——
    这条路在界面上必须标成「未标定」。

    ⚠️ **两条路都必须过 `_mark_calibrated`。** 装上成品那条路若绕开它，
    `calibrated` / `mismatch_note` / `artifact_note` 三个属性就不在管线上，
    而屏上那些 `getattr(pipe, ..., False)` 会静默退成「未标定」——
    一份标定好的模型在页③ 上自称兜底参数。
    """
    cfg = bundle.config() if bundle is not None else PipelineConfig.fallback()
    note = ""
    if bundle is not None:
        raw, note = _artifact_of(bundle)
        if raw is not None:
            art = PipelineArtifact.from_bytes(raw)
            pipe = FieldPipeline(cfg, ds).restore(
                art, fs=build_features(ds, groups))
            return _mark_calibrated(
                pipe, bundle,
                mismatch_note=_BORROWED_NOTE if _borrowed(ds, bundle) else "",
                artifact_note=note)

    pipe = FieldPipeline(cfg, ds).fit(build_features(ds, groups), ds)
    return _mark_calibrated(pipe, bundle,
                            mismatch_note=_BORROWED_NOTE if _borrowed(ds, bundle)
                            else "",
                            artifact_note=note)


class PipelineCache:
    """按管线身份缓存 `FieldPipeline`。容量默认 4 —— 一个演示里最多来回切几个数据集。

    与 `DatasetCache` 同形是**故意的**：两个缓存的失效规则必须读起来一样，
    否则「为什么这次没生效」会在两个不同的心智模型之间来回甩。
    """

    def __init__(self, *, builder=None, capacity: Capacity = 4) -> None:
        self._builder = builder or _build_pipeline
        self._capacity = int(capacity)
        self._items: dict[PipelineKey, FieldPipeline] = {}
        self._lock = threading.Lock()
        self.n_builds = 0

    @staticmethod
    def key_of(ds: Dataset, groups: tuple[str, ...], bundle) -> PipelineKey:
        return (
            ds.signature,
            groups_signature(groups),
            getattr(bundle, "created_at", None) or NO_BUNDLE,
        )

    def get(self, ds: Dataset, groups: tuple[str, ...], bundle) -> FieldPipeline:
        key = self.key_of(ds, groups, bundle)
        with self._lock:
            hit = self._items.get(key)
            if hit is not None:
                self._items[key] = self._items.pop(key)      # 命中即提到队尾
                return hit
            # 构建放在锁里：并发时第二个线程等在这里，醒来就命中，
            # 不会出现「两个线程各 fit 一遍」——那不只是浪费，是两次
            # 各要几十秒，前端等到超时。
            pipe = self._builder(ds, groups, bundle)
            self._items[key] = pipe
            while len(self._items) > self._capacity:
                self._items.pop(next(iter(self._items)))
            self.n_builds += 1
            return pipe


_PIPELINES = PipelineCache()


# ══════════════════════════ 当前数据集 ══════════════════════════
#: 「现在在用哪一份」。**只活在内存里**（规格书 §1.3 裁定 A）：不写状态文件，
#: 重启回空态 —— 与「启动时是空态」同一条规则。
#:
#: 为什么不做成 `paths.current_json()`：那会让「重启后屏幕上是什么」不再只由
#: 这次操作决定，而消灭那件事正是这个功能的目的。
_CURRENT: pathlib.Path | None = None


def set_current_dataset(path: pathlib.Path | str) -> None:
    """把「现在在用哪一份」指过去。**不校验文件在不在** —— 那是使用它的人的事。"""
    global _CURRENT
    _CURRENT = pathlib.Path(path)


def current_dataset_path() -> pathlib.Path:
    """现在在用的那一份。空态时抛 `NoDatasetError`（由 `main.py` 翻成 409）。"""
    if _CURRENT is None:
        raise NoDatasetError()
    return _CURRENT


def clear_current_dataset() -> None:
    """打回空态。测试与「重启」用。"""
    global _CURRENT
    _CURRENT = None


def install_dataset(path: pathlib.Path | str) -> None:
    """换数据集：**先清缓存，再改指针**（规格书 §4.2 第 5 步）。

    这两步合成一个函数而不是让调用点各写两行，只有一个理由：
    **顺序写反了不会有任何报错，只会有一个「新指针配旧缓存」的瞬间** ——
    而那一刻恰好是导入成功后的第一个请求。合成一个入口，顺序就不可能写反。

    它也顺手把白名单只撑大一个名字（`api/**` 从 `deps` 取名字受
    `tests/test_routes_use_cache.py` 守着）。
    """
    reset_cache()
    set_current_dataset(path)


#: 换数据集时要作废的**其余东西**的登记处。
#:
#: 四样要一起清（规格书 §三.1）：前三个是 `reset_cache()` 自己管的三个缓存，
#: 第四个是 `api/live.py` 的实时源 —— 它不在这里，而且 `live` 依赖 `deps`，
#: 反过来 import 成环。所以由 `live` 在 import 时**把自己登记进来**。
#:
#: 显式调用（上传路由里写两行）要求**每个未来的调用点**都记得调两次，
#: 而那正是今天这个漏的成因。「换数据集忘了清实时源」在结构上不可能发生，
#: 比「记得调」可靠。
_INVALIDATORS: list[Callable[[], None]] = []


def on_dataset_change(fn: Callable[[], None]) -> None:
    """登记一个「数据集换掉时请作废你自己」的回调。重复登记同一个函数无害。"""
    _INVALIDATORS.append(fn)


# ══════════════════════════ 用哪一份模型 ══════════════════════════
#: 「刚跑完、还没入库」的那一份挂在 job 对象上（`calibration_jobs._work` 的
#: 尾部写进去）。它排在第一顺位，所以必须有退场条件 —— 见 `retire_result()`。

@dataclass(frozen=True)
class CurrentBundle:
    """一次回答的**三**半：**用哪一份**、**它从哪来**、**它是不是为这份数据标的**。

    为什么把来源一起返回而不是另开一个函数：来源只有页② 用得上，而另开一个
    函数就得把「挑哪一份」的规则写第二遍 —— 两份实现迟早不一致，表现出来是
    页② 说「未入库」而构场用的是库里的那一份，屏上没有一处提示。

    ⚠️ `mismatch_note` 是 2026-10-10 用户裁定（「模型不绑数据集」）加上来的
    第三个状态。原先只有两档：**有包** / **没包**，于是「借来的」被塞进「没包」
    那一档 —— 屏上说的和库里存的对不上，而这是本屏最不能错的一处。
    """

    bundle: CalibrationBundle | None
    #: `"unsaved"` / `"library"` / `None`。前两个对应 §5.4 的两条来路。
    source: str | None
    #: 这一份包**不是**为当前训练段标的时候，那句要报出去的话；对得上时是
    #: **空串**（不是 None —— 前端不用判两种空，与 `ModelRow.why` 同一条房规）。
    #: 措辞就是 `_BORROWED_NOTE` 那一句，与构场那一路（管线上的同名属性）
    #: **同一个常量**。
    #: ⚠️ 只在 `source == "library"` 时可能非空：「刚跑完那一份」的那道闸门
    #: 还在（见 `current_bundle`），它过不来。
    mismatch_note: str = ""


def unsaved_bundle() -> CalibrationBundle | None:
    """本次会话刚跑完、还没入库的那一份。没有就 None。

    ⚠️ 只认 `DONE` 的 job：`CANCELLED` 与 `FAILED` 的那一次没有可用结果
    （`_work` 与 `_run` 都会把 result 清掉，这里再判一次是防将来有人改那两处）。
    """
    from . import jobs
    job = jobs.current()
    if job is None or job.state != jobs.DONE:
        return None
    return job.result


@dataclass(frozen=True)
class ModelFit:
    """一份模型**对得上**当前训练段吗，对不上的话是哪一轴不对。

    拆成两轴而不是一个布尔，是因为上层对这两轴的处理**不一样**（2026-10-10
    用户裁定「模型不绑数据集」）：

    · 数据集那一轴对不上 → 它就不是为这份数据标的，但**借来用是用户的事**
      （库里的模型都可以选），上层把它当**标签**报出去；
    · 特征组那一轴对不上 → 参数配的不是这套特征，**是输入类型对不上**，
      上层继续当**闸门**（见 `current_bundle` 第二档）。

    `why` 是给人看的一句话。对得上时是**空串**，不是 `None` —— 与
    `ModelRow.why` 同一条房规：前端不用判两种空。
    """

    same_data: bool
    same_groups: bool
    why: str

    @property
    def ok(self) -> bool:
        """两轴都对得上。**「能借来用」是另一件事**，别拿这个当那个。"""
        return self.same_data and self.same_groups


def model_fit(*, dataset_sig: str, groups_sig: str,
              ds: Dataset, current_groups_sig: str,
              data_file: str = "", current_file: str = "") -> ModelFit:
    """**全站唯一一处**回答「这一份模型对得上当前数据吗」。

    原先有两套口径：`routes/models.py::_compat` 只看数据集签名与文件名，而
    这里的 `_usable` **还比特征组**。于是一行按别的特征组标出来的模型，列表
    说「能用」，构场那条路却把它丢开、退回兜底参数 —— 屏上没有一个字提示这
    件事。两套定义不会报错，只会慢慢漂（这是 2026-10-10 用户裁定「模型不绑
    数据集」时揭出来的，不是那次改动引入的）。

    两个输入都是**签名**而不是名字：调用方手里有什么就用什么 —— 库那一行只有
    `groups_sig`（`ModelRow` **不带包**，一屏十行就是 8 MB），而包那一侧只有
    名字。签名本来就是为了比这一件事而存在的，所以两边都先化成它。

    ⚠️ 签名里掺了文件的 **mtime**（`loader.py:29`），所以「换了一份数据集」与
    「同一个文件原地重存过一次」都会让数据集那一轴对不上，而后者用户根本没换
    数据 —— 只说「数据来源不同」，他会去重新导入一份，然后发现还是不行。
    """
    same_groups = groups_sig == current_groups_sig
    if dataset_sig == ds.signature:
        return ModelFit(same_data=True, same_groups=same_groups,
                        why="" if same_groups else _GROUPS_WHY)
    if current_file and data_file == current_file:
        why = _TOUCHED_WHY
    else:
        why = f"数据来源不同：{data_file}" if data_file else "数据来源不同"
    return ModelFit(same_data=False, same_groups=same_groups, why=why)


#: 两条对不上的理由。写成常量是因为它们**逐字出现在测试的断言里**，
#: 而两处各写一遍必然有一天只改一处。
_GROUPS_WHY = "这一份是用别的特征组标出来的"
_TOUCHED_WHY = "同一个文件被改动过（内容或修改时间变了）"


def _usable(bundle, ds: Dataset, groups: tuple[str, ...]) -> bool:
    """这一份包能不能拿来给**这一份训练段**构场。

    比两样：数据集签名（它是不是为这份数据标出来的）与特征组（参数是按哪一组
    特征搜出来的）。规格书 §5.5 说只比签名也够 —— 因为库内特征组是个常量，
    而那句话**依赖页② 把特征组写死**（`calibration_jobs.py` 用的是
    `C.DEFAULT_FEATURE_GROUPS`）。多比一个字符串，把那条路堵在门口。

    ⚠️ 特征组那一半比的是**包里的名字**化成签名，不是包上那个 `groups_sig`
    字段：两者本该相同，但包是可以被造出来的（测试就 `dataclasses.replace`
    过 `feature_groups` 而不动 `groups_sig`），而**名字才是参数真正要配的
    那一样东西**。
    """
    return model_fit(dataset_sig=bundle.dataset_sig,
                     groups_sig=groups_signature(bundle.feature_groups),
                     ds=ds, current_groups_sig=groups_signature(groups)).ok


def current_bundle(groups: tuple[str, ...] | None = None) -> CurrentBundle:
    """**全站唯一一处回答「这次用哪一份模型」**（规格书 §5.4）。

    三档，按次序：

    1. 本次会话刚跑完、还没入库的那一份 → `"unsaved"`
    2. 否则库里的当前模型（**特征组对得上就照用**，数据集那一轴只报不拦）→ `"library"`
    3. 都没有 → `(None, None)`

    ⚠️ 第 1 条压在第 2 条上面，正是因为「用户刚跑完还没保存」时屏幕该显示
    **他刚跑的那一份**。它的两个退场条件在 `jobs.retire_result()` 与
    `jobs.submit()` 里（保存成功、再跑一次）。

    ⚠️ 每次请求读一次库（一行 LONGTEXT，约 794 KB）。这与它取代的
    `load_for()` 读一次 794 KB 的 JSON 是同一个量级 —— 而相对 fit 的几十秒
    可以忽略。`PipelineCache` 的键里含 `bundle.created_at`，所以「换模型 →
    场自动重算」这条链路是现成的。
    """
    from . import models_store
    from tfield import config as C
    groups = tuple(C.DEFAULT_FEATURE_GROUPS if groups is None else groups)
    ds = get_train_dataset()          # ← 模型认训练段，页① 认文件

    b = unsaved_bundle()
    if b is not None and _usable(b, ds, groups):
        return CurrentBundle(bundle=b, source="unsaved")

    # 第二档：库里的当前模型 —— **用户点了哪个就用哪个**（2026-10-10 用户裁定
    # 「只要是模型库中有模型，就能选择模型库中的任意一个模型来构建，而不是绑定
    # 数据集」）。数据集那一轴对不上**不再把它丢掉**，只如实报出去。
    #
    # ⚠️ 拦的只剩**特征组**那一轴（Ruling R1）：那不是「哪一份数据」的问题，
    # 是**输入类型**的问题 —— `_build_pipeline` 用的是传进来的 `groups` 去
    # `build_features`，拿另一组特征拟出来的矩阵去配这份参数，要么尺寸对不上
    # 当场炸，要么静默画错。判定一律走 `model_fit`，这里不许自己比。
    mid = models_store.current_id()
    if mid is None:
        return CurrentBundle(bundle=None, source=None)
    row = models_store.get_model(mid)
    b = models_store.load_bundle(mid)
    if row is None or b is None:
        return CurrentBundle(bundle=None, source=None)
    fit = model_fit(dataset_sig=row.dataset_sig, groups_sig=row.groups_sig,
                    ds=ds, current_groups_sig=groups_signature(groups),
                    data_file=row.data_file,
                    current_file=current_dataset_path().name)
    if not fit.same_groups:
        return CurrentBundle(bundle=None, source=None)
    # 报的是 `_BORROWED_NOTE` 这句**统一措辞**，不是 `fit.why` 那句带文件名的
    # 详细理由：构场那一路（`_build_pipeline`）手上没有 `data_file`，说不出
    # 「是换了哪一份」，两处各报各的迟早会分叉。带文件名的细节留给页③ 的列表行。
    return CurrentBundle(bundle=b, source="library",
                         mismatch_note="" if fit.same_data else _BORROWED_NOTE)


def get_pipeline(groups: tuple[str, ...] | None = None) -> FieldPipeline:
    """本项目管线的唯一入口。**路由层不许自己 new FieldPipeline、也不许自己 fit。**

    为什么它能与 `get_dataset` 并列成为 `api.deps` 的第二个出口：
    它**内部先调 `get_train_dataset()`**（而那个又调 `get_dataset()`），
    是数据集缓存的消费者而不是绕过者；
    让它当出口，是为了让「管线只构建一次」这条性质有一个**可计数**的落点
    （`PipelineCache.n_builds`），否则每个路由各 fit 一次，谁也数不出来。

    ⚠️ **它 fit 的是训练段，不是用户交进来的那份文件**（见 `get_train_dataset`）。
    页① 报的那份凭证与这里的世界**故意**不是同一个：模型不许看过留出段。
    """
    from tfield import config as C
    groups = tuple(C.DEFAULT_FEATURE_GROUPS if groups is None else groups)
    ds = get_train_dataset()          # ← 模型认训练段，页① 认文件
    # 每次请求问一次「用哪一份模型」—— 它的 `created_at` 是缓存键的一部分，
    # 不问就不知道键。相对 fit 的几十秒，这一次读可以忽略。
    return _PIPELINES.get(ds, groups, current_bundle(groups).bundle)


_CACHE = DatasetCache()


def get_dataset(path: pathlib.Path | str | None = None) -> Dataset:
    """本项目数据集的唯一入口。**路由层不许直接 import load_dataset。**

    `path=None` 时问「现在在用哪一份」：空态抛 `NoDatasetError`（由 `main.py`
    翻成 409），指针指着盘上没有的文件时抛 `FileNotFoundError`（翻成 404）。

    ⚠️ **这里不再回退到 `paths.dataset_path()`**（曾经是）。那条回退让
    「交付数据集」在启动时自动生效 —— 与规格书 §1.1「不预置、不代劳」
    正相反，而且它**不报错**：界面看起来一切正常，只是用的不是用户导的那一份。
    """
    if path is None:
        path = current_dataset_path()
    return _CACHE.get(path)


def probe_dataset(path: pathlib.Path | str) -> Dataset:
    """**试加载**：只回答「这份文件读不读得成数据集」，**不进任何缓存**。

    上传通道专用。它必须绕开 `_CACHE`，理由是**缓存键在这里从诞生起就是废的**：
    上传时文件还叫 `.<名字>.<pid>.part`，加载完紧接着就改名 ——
    按临时名算出来的 key 指向一个下一毫秒就不存在的路径。
    真放进缓存，它占掉 LRU 的一格，而且永远不可能再被命中。

    ⚠️ 它**不是** `get_dataset()` 的替代品：那个问的是「现在在用的是哪一份」，
    这个问的是「用户刚交上来的这一份能不能用」。两条问题不一样，
    合起来会让「当前数据集」这个指针被一次试加载悄悄改掉。

    为什么写在这里而不是 `api/uploads.py`：本仓有一条源码守卫
    （`tests/test_routes_use_cache.py`）规定 **`load_dataset` 只许出现在
    `api/deps.py`**。把试加载放进 `uploads.py` 就得给那个模块开一张
    整模块的白名单，而这里只需要多一个**点名**的出口。
    """
    return load_dataset(path)


#: 留出切分的缓存。键 = (数据集签名, 切点)。
#:
#: 切一次就是两次 iloc，不贵；记住它是为了让 `get_train_dataset()` 每次返回
#: **同一个** Dataset 对象 —— `PipelineCache` 的键虽然只看签名，
#: 但「同一次会话里训练段是同一份」这件事本身值得成立。
_HOLDOUTS: dict[tuple[str, str], Holdout] = {}


def _holdout(path: pathlib.Path | str | None = None,
             cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> Holdout:
    ds = get_dataset(path)
    key = (ds.signature, str(pd.Timestamp(cutoff)))
    hit = _HOLDOUTS.get(key)
    if hit is None:
        hit = split_holdout(ds, pd.Timestamp(cutoff))
        _HOLDOUTS[key] = hit
    return hit


def get_train_dataset(path: pathlib.Path | str | None = None,
                      cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> Dataset:
    """**模型与构场看得到的世界**：时间轴到 2026-07-27 11:55 为止的 1164 行。

    与 `get_dataset()` **分成两个出口**是这张规格书里唯一一处设计性的决定：

    - `get_dataset()` = 用户交进来的那份文件（页① 认证它）；
    - `get_train_dataset()` = 留出之后剩下的训练段（模型与场只用它）。

    合成一个出口的话，页① 会报「宽表 1164 × 52」却带着 `n_rows = 1308`
    的修复报告 —— 一份自相矛盾的凭证，而页① 的全部职责就是出自洽的凭证。
    """
    return _holdout(path, cutoff).train


def get_live_frames(path: pathlib.Path | str | None = None,
                    cutoff: pd.Timestamp = HOLDOUT_CUTOFF) -> pd.DataFrame:
    """**留出段**：实时模式一帧一帧接进时间轴的那 144 行（时间升序）。"""
    return _holdout(path, cutoff).live


def live_train_dataset() -> Dataset:
    """页⑤ 那条管线**拟合用的轴**：`configs/live/train.xlsx`，整份，不切。

    ⚠️ 它**不经过 `_holdout`**：这份文件**本身就是**训练那一半，再切一次只会
    得到「训练段 1164 + 留出段 0」。

    ⚠️ 写 `paths.LIVE_TRAIN` 这个**属性取值**，不能 `from .paths import LIVE_TRAIN`：
    测试靠 `monkeypatch.setattr(paths, "LIVE_TRAIN", …)` 把它指到 `tmp_path`，
    提前绑定会在 import 那一刻定型。
    """
    return get_dataset(paths.LIVE_TRAIN)


def live_playback_dataset() -> Dataset:
    """页⑤ 的**帧源**：`configs/live/live.xlsx`，整份，不切。

    同上：这份文件本身就是留出那一半，切点在这条路径上一次都不参与。
    """
    return get_dataset(paths.LIVE_FRAMES)


def reset_cache() -> None:
    """换数据集之后（上传、重新导出）显式清一次。**三个缓存一起清，再叫所有登记者作废自己。**

    只清数据集不清管线是最坏的组合：数据集重读了，管线还是按旧数据 fit 出来的，
    于是「数据被替换就重标」整条防线失效，而 `n_loads` 会显示「确实重读了」——
    一条看起来正常的错。

    ⚠️ 重建 `_CACHE` / `_PIPELINES` 是**换对象**不是 `clear()`：计数守卫
    （`test_end_to_end.py`）替换的是 `deps._CACHE` 这个模块属性，`clear()`
    会让它替换过的那个对象被清空、而模块属性还指着旧对象。
    """
    global _CACHE, _PIPELINES
    _CACHE = DatasetCache()
    _PIPELINES = PipelineCache()
    _HOLDOUTS.clear()      # 切分结果挂着旧的 Dataset 对象，留着就是「换了数据集还用旧训练段」
    for fn in _INVALIDATORS:      # ← 第四个：实时源（由 api/live.py 登记）
        fn()
