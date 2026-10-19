"""计算使用的模型与未保存结果由 Java 在请求开始时明确指定。"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .dataset_context import DatasetContextError, require_internal


@dataclass(frozen=True)
class ModelContext:
    model_id: int | None
    result_job_id: str | None
    request_id: str = ""


_CONTEXT: ContextVar[ModelContext | None] = ContextVar("tfield_model", default=None)


def current_model_context() -> ModelContext | None:
    return _CONTEXT.get()


class ModelContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = Headers(scope=scope) if scope["type"] == "http" else None
        if headers is None or "x-tfield-model-id" not in headers:
            await self.app(scope, receive, send)
            return
        try:
            require_internal(headers)
            raw_model = headers["x-tfield-model-id"]
            model_id = None if raw_model == "none" else int(raw_model)
            if model_id is not None and model_id <= 0:
                raise ValueError("model id")
            raw_result = headers.get("x-tfield-result-id", "none")
            result_id = None if raw_result == "none" else str(UUID(raw_result))
            context = ModelContext(model_id, result_id, headers.get("x-request-id", ""))
        except (ValueError, DatasetContextError) as exc:
            status = exc.status if isinstance(exc, DatasetContextError) else 400
            detail = exc.detail if isinstance(exc, DatasetContextError) else "模型或训练结果编号无效。"
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
            return
        token = _CONTEXT.set(context)
        try:
            await self.app(scope, receive, send)
        finally:
            _CONTEXT.reset(token)
