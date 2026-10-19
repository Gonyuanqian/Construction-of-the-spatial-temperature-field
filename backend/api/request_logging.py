"""Java 与 Python 共用请求编号，保持响应体与计算语义不变。"""
from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_VALID_ID = re.compile(r"[a-zA-Z0-9._-]{1,64}\Z")
_LOG = logging.getLogger("uvicorn.error")


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next((v.decode("latin-1") for k, v in scope.get("headers", [])
                         if k.lower() == b"x-request-id"), "")
        request_id = incoming if _VALID_ID.fullmatch(incoming) else uuid.uuid4().hex
        started = time.perf_counter()
        status = 500

        async def traced_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() != b"x-request-id"]
                message = {**message, "headers": [*headers,
                           (b"x-request-id", request_id.encode("ascii"))]}
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        finally:
            _LOG.info("request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f",
                      request_id, scope.get("method", ""), scope.get("path", ""),
                      status, (time.perf_counter() - started) * 1000)
