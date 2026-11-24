from __future__ import annotations

import asyncio
import os
import time
from contextvars import copy_context
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from ..assistant import config, field_tools, knowledge, routing, runtime, store, web_research, design_inspection
from ..assistant.ownership import request_scope
from ..assistant import control_plans
from ..assistant.ownership import OWNER
from ..dataset_context import DatasetContextError, require_internal
from .. import live, managed_live
from .live import _get_frame, _get_volume
from tfield import config as C

router = APIRouter(prefix='/assistant', include_in_schema=False,dependencies=[Depends(request_scope)])
STREAM_SECONDS = 25

@router.get('/info')
def info():
    return {'owner_isolation_version':1,'design_inspection_version':1,'design_inspection_policy':'advisory-v2','design_citation_limit':64,'inspection_history_policy':'followup_only','control_plan_version':1}


@router.post('/control-plans')
def control_plan(body: control_plans.Request, request: Request):
    require_internal(request.headers)
    if not OWNER.get():
        raise DatasetContextError(422, '控制计划需要用户上下文。')
    if not config.api_key():
        raise DatasetContextError(503, 'AgriSeek 尚未配置。')
    if not control_plans.SLOTS.acquire(blocking=False):
        raise DatasetContextError(429, '控制计划服务繁忙。')
    try:
        return control_plans.generate(body)
    except Exception as exc:
        raise DatasetContextError(502, '控制计划暂未生成，请稍后重试；未创建执行任务。') from exc
    finally:
        control_plans.SLOTS.release()

@router.post('/design-snapshots')
def design_snapshot(body:design_inspection.DesignSnapshotRequest,request:Request):
    require_internal(request.headers)
    try:return design_inspection.snapshot(body)
    except ValueError as exc:raise DatasetContextError(422,str(exc)) from exc


class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    frame_index: int | None = Field(default=None, ge=0)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    snapshot_id: UUID | None = None
    request_key: UUID
    conversation_id: UUID | None = None
    parent_run_id: UUID | None = None
    legacy_run_ids: list[UUID] = Field(default_factory=list, max_length=20)
    question: str = Field(min_length=1, max_length=2000)
    crop: str | None = Field(default=None, max_length=80)
    stage: str | None = Field(default=None, max_length=80)
    web_search_enabled: bool = True
    thinking_enabled: bool = True
    position: field_tools.Position | None = None
    region: field_tools.Region | None = None
    regions: field_tools.RegionPair | None = None


@router.get('/capabilities')
def capabilities(request: Request):
    require_internal(request.headers)
    return {'model_configured': bool(config.api_key()),
            'model': os.getenv('TFIELD_ASSISTANT_MODEL', 'deepseek-flash'),
            'knowledge_configured': bool(knowledge.configured()),
            'web_search_configured': web_research.configured(),
            'native_thinking_enabled': os.getenv('TFIELD_ASSISTANT_THINKING_ENABLED','true').lower()!='false',
            'min_cycles': 1, 'min_reviews': 2, 'max_cycles': 6, 'data_mode': 'replay',
            'tools': ['read_snapshot', 'get_temperature_point', 'find_temperature_extrema',
                      'get_region_statistics', 'compare_regions', 'search_agri_knowledge',
                      *(['search_web', 'read_web_source'] if web_research.configured() else [])],
            'limitations': ['点温与区域统计使用固定快照的有效重建网格；极值不是棚体真实连续场极值。',
                            '本地资料不足时可联网补充原文，经引用与适用条件复核后使用；不自动写入知识库。',
                            '未提供历史、未来预测或设备控制；外部文献不能替代本棚现场读数。']}


@router.post('/snapshots')
def capture(body: SnapshotRequest, request: Request):
    require_internal(request.headers)
    session_id = request.headers.get('x-tfield-live-session-id')
    if not session_id:
        raise DatasetContextError(409, '请通过业务入口绑定实时会话。')
    with live.guard():
        source = live.get_live_source()
        n = source.cursor() if body.frame_index is None else body.frame_index
        frame = _get_frame(n, preset='standard', monotonic=True)
        volume = _get_volume(n, preset='standard', monotonic=True, y_step=.5, y_min=0., y_max=18.)
        if frame['frame']['time'] != volume['frame']['time']:
            raise DatasetContextError(409, '快照的断面与三维时刻不一致，请重新绑定。')
        volume['geometry'] = {'radius': float(C.ARCH_R), 'center_x': float(C.ARCH_XC), 'offset_z': float(C.ARCH_K)}
        status = managed_live.status(session_id)
        captured = store.snapshot({'session_id': session_id, 'frame_index': n,
            'source_time': frame['frame']['time'], 'source_timezone': 'Asia/Shanghai',
            'model_id': status['manifest']['model_id'], 'manifest': status.get('manifest'),
            'calculation_profile': {'preset': 'standard', 'monotonic': True, 'y_step': .5, 'y_min': 0., 'y_max': 18.},
            'volume': volume,
            'field_domain': ({'x_min':volume['x'][0],'x_max':volume['x'][-1],
                              'y_min':volume['planes'][0]['y'],'y_max':volume['planes'][-1]['y'],
                              'z_min':volume['z'][0],'z_max':volume['z'][-1],
                              'max_measured_z':volume['max_measured_z']} if volume.get('x') else {}),
            'facts': runtime.facts_from_frame(frame)})
        return field_tools.public_snapshot(captured)


@router.get('/snapshots/{identifier}')
def snapshot_info(identifier: UUID, request: Request):
    require_internal(request.headers)
    return field_tools.public_snapshot(store.get_snapshot(str(identifier)))


@router.get('/snapshots/{identifier}/volume')
def snapshot_volume(identifier: UUID, request: Request):
    require_internal(request.headers)
    return field_tools.volume_of(store.get_snapshot(str(identifier)))


@router.get('/snapshots/{identifier}/point')
def snapshot_point(identifier: UUID, x: float, y: float, z: float, request: Request):
    require_internal(request.headers)
    try:
        return field_tools.point(store.get_snapshot(str(identifier)), {'x':x,'y':y,'z':z})
    except ValueError as exc:
        raise DatasetContextError(422, str(exc)) from exc


@router.post('/runs')
def submit(body: RunRequest, request: Request):
    require_internal(request.headers)
    if not body.question.strip():
        raise DatasetContextError(422, '请输入问题。')
    if body.parent_run_id and not body.conversation_id:
        raise DatasetContextError(422, '追问需要指定所属会话。')
    if body.snapshot_id:
        store.get_snapshot(str(body.snapshot_id))
    if sum(value is not None for value in (body.position,body.region,body.regions))>1:
        raise DatasetContextError(422,'位置、单区域和双区域请选择一种。')
    preliminary = routing.plan(body.question,body.position.model_dump() if body.position else None,
                               body.region.model_dump() if body.region else None,
                               body.regions.model_dump() if body.regions else None)
    if not config.api_key() and preliminary['mode'] not in ('unsupported','clarification'):
        raise DatasetContextError(503, 'DeepSeek 尚未配置，请在服务端设置 DEEPSEEK_API_KEY。')
    if not runtime.SLOTS.acquire(blocking=False):
        raise DatasetContextError(429, '助手当前任务较多，请稍后重试。')
    try:
        args = body.model_dump(mode='json', exclude={'request_key'}, exclude_unset=True)
        args['conversation_id'] = str(body.conversation_id or uuid5(NAMESPACE_URL, 'agriseek:'+str(body.request_key)))
        value, created = store.create_run(str(body.request_key), args)
        if created:
            runtime.POOL.submit(copy_context().run, runtime.work, value)
        else:
            runtime.SLOTS.release()
        return store.public_run(value)
    except BaseException:
        runtime.SLOTS.release()
        raise


@router.get('/runs/{identifier}')
def get_run(identifier: UUID, request: Request):
    require_internal(request.headers)
    return store.public_run(store.get_run(str(identifier)))


@router.post('/runs/{identifier}/cancel')
def cancel(identifier: UUID, request: Request):
    require_internal(request.headers)
    value = store.cancel(str(identifier))
    runtime.cancel_inflight(str(identifier))
    return store.public_run(value)


@router.get('/conversations')
def conversations(request: Request):
    require_internal(request.headers)
    return store.list_conversations()


@router.get('/conversations/{identifier}')
def conversation(identifier: UUID, request: Request):
    require_internal(request.headers)
    return store.get_conversation(str(identifier))


class ConversationRename(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1,max_length=80)


@router.post('/conversations/{identifier}/rename')
def rename_conversation(identifier: UUID, body: ConversationRename, request: Request):
    require_internal(request.headers)
    return store.rename_conversation(str(identifier),body.title)


@router.post('/conversations/{identifier}/delete')
def delete_conversation(identifier: UUID, request: Request):
    require_internal(request.headers)
    return store.delete_conversation(str(identifier))


@router.get('/conversations/{identifier}/events')
def conversation_events(identifier: UUID, request: Request, after: int = Query(0, ge=0),
                        limit: int = Query(100, ge=1, le=200)):
    require_internal(request.headers)
    return store.conversation_events(str(identifier), after, limit)


@router.get('/conversations/{identifier}/stream')
def conversation_stream(identifier: UUID, request: Request, after: int = Query(0, ge=0)):
    require_internal(request.headers)
    chat = str(identifier)
    initial = store.conversation_events(chat, after, 100)  # Reject bad cursors before HTTP 200.

    async def stream():
        cursor, batch = after, initial
        deadline, heartbeat = time.monotonic() + STREAM_SECONDS, time.monotonic()
        yield 'event: ready\ndata: {"protocol_version":1}\n\n'
        while time.monotonic() < deadline and not await request.is_disconnected():
            for event in batch['events']:
                cursor = event['seq']
                yield f'id: {cursor}\nevent: session\ndata: {store.packed(event)}\n\n'
            if time.monotonic() - heartbeat >= 5:
                yield ': heartbeat\n\n'
                heartbeat = time.monotonic()
            if cursor >= batch['cursor']:
                await asyncio.sleep(.25)
            batch = await run_in_threadpool(store.conversation_events, chat, cursor, 100)

    return StreamingResponse(stream(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})
