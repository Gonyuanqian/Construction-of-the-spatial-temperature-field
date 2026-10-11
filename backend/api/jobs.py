"""长任务的记账本：提交、轮询、取消。

**为什么单独一个模块**：它不是路由（`api/routes/` 下的东西只负责把 HTTP
翻成函数调用），也不属于 `deps`（那个管数据集与管线）。它管的是「一个
进程内跑着的长任务」，两个路由模块都要用。

**为什么不落盘**：重启回「没有 job」，与「启动时是空态」是一条规则
（规格书 §4.6）。job 的 id 只在这一段进程生命的内部有意义。

**为什么互斥不写锁**：执行器 `max_workers=1` 本身就是互斥（规格书 §4.2）。
再写一把锁就是同一个保证有两个实现，而它们迟早会不一致。
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

#: 四态。字符串常量而不是 Enum：它们要原样进 JSON，Enum 还要多一层转换，
#: 而多出来的那层正是「某个分支忘了转」的地方。
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    created_at: str
    state: str = RUNNING
    progress: str = ""
    error: str | None = None
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    #: 跑出来的那一份结果（现在是 `CalibrationBundle`）。
    #:
    #: **只在这一次会话里**：不落盘、不进 `to_dict()`、进程一停就没了 ——
    #: 与「不保存就丢掉」是同一条规则（规格书 §5.3）。放这里而不是写回盘，
    #: 是因为「训完的模型要不要留下」现在由用户回答，不由系统替他回答。
    #:
    #: 不进 `to_dict()` 不是省事：轮询接口每次都要序列化它，而这一份是
    #: 794 KB —— 前端每两秒问一次「跑到哪一句了」，不该拖着 794 KB 走。
    result: Any = None

    def elapsed_s(self) -> float:
        now = self.finished if self.finished is not None else time.monotonic()
        return round(now - self.started, 1)

    def stop_requested(self) -> bool:
        """库的 `should_stop` 回调收的就是它。"""
        return self.cancel.is_set()

    def to_dict(self) -> dict[str, Any]:
        """**摘要**，不是结果。

        图上那些数不在这里（规格书 §4.1：轮询要轻）。诊断另有一条出口，
        按包缓存 —— 把它塞进这里，每次轮询就要拖着三千六百个计数走。
        """
        return {"id": self.id, "state": self.state, "progress": self.progress,
                "elapsed_s": self.elapsed_s(), "error": self.error,
                "created_at": self.created_at}


#: `max_workers=1`：**互斥由执行器保证**。线程名带前缀，出问题时栈里看得出是谁。
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="calibration-job")

_JOBS: dict[str, Job] = {}
_CURRENT: str | None = None
_LOCK = threading.Lock()


def get(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def current() -> Job | None:
    """当前 / 最近一次 job。一次都没跑过就是 None（刚启动时就是它）。"""
    with _LOCK:
        return _JOBS.get(_CURRENT) if _CURRENT is not None else None


def clear() -> None:
    """打回「一次都没跑过」。测试用，也是「重启」的替身。"""
    global _CURRENT
    with _LOCK:
        _JOBS.clear()
        _CURRENT = None


def retire_result() -> None:
    """把「刚跑完的那一份」摘掉。**保存成功、显式换模型时都要调它。**

    为什么不靠 job 自己的状态：`POST /api/models` 存成功之后那个 job 还是
    `done`、`result` 也还在，于是 `current_bundle()` 的第一顺位永远命中它 ——
    用户在库列表里把**另一个**模型设为当前，页③ 上一点变化都没有，而屏上
    没有一个字提示这件事。摘掉它，第二顺位才轮得上。
    """
    job = current()
    if job is not None:
        job.result = None


def set_progress(job: Job, line: str) -> None:
    """库的 `progress` 回调收的就是它。只保留**最近一行**（规格书 §4.3）。"""
    job.progress = line


def finish(job: Job, state: str, *, error: str | None = None) -> None:
    """下一个结论并停表。**`done` 必须等包真的落盘之后再置**（规格书 §5.1 第 4 步）。"""
    with _LOCK:
        job.state = state
        job.error = error
        job.finished = time.monotonic()


def submit(work: Callable[[Job], None]) -> Job:
    """登记一个 job 并交给执行器。

    `work` 收 job 本身：它据此报进度（`set_progress`）与问取消
    （`job.stop_requested`）。**它负责下结论**（调 `finish`）；
    没下结论就返回的那些由 `_run` 兜成 `failed`。
    """
    global _CURRENT
    job = Job(id=uuid.uuid4().hex[:12],
              created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with _LOCK:
        _JOBS[job.id] = job
        _CURRENT = job.id
    _EXECUTOR.submit(_run, work, job)
    return job


def _run(work: Callable[[Job], None], job: Job) -> None:
    """执行器线程的入口。

    ⚠️ 捉 `BaseException` 而不是 `Exception`：线程里抛出去的东西会落进
    `Future`，而没有人 `result()` 它 —— 结果是 job 永远停在 `running`，
    界面永远转圈，且**没有任何一处报错**。宁可把 `MemoryError` 说成
    「这一次失败了」，也不要一个不会结束的转圈。
    """
    try:
        work(job)
    except BaseException as exc:                      # noqa: BLE001
        job.result = None     # 半途而废的那一份不许留下：它没走完该走的检查
        finish(job, FAILED, error=f"{type(exc).__name__}: {exc}")
    else:
        if job.state == RUNNING:                      # work 忘了下结论
            finish(job, FAILED, error="任务结束了但没有给出结论")
