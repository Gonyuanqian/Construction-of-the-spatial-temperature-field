from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import managed_live
from ..dataset_context import require_internal

router = APIRouter(prefix="/live", include_in_schema=False)


class Preparation(BaseModel):
    model_id: int = Field(gt=0)
    restore_cursor: int = Field(ge=0)
    expected_manifest: dict | None = None


class Operation(BaseModel):
    operation_id: UUID
    action: Literal["start", "pause", "next"]
    from_n: int | None = None


@router.get("/info")
def info(request: Request):
    require_internal(request.headers)
    return {"protocol_version": 1, "instance_id": managed_live.INSTANCE_ID}


@router.get("/sources")
def sources(request: Request):
    require_internal(request.headers)
    return managed_live.source_info()


@router.post("/sessions/{session_id}/prepare")
def prepare(session_id: UUID, body: Preparation, request: Request):
    require_internal(request.headers)
    try:
        return managed_live.prepare(str(session_id), body.model_id, body.restore_cursor, body.expected_manifest)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/sessions/{session_id}")
def status(session_id: UUID, request: Request):
    require_internal(request.headers)
    return managed_live.status(str(session_id))


@router.post("/sessions/{session_id}/operations")
def operation(session_id: UUID, body: Operation, request: Request):
    require_internal(request.headers)
    try:
        return managed_live.operation(str(session_id), str(body.operation_id), body.action, body.from_n)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
