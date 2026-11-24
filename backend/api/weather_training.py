"""Persistent compute records and immutable G artifacts, reached through Java."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import pickle
import threading
import time
from uuid import UUID, uuid4

from tfield.data.loader import load_dataset
from tfield.weather_training import describe, options, train
from . import paths
from .dataset_context import DatasetContextError, current_context, verify_file

LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='weather-G')
STATES, CANCEL, STARTED = {}, {}, {}


def root():
    path = Path(os.environ.get('TFIELD_WEATHER_TRAINING_ROOT', paths.CONFIGS / 'weather-training'))
    if not path.is_absolute():
        raise DatasetContextError(503, 'G 训练数据目录必须是绝对路径。')
    return path.resolve()


def folder(id):
    try:
        if str(UUID(id)) != id: raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise DatasetContextError(422, 'G 任务编号无效。')
    path = root() / id
    if path.is_symlink() or path.resolve().parent != root():
        raise DatasetContextError(422, 'G 任务目录无效。')
    return path


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.part')
    try:
        with temp.open('xb') as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def persist(state):
    atomic(folder(state['id']) / 'state.json', json.dumps(state, ensure_ascii=False, allow_nan=False).encode('utf-8'))


def recover():
    root().mkdir(parents=True, exist_ok=True)
    with LOCK:
        STATES.clear(); CANCEL.clear(); STARTED.clear()
        for path in root().glob('*/state.json'):
            state = json.loads(path.read_text('utf-8'))
            if path.parent.resolve() != folder(state['id']).resolve():
                raise RuntimeError('G 训练记录目录不一致。')
            if state['state'] == 'running':
                state.update(state='failed', error='计算服务重启，训练已中断；已有成品保留，请重新提交。', progress='训练已中断')
                persist(state)
            STATES[state['id']] = state


def public(state):
    out = copy.deepcopy(state)
    if state['state'] == 'running': out['elapsed_s'] = round(time.monotonic() - STARTED.get(state['id'], time.monotonic()), 1)
    out.pop('dataset_sha256', None)
    return out


def active():
    with LOCK:
        return any(s['state'] == 'running' for s in STATES.values())


def context():
    ctx = current_context()
    if ctx is None or ctx.path is None:
        raise DatasetContextError(409, '请先导入或选择训练数据集。')
    return ctx


def info():
    ctx = context()
    description = describe(load_dataset(ctx.path))
    with LOCK:
        records = sorted((s for s in STATES.values() if s['dataset_id'] == ctx.dataset_id), key=lambda s: s['created_at'], reverse=True)[:20]
        running = next((public(s) for s in STATES.values() if s['state'] == 'running'), None)
        return dict(protocol_version=1, dataset_id=ctx.dataset_id, filename=ctx.filename,
                    dataset=description, jobs=[public(s) for s in records], active_job=running)


def get(id):
    folder(id)
    with LOCK:
        if id not in STATES: raise DatasetContextError(404, '没有这个 G 训练记录。')
        return public(STATES[id])


def submit(id, body):
    folder(id)
    ctx = context()
    try: cfg = options(body)
    except ValueError as exc: raise DatasetContextError(422, str(exc))
    with LOCK:
        if id in STATES:
            old = STATES[id]
            if options(old['options']) != cfg or old['dataset_id'] != ctx.dataset_id or old['dataset_sha256'] != ctx.sha256:
                raise DatasetContextError(409, '同一操作编号不能提交不同的 G 训练配置。')
            return public(old)
        if active(): raise DatasetContextError(409, '已有训练任务正在执行，请等待或取消。')
        description = describe(load_dataset(ctx.path))
        if not description['ready']: raise DatasetContextError(422, description['reason'])
        state = dict(id=id, state='running', name=cfg['name'], options=cfg, dataset_id=ctx.dataset_id,
            dataset_sha256=ctx.sha256, filename=ctx.filename, created_at=datetime.now(timezone.utc).isoformat(),
            elapsed_s=0., progress='已提交训练', error=None, cancel_requested=False, result=None, artifacts=None)
        persist(state)
        STATES[id] = state; CANCEL[id] = threading.Event(); STARTED[id] = time.monotonic()
        POOL.submit(work, id, ctx)
        return public(state)


class Cancelled(Exception): pass


def work(id, ctx):
    def checkpoint(message):
        with LOCK:
            if CANCEL[id].is_set(): raise Cancelled()
            STATES[id].update(progress=message, elapsed_s=round(time.monotonic()-STARTED[id], 1))
            persist(STATES[id])
    try:
        checkpoint('正在校验训练数据快照')
        path = verify_file(ctx.dataset_id, ctx.sha256)
        result, models = train(load_dataset(path), STATES[id]['options'], checkpoint)
        artifacts = {}
        for key, model in models.items():
            checkpoint('正在归档训练成品')
            raw = pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL)
            atomic(folder(id) / f'{key}.pkl', raw)
            artifacts[key] = hashlib.sha256(raw).hexdigest()
        with LOCK:
            if CANCEL[id].is_set(): raise Cancelled()
            STATES[id].update(state='done', progress='训练完成，成品已归档', result=result,
                artifacts=artifacts, elapsed_s=round(time.monotonic()-STARTED[id], 1))
            persist(STATES[id])
    except Exception as exc:
        with LOCK:
            STATES[id].update(state='cancelled' if isinstance(exc, Cancelled) else 'failed',
                progress='训练已取消' if isinstance(exc, Cancelled) else '训练失败',
                error=None if isinstance(exc, Cancelled) else str(exc), elapsed_s=round(time.monotonic()-STARTED[id], 1))
            persist(STATES[id])


def cancel(id):
    get(id)
    with LOCK:
        if STATES[id]['state'] == 'running':
            CANCEL[id].set(); STATES[id].update(cancel_requested=True, progress='正在取消，等待当前拟合结束…'); persist(STATES[id])
        return public(STATES[id])


def saved_models():
    with LOCK:
        return [copy.deepcopy(s['saved_model']) for s in sorted(STATES.values(),key=lambda s:s['created_at'],reverse=True) if s.get('saved_model')]


def save_model(id,body):
    if not isinstance(body,dict) or set(body)!={'name'} or not isinstance(body['name'],str) or not 1<=len(body['name'].strip())<=120:
        raise DatasetContextError(422,'模型名称需为 1 至 120 个字符。')
    get(id);name=body['name'].strip()
    with LOCK:
        state=STATES[id]
        if state['state']!='done' or not state.get('options',{}).get('workbench') or not state.get('artifacts'):
            raise DatasetContextError(409,'请先完成当前工作台模型的训练。')
        if state.get('saved_model'):
            if state['saved_model']['name']!=name:raise DatasetContextError(409,'此训练成品已经保存，请使用原名称查看记录。')
            return copy.deepcopy(state['saved_model'])
        for key,digest in state['artifacts'].items():
            if key not in ('field','current'):raise DatasetContextError(409,'训练成品类型不匹配。')
            path=folder(id)/f'{key}.pkl'
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise DatasetContextError(409,'训练成品缺失或摘要校验失败，请重新训练。')
        w=state['options']['workbench']
        saved=dict(id=id,name=name,target=w['target'],algorithm=w['algorithm'],interpolation=w['interpolation'] if w['target']=='field' else None,
            prediction_target=w.get('prediction_target','absolute') if w['target']=='mapping' else None,
            dataset_id=state['dataset_id'],filename=state['filename'],saved_at=datetime.now(timezone.utc).isoformat(),
            params=copy.deepcopy(state['result']['selected_params']),test=copy.deepcopy(state['result']['test']),artifacts=copy.deepcopy(state['artifacts']))
        state['saved_model']=saved
        try:persist(state)
        except Exception:
            state.pop('saved_model',None);raise
        return copy.deepcopy(saved)
