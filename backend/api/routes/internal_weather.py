"""Private Java-to-compute interface. No global workspace/session mutations."""
from fastapi import APIRouter, HTTPException, Request
from .. import weather_views
from ..assistant.ownership import owner_scope
from pydantic import BaseModel, ConfigDict, Field

from tfield import weather_runtime as runtime
from tfield import prototype_runtime
from ..dataset_context import require_internal

router = APIRouter(prefix='/weather', include_in_schema=False)

class PrototypeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    frame_id:str
    reference_id:str=Field(pattern=r'^[a-f0-9]{64}$')
    dimensions:dict
    frames:list[dict]=Field(min_length=1,max_length=1)

@router.get('/prototype')
def prototype_info(request:Request):
    require_internal(request.headers)
    return prototype_runtime.info()

@router.post('/prototype/infer')
def prototype_infer(body:PrototypeRequest,request:Request):
    require_internal(request.headers)
    try:
        runtime.identifier(body.frame_id)
        result=prototype_runtime.infer(body.frames,body.dimensions,body.reference_id)
        runtime.save_result(body.frame_id,result)
        return result['summary']
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise HTTPException(422,str(exc))


class WeatherRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    package_id: str
    package_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    frame_id: str
    frames: list[dict] = Field(min_length=1, max_length=13)


@router.get('/info')
def info(request: Request):
    require_internal(request.headers)
    return {'protocol_version': 1, 'geometry_key': 'ginseng_arch_v1',
            'views_version':1,'input_mode':'external_weather',
            'source': 'virtual_weather_prediction'}


@router.get('/packages/{package_id}')
def package_info(package_id: str, request: Request):
    require_internal(request.headers)
    try:
        return runtime.inspect_package(package_id)
    except FileNotFoundError:
        raise HTTPException(404, '服务器上没有该气象模型包。')
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, '气象模型包校验失败。')


@router.post('/infer')
def inference(body: WeatherRequest, request: Request):
    require_internal(request.headers)
    try:
        runtime.identifier(body.frame_id)
        result = runtime.infer(body.package_id, body.package_sha256, body.frames)
        runtime.save_result(body.frame_id, result)
        return result['summary']
    except FileNotFoundError:
        raise HTTPException(409, '已发布的气象模型包文件缺失。')
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, '模型包或外部气象数据校验失败。')


@router.get('/results/{frame_id}')
def result(frame_id: str, request: Request):
    require_internal(request.headers)
    try:
        return runtime.read_result(frame_id)
    except FileNotFoundError:
        raise HTTPException(404, '温度场结果文件缺失，请联系管理员。')
    except ValueError:
        raise HTTPException(422, '无效结果编号。')


def view(request, call):
    require_internal(request.headers)
    try:
        return call()
    except FileNotFoundError:
        raise HTTPException(404,'温度场结果文件缺失，请联系管理员。')
    except ValueError as exc:
        raise HTTPException(422,str(exc))


@router.get('/results/{frame_id}/sections')
def result_sections(frame_id: str, request: Request, preset: str='standard', monotonic: bool=True):
    return view(request,lambda:weather_views.sections(frame_id,preset=preset,monotonic=monotonic))


@router.get('/results/{frame_id}/volume')
def result_volume(frame_id: str, request: Request, preset: str='standard', monotonic: bool=True,
                  y_step: float=.5, y_min: float=0., y_max: float|None=None):
    return view(request,lambda:weather_views.saved_volume(frame_id,preset=preset,monotonic=monotonic,y_step=y_step,y_min=y_min,y_max=y_max)[1])


@router.get('/results/{frame_id}/point')
def result_point(frame_id: str, request: Request, x: float, y: float, z: float, preset: str='standard', monotonic: bool=True,
                y_step: float=.5, y_min: float=0., y_max: float|None=None, expected_ref: str|None=None):
    return view(request,lambda:weather_views.point(frame_id,x,y,z,preset=preset,monotonic=monotonic,y_step=y_step,y_min=y_min,y_max=y_max,expected_ref=expected_ref))


@router.post('/results/{frame_id}/snapshot')
def result_snapshot(frame_id: str, request: Request, context: dict):
    require_internal(request.headers)
    with owner_scope(request.headers.get('x-tfield-assistant-owner')):
        return view(request,lambda:weather_views.snapshot(frame_id,context))
