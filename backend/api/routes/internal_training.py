"""Java 管理训练的内部协议，提交编号由 Java 生成。"""
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import managed_training, business_client
from ..dataset_context import require_internal

router = APIRouter(prefix="/training", include_in_schema=False)


class Submission(BaseModel):
    config_sha256: str
    created_at: str


@router.get("/info")
def info(request: Request):
    require_internal(request.headers)
    return {"instance_id": managed_training.INSTANCE_ID, "protocol_version": 1,
            "model_store_mode": "java" if business_client.java_store() else "legacy",
            **managed_training.spec()}


@router.post("/jobs/{job_id}")
def submit(job_id: UUID, body: Submission, request: Request):
    require_internal(request.headers)
    return managed_training.submit(str(job_id), body.config_sha256, body.created_at)


@router.get("/jobs/{job_id}")
def status(job_id: UUID, request: Request):
    require_internal(request.headers)
    return managed_training.status(str(job_id))


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: UUID, request: Request):
    require_internal(request.headers)
    return managed_training.cancel(str(job_id))


@router.post("/jobs/{job_id}/export")
def export(job_id: UUID, request: Request):
    require_internal(request.headers)
    return managed_training.export(str(job_id))
