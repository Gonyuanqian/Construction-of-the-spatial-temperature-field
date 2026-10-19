"""固定数据、模型和操作编号的实时会话；Java 保存业务记录及确认游标。"""
from __future__ import annotations

from contextlib import nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import threading
import time
from uuid import UUID, uuid4

import pandas as pd
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from tfield import config as C
from tfield.data.loader import dataset_signature

from . import business_client, deps, paths
from .dataset_context import DatasetContextError, require_internal
from .live import LIVE_INTERVAL_S, LiveSource
from .managed_training import _atomic, spec
from .model_context import current_model_context

INSTANCE_ID = str(uuid4())
_CURRENT: ContextVar[str | None] = ContextVar("tfield_live_session", default=None)
_LOCK = threading.RLock()
_LOG = logging.getLogger("uvicorn.error")


@dataclass
class Session:
    metadata: dict
    source: LiveSource | None = None
    gate: threading.RLock = field(default_factory=threading.RLock)
    preparing: bool = False


_SESSIONS: dict[str, Session] = {}


def root() -> Path:
    value = os.environ.get("TFIELD_LIVE_SESSION_ROOT")
    path = Path(value) if value else paths.CONFIGS / "live-sessions"
    if not path.is_absolute():
        raise DatasetContextError(503, "实时会话目录必须是绝对路径。")
    return path.resolve()


def directory(session_id: str) -> Path:
    try:
        canonical = str(UUID(session_id))
    except (ValueError, TypeError) as exc:
        raise DatasetContextError(422, "实时会话编号无效。") from exc
    result = (root() / canonical).resolve()
    if not result.is_relative_to(root()):
        raise DatasetContextError(400, "实时会话位置无效。")
    return result


def _persist(session: Session) -> None:
    _atomic(directory(session.metadata["session_id"]) / "session.json",
            json.dumps(session.metadata, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _get(session_id: str) -> Session:
    session_id = str(UUID(session_id))
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise DatasetContextError(404, "实时会话文件不存在，请重新准备新的会话。")
    return session


def recover() -> None:
    root().mkdir(parents=True, exist_ok=True)
    for file in root().glob("*/session.json"):
        try:
            metadata = json.loads(file.read_text(encoding="utf-8"))
            if directory(metadata["session_id"]) != file.parent.resolve():
                raise ValueError("session directory mismatch")
            metadata.update(running=False, phase="needs_restore")
            session = Session(metadata)
            _persist(session)
            _SESSIONS[metadata["session_id"]] = session
        except (OSError, ValueError, KeyError, DatasetContextError):
            _LOG.error("Cannot recover live session directory=%s", file.parent.name)


def _hash(file: Path) -> str:
    if not file.is_file():
        raise DatasetContextError(409, "实时源文件缺失，请先生成实时数据源。")
    return hashlib.sha256(file.read_bytes()).hexdigest()


def _model(model_id: int) -> dict:
    context = current_model_context()
    if context is None or context.model_id != model_id or context.result_job_id is not None:
        raise DatasetContextError(409, "实时会话需要明确的已保存模型引用。")
    bundle = business_client.fetch(f"/models/{model_id}/bundle", raw=True, missing_ok=True)
    artifact = business_client.fetch(f"/models/{model_id}/artifact", raw=True, missing_ok=True)
    if bundle is None:
        raise DatasetContextError(404, "会话绑定的模型不存在。")
    return {"model_id": model_id, "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
            "artifact_sha256": None if artifact is None else hashlib.sha256(artifact).hexdigest()}


def source_info() -> dict:
    try:
        ds = deps.live_playback_dataset()
        return {"total": len(ds.wide), "interval_s": LIVE_INTERVAL_S, "source_available": True}
    except (FileNotFoundError, ValueError) as exc:
        return {"total": 0, "interval_s": LIVE_INTERVAL_S, "source_available": False,
                "detail": "实时源尚未生成或格式无效，请先生成实时数据源。"}


def _create(session_id: str, model_id: int) -> Session:
    target = directory(session_id)
    target.mkdir(parents=True, exist_ok=True)
    original = {"train": paths.LIVE_TRAIN, "frames": paths.LIVE_FRAMES}
    before = {key: _hash(file) for key, file in original.items()}
    sources = {}
    for key, file in original.items():
        copied = target / (key + ".xlsx")
        shutil.copy2(file, copied)
        if _hash(copied) != before[key] or _hash(file) != before[key]:
            raise DatasetContextError(409, "实时源正在更新，请生成完毕后重新准备。")
        sources[key] = {"sha256": before[key], "signature": dataset_signature(file),
                        "storage_key": session_id + "/" + key + ".xlsx"}
    train = deps.get_dataset(target / "train.xlsx")
    frames = deps.get_dataset(target / "frames.xlsx")
    if len(train.wide) == 0 or len(frames.wide) == 0:
        raise DatasetContextError(409, "实时源的训练段和帧源都不能为空。")
    if pd.Timestamp(frames.wide[C.COL_TIMESTAMP].iloc[0]) <= pd.Timestamp(train.wide[C.COL_TIMESTAMP].iloc[-1]):
        raise DatasetContextError(409, "实时帧必须位于训练段之后。")
    # 复查复制窗口内文件稳定；源文件生成与新会话准备仍应串行进行。
    if any(_hash(file) != before[key] for key, file in original.items()):
        raise DatasetContextError(409, "实时源正在更新，请稍后重新准备。")
    metadata = {"session_id": session_id, **_model(model_id), "sources": sources,
                "algorithm_sha256": spec()["config"]["algorithm_sha256"],
                "cursor": 0, "running": False, "phase": "needs_restore", "total": len(frames.wide),
                "interval_s": LIVE_INTERVAL_S, "operations": {}}
    session = Session(metadata)
    _persist(session)
    return session


def _verify(session: Session, model_id: int) -> None:
    metadata = session.metadata
    if metadata["model_id"] != model_id or metadata["algorithm_sha256"] != spec()["config"]["algorithm_sha256"]:
        raise DatasetContextError(409, "会话的模型或计算版本不一致，请使用匹配版本恢复或重新准备。")
    actual = _model(model_id)
    if any(actual[key] != metadata[key] for key in ("bundle_sha256", "artifact_sha256")):
        raise DatasetContextError(409, "绑定的模型内容已改变，无法按原版本恢复。")
    for key in ("train", "frames"):
        if _hash(directory(metadata["session_id"]) / (key + ".xlsx")) != metadata["sources"][key]["sha256"]:
            raise DatasetContextError(409, "会话的数据副本内容已改变，无法按原版本恢复。")


def status(session_id: str) -> dict:
    session = _get(session_id)
    with _LOCK:
        source = session.source
        ready = source is not None and not session.preparing
        return {"session_id": session_id, "state": "ready" if ready else "idle",
                "cursor": source.cursor() if ready else session.metadata["cursor"],
                "running": bool(source.running) if ready else False,
                "total": session.metadata["total"], "interval_s": LIVE_INTERVAL_S,
                "instance_id": INSTANCE_ID, "recovery_required": not ready,
                "preparing": session.preparing, "manifest": {
                    key: session.metadata[key] for key in ("sources", "model_id", "bundle_sha256",
                                                           "artifact_sha256", "algorithm_sha256")}}


def prepare(session_id: str, model_id: int, restore_cursor: int, expected_manifest: dict | None = None) -> dict:
    started = time.monotonic()
    session_id = str(UUID(session_id))
    # 首次接受快照与同编号重试互斥，慢的管线构建不占全局注册锁。
    with _LOCK:
        session = _SESSIONS.get(session_id)
        if session is None:
            if expected_manifest is not None:
                raise DatasetContextError(409, "原会话记录或数据副本缺失，请重新准备新会话。")
            session = _create(session_id, model_id)
            _SESSIONS[session_id] = session
        if expected_manifest is not None and status(session_id)["manifest"] != expected_manifest:
            raise DatasetContextError(409, "会话的源数据或模型版本与登记记录不一致。")
    with session.gate:
        if session.metadata["model_id"] != model_id:
            raise DatasetContextError(409, "会话绑定的模型编号不一致。")
        if session.source is not None:
            return {"seconds": 0.0, "status": status(session_id)}
        if not 0 <= restore_cursor < session.metadata["total"]:
            raise DatasetContextError(400, "恢复帧号超出实时源范围。")
        with _LOCK:
            session.preparing = True
        try:
            _verify(session, model_id)
            folder = directory(session_id)
            def load(key: str):
                return replace(deps.get_dataset(folder / (key + ".xlsx")),
                               signature=session.metadata["sources"][key]["signature"])
            def build(ds, groups, bundle):
                if bundle is None:
                    raise DatasetContextError(409, "绑定模型与当前特征配置不兼容，请选择可用模型后重新准备。")
                return deps._build_pipeline(ds, groups, bundle)
            source = LiveSource(builder=build, train_loader=lambda: load("train"),
                                frames_loader=lambda: load("frames"))
            source.frames()
            source.prepare()
            source.advance_to(restore_cursor)
            source.cursor_frozen = restore_cursor
            with _LOCK:
                before = copy.deepcopy(session.metadata)
                session.metadata.update(cursor=restore_cursor, running=False, phase="ready")
                try:
                    _persist(session)
                except OSError:
                    session.metadata = before
                    raise
                session.source = source
        finally:
            with _LOCK:
                session.preparing = False
    return {"seconds": max(0.0, time.monotonic() - started), "status": status(session_id)}


def operation(session_id: str, operation_id: str, action: str, from_n: int | None) -> dict:
    session = _get(session_id)
    operation_id = str(UUID(operation_id))
    with session.gate:
        with _LOCK:
            old = session.metadata["operations"].get(operation_id)
        if old is not None:
            if old["action"] != action or old["from_n"] != from_n:
                raise DatasetContextError(409, "相同操作编号不能用于另一项实时操作。")
            return {"operation_id": operation_id, "result": old["result"], "current": status(session_id)}
        source = session.source
        if source is None:
            raise DatasetContextError(409, "实时管线需要恢复，请先准备实时源。")
        with _LOCK:
            previous = (source.started_at, source.running, source.cursor_frozen)
            metadata = copy.deepcopy(session.metadata)
            try:
                if action == "start":
                    source.start(from_n)
                elif action == "pause":
                    source.pause()
                elif action == "next":
                    source.next_frame()
                else:
                    raise DatasetContextError(422, "未知实时操作。")
                result = status(session_id)
                session.metadata.update(cursor=result["cursor"], running=result["running"])
                session.metadata["operations"][operation_id] = {
                    "action": action, "from_n": from_n, "result": {key: result[key]
                        for key in ("cursor", "running", "total", "interval_s")}}
                _persist(session)  # 游标和回执一同落盘，提交失败时回退时钟状态。
            except BaseException:
                source.started_at, source.running, source.cursor_frozen = previous
                session.metadata = metadata
                raise
        return {"operation_id": operation_id,
                "result": session.metadata["operations"][operation_id]["result"], "current": result}


def current_source() -> LiveSource | None:
    session_id = _CURRENT.get()
    if session_id is None:
        return None
    source = _get(session_id).source
    if source is None:
        raise DatasetContextError(409, "实时管线需要恢复，请先准备实时源。")
    return source


def frame_guard():
    session_id = _CURRENT.get()
    return nullcontext() if session_id is None else _get(session_id).gate


class LiveContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        headers = Headers(scope=scope) if scope["type"] == "http" else None
        if headers is None or "x-tfield-live-session-id" not in headers:
            await self.app(scope, receive, send)
            return
        try:
            require_internal(headers)
            session_id = str(UUID(headers["x-tfield-live-session-id"]))
            model = current_model_context()
            session = _get(session_id)
            if model is None or model.model_id != session.metadata["model_id"] or model.result_job_id is not None:
                raise DatasetContextError(409, "实时计算的模型引用与会话绑定不一致。")
        except (ValueError, DatasetContextError) as exc:
            status_code = exc.status if isinstance(exc, DatasetContextError) else 400
            detail = exc.detail if isinstance(exc, DatasetContextError) else "实时会话编号无效。"
            await JSONResponse({"detail": detail}, status_code=status_code)(scope, receive, send)
            return
        token = _CURRENT.set(session_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _CURRENT.reset(token)
