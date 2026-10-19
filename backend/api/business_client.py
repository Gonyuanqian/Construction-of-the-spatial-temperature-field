"""Python 仅向 Java 读取模型记录与原始产物，不直接写业务数据库。"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .dataset_context import DatasetContextError, internal_key
from .model_context import current_model_context


def java_store() -> bool:
    return os.environ.get("TFIELD_MODEL_STORE_MODE", "java").lower() != "legacy"


def fetch(path: str, *, raw: bool = False, missing_ok: bool = False):
    base = os.environ.get("TFIELD_BUSINESS_URL", "http://127.0.0.1:8080").rstrip("/")
    headers = {"X-TField-Internal-Key": internal_key()}
    context = current_model_context()
    if context is not None and context.request_id:
        headers["X-Request-ID"] = context.request_id
    try:
        with urlopen(Request(base + "/internal/v1/model-store" + path, headers=headers),
                     timeout=30) as response:
            body = response.read()
            if response.status == 204:
                return None
            return body if raw else json.loads(body)
    except HTTPError as exc:
        if exc.code == 404 and missing_ok:
            return None
        exc.read()
        raise DatasetContextError(503, "模型登记服务暂不可用，请稍后重试。") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise DatasetContextError(503, "模型登记服务暂不可用，请稍后重试。") from exc
