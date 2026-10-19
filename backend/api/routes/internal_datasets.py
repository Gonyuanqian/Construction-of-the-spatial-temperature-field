"""数据集登记的内部协议；验证与接管不修改当前数据集或提交训练。"""
from __future__ import annotations

import hashlib
import shutil
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from tfield.data.loader import dataset_signature

from .. import deps, jobs, uploads, managed_training
from ..dataset_context import DatasetContextError, dataset_file, require_internal, verify_file

router = APIRouter(prefix="/datasets", include_in_schema=False)


class DatasetInput(BaseModel):
    dataset_id: UUID
    filename: str = Field(min_length=1, max_length=1024)


class DatasetReference(BaseModel):
    dataset_id: UUID
    sha256: str


class AdoptionInput(BaseModel):
    dataset_id: UUID


def _manifest(dataset_id: str, name: str, legacy_signature: str | None = None) -> dict:
    path = dataset_file(dataset_id)
    if not path.is_file():
        raise DatasetContextError(404, "待校验的数据集文件不存在。")
    reject = uploads.precheck(name, path.stat().st_size)
    if reject is not None:
        raise DatasetContextError(reject.status, reject.detail)
    filename = uploads.safe_name(name)
    if len(filename) > 255:
        raise DatasetContextError(422, "文件名最多 255 个字符。")
    try:
        info = uploads.validate_existing(path)
    except uploads.Rejected as exc:
        raise DatasetContextError(exc.status, exc.detail) from exc
    return {
        "dataset_id": dataset_id, "file": filename,
        "storage_key": dataset_id + "/source.xlsx",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "legacy_signature": legacy_signature or dataset_signature(path),
        "size_bytes": path.stat().st_size,
        "n_times": info.n_times, "n_columns": info.n_columns,
        "time_start": info.time_start, "time_end": info.time_end,
    }


@router.post("/validate")
def validate(body: DatasetInput, request: Request) -> dict:
    require_internal(request.headers)
    return _manifest(str(body.dataset_id), body.filename)


@router.post("/check")
def check(body: DatasetReference, request: Request) -> dict:
    require_internal(request.headers)
    verify_file(str(body.dataset_id), body.sha256)
    return {"dataset_id": str(body.dataset_id), "available": True}


@router.get("/activity")
def activity(request: Request) -> dict:
    require_internal(request.headers)
    job = jobs.current()
    return {"training_running": (job is not None and job.state == jobs.RUNNING)
            or managed_training.running() is not None}


@router.post("/adopt-current")
def adopt_current(body: AdoptionInput, request: Request) -> dict:
    require_internal(request.headers)
    source = deps.current_dataset_path()
    signature = dataset_signature(source)
    target = dataset_file(str(body.dataset_id))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
            raise DatasetContextError(409, "数据集编号已经对应另一份文件。")
    else:
        shutil.copy2(source, target)
    return _manifest(str(body.dataset_id), deps.current_dataset_name(), signature)
