"""Gateway-selected user namespace, retained by request and background work."""
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID
from fastapi import Request
from ..dataset_context import DatasetContextError, require_internal

OWNER=ContextVar('assistant_owner',default=None)

@contextmanager
def owner_scope(value):
    if value is not None:
        try:
            if str(UUID(value))!=value: raise ValueError()
        except (ValueError,TypeError,AttributeError):
            raise DatasetContextError(422,'助手用户编号无效。')
    token=OWNER.set(value)
    try: yield
    finally: OWNER.reset(token)

async def request_scope(request: Request):
    require_internal(request.headers)
    with owner_scope(request.headers.get('x-tfield-assistant-owner')):
        yield
