from uuid import UUID
from fastapi import APIRouter, Request
from .. import weather_training, weather_publication
from ..dataset_context import require_internal

router = APIRouter(prefix='/weather-training', include_in_schema=False)

@router.get('/models')
def saved_models(request:Request):
    require_internal(request.headers)
    return weather_training.saved_models()

@router.post('/jobs/{id}/save')
def save_model(id:UUID,body:dict,request:Request):
    require_internal(request.headers)
    return weather_training.save_model(str(id),body)

@router.get('')
def info(request: Request):
    require_internal(request.headers)
    return weather_training.info()

@router.post('/jobs/{id}')
def submit(id: UUID, body: dict, request: Request):
    require_internal(request.headers)
    return weather_training.submit(str(id), body)

@router.get('/jobs/{id}')
def status(id: UUID, request: Request):
    require_internal(request.headers)
    return weather_training.get(str(id))

@router.post('/jobs/{id}/cancel')
def cancel(id: UUID, request: Request):
    require_internal(request.headers)
    return weather_training.cancel(str(id))


@router.post('/jobs/{id}/package')
def package(id: UUID, body: dict, request: Request):
    require_internal(request.headers)
    return weather_publication.package(str(id), body)
