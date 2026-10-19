"""Java 编号的训练执行与暂存结果；数据库业务记录由 Java 维护。"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from functools import lru_cache
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from tfield import config as C
from tfield.calibration import (CalibrationAborted, CalibrationBundle, IDW_SPACE,
                                TOOL_VERSION, TREND_SPACE, groups_signature,
                                run_calibration)
from tfield.data.loader import HOLDOUT_CUTOFF

from . import deps, models_store, paths
from .dataset_context import DatasetContextError, current_context

INSTANCE_ID = str(uuid4())
_LOG = logging.getLogger("uvicorn.error")
_LOCK = threading.RLock()
_EXPORT_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="managed-training")
_STATES: dict[str, dict] = {}
_CANCEL: dict[str, threading.Event] = {}
_STARTED: dict[str, float] = {}
_LAST_WRITE: dict[str, float] = {}


def root() -> Path:
    value = os.environ.get("TFIELD_TRAINING_ROOT")
    path = Path(value) if value else paths.CONFIGS / "training-jobs"
    if not path.is_absolute():
        raise DatasetContextError(503, "训练暂存目录必须是绝对路径。")
    return path.resolve()


def directory(job_id: str) -> Path:
    try:
        canonical = str(UUID(job_id))
    except (ValueError, TypeError) as exc:
        raise DatasetContextError(422, "训练任务编号无效。") from exc
    parent = root()
    path = (parent / canonical).resolve()
    if not path.is_relative_to(parent):
        raise DatasetContextError(400, "训练任务位置无效。")
    return path


def _atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".part")
    try:
        with temporary.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _persist(state: dict) -> None:
    _atomic(directory(state["id"]) / "state.json",
            json.dumps(state, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    _LAST_WRITE[state["id"]] = time.monotonic()


@lru_cache(maxsize=1)
def spec() -> dict:
    defaults = inspect.signature(run_calibration).parameters
    sources = sorted((paths.BACKEND / "src/tfield").rglob("*.py"))
    algorithm = hashlib.sha256()
    for source in sources:
        algorithm.update(source.relative_to(paths.BACKEND).as_posix().encode("utf-8"))
        algorithm.update(b"\0" + source.read_bytes() + b"\0")
    value = {"tool_version": TOOL_VERSION, "feature_groups": list(C.DEFAULT_FEATURE_GROUPS),
             "groups_sig": groups_signature(tuple(C.DEFAULT_FEATURE_GROUPS)),
             "holdout_cutoff": str(HOLDOUT_CUTOFF), "seed": defaults["seed"].default,
             "n_trials": defaults["n_trials"].default, "algorithm_sha256": algorithm.hexdigest(),
             "trend_space": dict(TREND_SPACE), "idw_space": dict(IDW_SPACE)}
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"config": value, "config_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def recover() -> None:
    """进程重启后不复跑旧执行；已完成结果保留，未完成执行明确失败。"""
    spec()  # 固定当前进程加载的参数及源码版本；更新代码后需重启计算服务。
    root().mkdir(parents=True, exist_ok=True)
    with _LOCK:
        for file in root().glob("*/state.json"):
            try:
                state = json.loads(file.read_text(encoding="utf-8"))
                if directory(state["id"]) != file.parent.resolve():
                    raise ValueError("task directory mismatch")
                if state["state"] == "running":
                    state.update(state="failed", progress="训练已中断",
                                 error="Python 计算服务已重启，本次训练已中断；请重新提交。")
                    _persist(state)
                _STATES[state["id"]] = state
            except (OSError, ValueError, KeyError, DatasetContextError):
                _LOG.error("Cannot recover training record directory=%s", file.parent.name)


def _get(job_id: str) -> dict:
    canonical = str(UUID(job_id))
    state = _STATES.get(canonical)
    if state is None:
        raise DatasetContextError(404, "没有这个训练执行记录。")
    return state


def summary(state: dict) -> dict:
    elapsed = state["elapsed_s"]
    if state["state"] == "running" and state["id"] in _STARTED:
        elapsed = round(time.monotonic() - _STARTED[state["id"]], 1)
    return {key: state[key] for key in ("id", "state", "progress", "error", "created_at")} | {
        "elapsed_s": elapsed, "instance_id": INSTANCE_ID,
        "dataset_id": state["dataset_id"], "config_sha256": state["config_sha256"]}


def status(job_id: str) -> dict:
    with _LOCK:
        return summary(_get(job_id))


def running() -> str | None:
    with _LOCK:
        return next((key for key, state in _STATES.items() if state["state"] == "running"), None)


def submit(job_id: str, config_sha256: str, created_at: str) -> dict:
    job_id = str(UUID(job_id))
    context = current_context()
    if context is None or context.path is None:
        raise DatasetContextError(409, "训练需要明确的已登记数据集。")
    # 在接收执行之前验证数据和切分；失败不会留下可重试的运行记录。
    deps.get_train_dataset()
    with _LOCK:
        old = _STATES.get(job_id)
        if old is not None:
            if (old["dataset_id"] != context.dataset_id or old["config_sha256"] != config_sha256
                    or old["dataset_sha256"] != context.sha256
                    or old["dataset_signature"] != context.signature):
                raise DatasetContextError(409, "相同任务编号不能用于不同训练输入。")
            return summary(old)
        if config_sha256 != spec()["config_sha256"]:
            raise DatasetContextError(409, "训练配置已改变，请重新提交新任务。")
        active = running()
        if active is not None:
            raise DatasetContextError(409, "已有训练执行正在运行。")
        state = {"id": job_id, "dataset_id": context.dataset_id, "state": "running",
                 "progress": "已接收训练任务", "error": None, "created_at": created_at,
                 "elapsed_s": 0.0, "config_sha256": config_sha256,
                 "dataset_signature": context.signature, "dataset_sha256": context.sha256,
                 "file": context.filename, "config": spec()["config"],
                 "instance_id": INSTANCE_ID}
        _persist(state)  # 先持久化接受记录，再启动；同编号重试可找到同一执行。
        _STATES[job_id] = state
        _CANCEL[job_id] = threading.Event()
        _STARTED[job_id] = time.monotonic()
        captured = copy_context()
        _EXECUTOR.submit(captured.run, _run, job_id)
        return summary(state)


def cancel(job_id: str) -> dict:
    with _LOCK:
        state = _get(job_id)
        if state["state"] == "running":
            _CANCEL[state["id"]].set()
            state["progress"] = "已请求取消，等待算法停止"
            _persist(state)
        return summary(state)


def _progress(job_id: str, line: str) -> None:
    with _LOCK:
        state = _get(job_id)
        state["progress"] = str(line)[:4000]
        state["elapsed_s"] = round(time.monotonic() - _STARTED[job_id], 1)
        if time.monotonic() - _LAST_WRITE.get(job_id, 0) >= 1:
            _persist(state)


def _finish(job_id: str, state: str, error: str | None = None) -> None:
    with _LOCK:
        item = _get(job_id)
        item.update(state=state, error=error,
                    elapsed_s=round(time.monotonic() - _STARTED[job_id], 1))
        _persist(item)


def _run(job_id: str) -> None:
    try:
        with _LOCK:
            config = dict(_get(job_id)["config"])
        ds = deps.get_train_dataset()
        bundle = run_calibration(ds, tuple(config["feature_groups"]),
                                 n_trials=config["n_trials"], seed=config["seed"],
                                 idw_space=config["idw_space"], trend_space=config["trend_space"],
                                 root=directory(job_id) / "search",
                                 progress=lambda line: _progress(job_id, line),
                                 should_stop=_CANCEL[job_id].is_set)
        if _CANCEL[job_id].is_set():
            _finish(job_id, "cancelled")
            return
        raw = bundle.to_json().encode("utf-8")
        _atomic(directory(job_id) / "bundle.json", raw)
        with _LOCK:
            _get(job_id)["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
        _finish(job_id, "done")
    except CalibrationAborted:
        _finish(job_id, "cancelled")
    except BaseException as exc:  # 执行线程异常必须成为可查询的终态。
        try:
            _finish(job_id, "failed", f"{type(exc).__name__}: {exc}"[:8000])
        except OSError:
            _LOG.exception("Cannot persist failed training state job_id=%s", job_id)


def _result(job_id: str) -> tuple[dict, CalibrationBundle, bytes]:
    with _LOCK:
        state = dict(_get(job_id))
    context = current_context()
    if context is not None and (state["dataset_id"] != context.dataset_id
                                or state["dataset_sha256"] != context.sha256
                                or state["dataset_signature"] != context.signature):
        raise DatasetContextError(409, "训练结果与当前数据集不一致。")
    if state["state"] != "done":
        raise DatasetContextError(409, "训练结果尚未完成。")
    try:
        raw = (directory(job_id) / "bundle.json").read_bytes()
    except OSError as exc:
        raise DatasetContextError(409, "训练结果文件缺失，请重新训练。") from exc
    if hashlib.sha256(raw).hexdigest() != state.get("bundle_sha256"):
        raise DatasetContextError(409, "训练结果内容与记录不一致，请重新训练。")
    return state, CalibrationBundle.from_json(raw.decode("utf-8")), raw


def result_job(job_id: str):
    state, bundle, _ = _result(job_id)
    return SimpleNamespace(id=job_id, state="done", result=bundle,
                           dataset_id=state["dataset_id"], to_dict=lambda: summary(state))


def result_artifact(job_id: str, bundle) -> bytes | None:
    state, stored, _ = _result(job_id)
    if stored.created_at != bundle.created_at:
        raise DatasetContextError(409, "训练结果版本不一致。")
    digest = state.get("artifact_sha256")
    if digest is None:
        return None
    try:
        raw = (directory(job_id) / "artifact.bin").read_bytes()
    except OSError as exc:
        raise DatasetContextError(409, "训练成品文件缺失，请重新训练。") from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        raise DatasetContextError(409, "训练成品内容与记录不一致。")
    return raw


def export(job_id: str) -> dict:
    with _EXPORT_LOCK:
        state, bundle, raw_bundle = _result(job_id)
        if state["config_sha256"] != spec()["config_sha256"]:
            raise DatasetContextError(409, "训练执行配置与当前计算服务不同，请使用原版本服务保存或重新训练。")
        ds = deps.get_train_dataset()
        if ds.signature != bundle.dataset_sig:
            raise DatasetContextError(409, "保存输入与训练结果不一致。")
        artifact = result_artifact(job_id, bundle)
        if artifact is None:
            artifact = deps.get_pipeline().capture().to_bytes()
            _atomic(directory(job_id) / "artifact.bin", artifact)
            with _LOCK:
                _get(job_id)["artifact_sha256"] = hashlib.sha256(artifact).hexdigest()
                _persist(_get(job_id))
        mae, rmse, r2 = models_store.report_metrics(bundle)
        ts = ds.wide[C.COL_TIMESTAMP]
        return {"job_id": job_id, "dataset_id": state["dataset_id"],
                "dataset_sig": bundle.dataset_sig, "groups_sig": bundle.groups_sig,
                "data_file": state["file"], "data_start": ts.iloc[0].isoformat(),
                "data_end": ts.iloc[-1].isoformat(), "mae": mae, "rmse": rmse, "r2": r2,
                "bundle": raw_bundle.decode("utf-8"),
                "bundle_sha256": hashlib.sha256(raw_bundle).hexdigest(),
                "artifact_base64": base64.b64encode(artifact).decode("ascii"),
                "artifact_sha256": hashlib.sha256(artifact).hexdigest()}
