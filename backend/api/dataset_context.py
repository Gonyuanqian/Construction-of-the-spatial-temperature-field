"""Java 管理的数据集按请求绑定；旧 Python 入口保留原有会话行为。"""
from __future__ import annotations

import base64
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
from uuid import UUID

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import paths


class DatasetContextError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class DatasetContext:
    dataset_id: str
    path: Path | None
    filename: str
    signature: str
    sha256: str


_CONTEXT: ContextVar[DatasetContext | None] = ContextVar("tfield_dataset", default=None)


def current_context() -> DatasetContext | None:
    return _CONTEXT.get()


def storage_root() -> Path:
    configured = os.environ.get("TFIELD_DATASET_STORAGE_ROOT")
    root = Path(configured) if configured else paths.BACKEND / "configs/datasets"
    if not root.is_absolute():
        raise DatasetContextError(503, "数据存储目录必须配置为绝对路径。")
    return root.resolve()


def dataset_file(dataset_id: str) -> Path:
    try:
        canonical = str(UUID(dataset_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DatasetContextError(400, "数据集编号无效。") from exc
    root = storage_root()
    path = (root / canonical / "source.xlsx").resolve()
    if not path.is_relative_to(root):
        raise DatasetContextError(400, "数据集文件位置无效。")
    return path


def internal_key() -> str:
    expected = os.environ.get("TFIELD_INTERNAL_TOKEN")
    if not expected:
        configured = os.environ.get("TFIELD_INTERNAL_TOKEN_FILE")
        token_file = Path(configured) if configured else paths.PROJECT / ".local/service-token"
        try:
            expected = token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise DatasetContextError(503, "内部服务连接尚未完成配置。") from exc
    return expected


def require_internal(headers: Headers) -> None:
    expected = internal_key()
    provided = headers.get("x-tfield-internal-key", "")
    if not expected or not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise DatasetContextError(403, "内部服务凭据无效。")


def verify_file(dataset_id: str, expected_hash: str) -> Path:
    path = dataset_file(dataset_id)
    if not path.is_file():
        raise DatasetContextError(404, "已登记的数据集文件不存在，请重新导入或选择其他数据集。")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise DatasetContextError(400, "数据集内容摘要无效。")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hmac.compare_digest(actual, expected_hash):
        raise DatasetContextError(409, "数据集文件内容与登记版本不一致，请重新导入。")
    return path


def _from_headers(headers: Headers) -> DatasetContext:
    require_internal(headers)
    dataset_id = headers["x-tfield-dataset-id"]
    if dataset_id == "none":
        return DatasetContext("none", None, "", "", "")
    signature = headers.get("x-tfield-dataset-signature", "")
    if not re.fullmatch(r"[0-9a-f]{16}", signature):
        raise DatasetContextError(400, "数据集签名无效。")
    encoded_name = headers.get("x-tfield-dataset-name", "")
    try:
        if len(encoded_name) > 2048:
            raise ValueError("filename header too long")
        filename = base64.b64decode(encoded_name + "=" * (-len(encoded_name) % 4),
                                    altchars=b"-_", validate=True).decode("utf-8")
        if not filename or len(filename) > 255:
            raise ValueError("filename length")
    except (ValueError, UnicodeError) as exc:
        raise DatasetContextError(400, "数据集文件名无效。") from exc
    digest = headers.get("x-tfield-dataset-hash", "")
    path = verify_file(dataset_id, digest)
    return DatasetContext(str(UUID(dataset_id)), path, filename, signature, digest)


class DatasetContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if "x-tfield-dataset-id" not in headers:
            await self.app(scope, receive, send)
            return
        try:
            context = _from_headers(headers)
        except DatasetContextError as exc:
            await JSONResponse({"detail": exc.detail}, status_code=exc.status)(scope, receive, send)
            return
        token = _CONTEXT.set(context)
        try:
            await self.app(scope, receive, send)
        finally:
            _CONTEXT.reset(token)
