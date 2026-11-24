from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4

from .. import paths
from ..dataset_context import DatasetContextError
from . import analysis
from .ownership import OWNER

INSTANCE = str(uuid4())


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


@contextmanager
def connect():
    configured=os.getenv('TFIELD_ASSISTANT_STATE_ROOT')
    root=Path(configured) if configured else paths.PROJECT / '.local' / 'assistant'
    if not root.is_absolute(): raise ValueError('TFIELD_ASSISTANT_STATE_ROOT must be absolute')
    if OWNER.get() is not None: root=root/'users'/OWNER.get()
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'runs.sqlite3', timeout=5)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, request_key TEXT UNIQUE, '
               'fingerprint TEXT, instance TEXT, body TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, head TEXT, title TEXT NOT NULL, '
               'created_at REAL NOT NULL, updated_at REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS deleted_conversations (id TEXT PRIMARY KEY, deleted_at REAL NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS assistant_events (conversation_id TEXT NOT NULL, seq INTEGER NOT NULL, '
               'turn_id TEXT NOT NULL, step_id TEXT, type TEXT NOT NULL, time REAL NOT NULL, data TEXT NOT NULL, '
               'PRIMARY KEY(conversation_id,seq))')
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def snapshot(body, identifier=None):
    # All facts are materialized now; later model calls never reread the live pipeline.
    value = json.loads(packed(body))
    value['snapshot_id'] = identifier or str(uuid4())
    value['data_mode'] = body.get('data_mode','replay')
    value['captured_at'] = time.time()
    value['content_sha256'] = hashlib.sha256(packed(body).encode()).hexdigest()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT body FROM snapshots WHERE id=?',(value['snapshot_id'],)).fetchone()
        if existing:
            old=json.loads(existing[0])
            if old.get('content_sha256')!=value['content_sha256']:raise DatasetContextError(409,'相同设计检验编号不能绑定其他方案内容。')
            return old
        db.execute('INSERT INTO snapshots VALUES (?,?)', (value['snapshot_id'], packed(value)))
    return value


def get_snapshot(identifier):
    with connect() as db:
        row = db.execute('SELECT body FROM snapshots WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise DatasetContextError(404, '分析快照不存在，请重新绑定当前帧。')
    return json.loads(row[0])


PUBLIC_FIELDS = ('id', 'conversation_id', 'parent_run_id', 'question', 'status', 'cycle', 'events', 'result',
                 'conversation_origin',
                 'analysis', 'detail', 'error_code', 'created_at', 'cancelled', 'snapshot_id', 'crop', 'stage',
                 'position', 'region', 'regions', 'resolved_context', 'model_calls', 'tool_calls', 'tokens',
                 'evaluations', 'history_turns_in_model', 'event_seq', 'diagnostic',
                 'web_search_enabled', 'web_search_calls', 'web_read_calls', 'protocol_repairs', 'answer_plan',
                 'thinking_enabled', 'thinking', 'answer_stream')


def public_run(value):
    """Only published claims and execution metadata cross the business boundary."""
    out = {k: value[k] for k in PUBLIC_FIELDS if k in value}
    out = json.loads(packed(out))
    if out.get('diagnostic'):
        out['diagnostic'] = {k: v for k, v in out['diagnostic'].items()
                             if k in ('category', 'phase', 'exception_type', 'http_status', 'finish_reason',
                                      'tool_call_count', 'content_kind', 'content_chars', 'model_call', 'protocol_repairs', 'answer_plan')}
    if out.get('result') and out['result'].get('snapshot'):
        out['result']['snapshot'].pop('manifest', None)
    return out


def _append(db, value, kind, data, step_id=None):
    conversation_id = value.get('conversation_id') or 'run:' + value['id']
    seq = db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM assistant_events WHERE conversation_id=?',
                     (conversation_id,)).fetchone()[0]
    if kind in ('turn/start', 'turn/checkpoint', 'turn/end'):
        value['event_seq'] = seq
        data = {'run': public_run(value)}
    event = {'seq': seq, 'type': kind, 'time': time.time(), 'turn_id': value['id'],
             'step_id': step_id, 'data': data}
    db.execute('INSERT INTO assistant_events VALUES (?,?,?,?,?,?,?)',
               (conversation_id, seq, value['id'], step_id, kind, event['time'], packed(data)))
    return event


def emit_activity(identifier, activity_id, kind, status, label, **metrics):
    """No free-form provider/tool payloads: the public event schema is an allowlist."""
    if kind not in ('model', 'tool') or status not in ('running', 'completed', 'failed'):
        raise ValueError('invalid activity')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT body FROM runs WHERE id=?', (identifier,)).fetchone()
        value = json.loads(row[0])
        if value['status'] in analysis.TERMINAL or value.get('cancelled'):
            return
        data = {'id': activity_id, 'kind': kind, 'status': status, 'label': label[:100]}
        data.update({k: v for k, v in metrics.items() if k in ('received_chars', 'tool_count', 'evidence_count')
                     and isinstance(v, int) and 0 <= v <= 1000000})
        _append(db, value, 'activity/update', data, f"{identifier}:step:{value.get('cycle', 0)}")


def stream_answer(identifier, generation, text):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        value=_read_run(db,identifier)
        if value['status'] in analysis.TERMINAL or value.get('cancelled'):return
        previous=value.get('answer_stream',{})
        if generation<previous.get('generation',0):return
        current={'generation':generation,'text':text[:20000]}
        if current==previous:return
        value['answer_stream']=current
        event=_append(db,value,'answer/update',current)
        value['event_seq']=event['seq']
        db.execute('UPDATE runs SET body=? WHERE id=?',(packed(value),identifier))


def create_run(key, request):
    fingerprint = hashlib.sha256(packed(request).encode()).hexdigest()
    value = dict(id=str(uuid4()), status='queued', cycle=0, events=[], result=None,
                 created_at=time.time(), cancelled=False, analysis=analysis.new(), **request)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if request.get('conversation_id'):
            _ensure_visible(db, request['conversation_id'])
        existing = db.execute('SELECT fingerprint,body FROM runs WHERE request_key=?', (key,)).fetchone()
        if existing:
            if existing[0] != fingerprint:
                raise DatasetContextError(409, '相同请求编号不能用于另一条问题或快照。')
            return json.loads(existing[1]), False
        conversation_id = request.get('conversation_id')
        parent_id = request.get('parent_run_id')
        if _inspection_only(db,value):
            value['conversation_origin']='greenhouse_design_inspection'
        if parent_id and not conversation_id:
            raise DatasetContextError(422, '追问需要指定所属会话。')
        if conversation_id:
            chat = db.execute('SELECT head FROM conversations WHERE id=?', (conversation_id,)).fetchone()
            legacy = request.get('legacy_run_ids') or []
            legacy_title = None
            if legacy:
                if chat or len(legacy) > 20 or len(set(legacy)) != len(legacy) or legacy[-1] != parent_id:
                    raise DatasetContextError(409, '旧会话记录关联不一致，请刷新后重试。')
                previous_id, previous_time = None, -1
                for legacy_id in legacy:
                    old_row = db.execute('SELECT instance,body FROM runs WHERE id=?', (legacy_id,)).fetchone()
                    if not old_row:
                        raise DatasetContextError(404, '旧会话中的问答记录不存在。')
                    old = json.loads(old_row[1])
                    if legacy_title is None: legacy_title = old['question']
                    if old.get('conversation_id') is not None or old['created_at'] < previous_time:
                        raise DatasetContextError(409, '旧记录已属于其他会话或顺序不一致。')
                    if old['status'] in ('queued', 'running') and old_row[0] == INSTANCE:
                        raise DatasetContextError(409, '旧会话仍有进行中的任务，请先完成或取消。')
                    old.update(conversation_id=conversation_id, parent_run_id=previous_id)
                    db.execute('UPDATE runs SET body=? WHERE id=?', (packed(old), legacy_id))
                    previous_id, previous_time = legacy_id, old['created_at']
            if chat and chat[0] != parent_id:
                raise DatasetContextError(409, '会话已有新的问答，请刷新会话后重试。')
            if parent_id:
                parent_row = db.execute('SELECT instance,body FROM runs WHERE id=?', (parent_id,)).fetchone()
                if not parent_row:
                    raise DatasetContextError(404, '上一轮问答不存在，请重新选择会话。')
                parent = json.loads(parent_row[1])
                if parent.get('conversation_id') not in (None, conversation_id):
                    raise DatasetContextError(409, '不能引用其他会话的问答。')
                if parent['status'] in ('queued', 'running') and parent_row[0] == INSTANCE:
                    raise DatasetContextError(409, '上一轮问答仍在进行，请等待结束或取消。')
                # Old browser-only histories can continue from one unclaimed legacy turn.
                if parent.get('conversation_id') is None:
                    parent['conversation_id'] = conversation_id
                    db.execute('UPDATE runs SET body=? WHERE id=?', (packed(parent), parent_id))
            if not chat:
                db.execute('INSERT INTO conversations VALUES (?,?,?,?,?)',
                           (conversation_id, None, (legacy_title or (parent['question'] if parent_id else request['question']))[:80], value['created_at'], value['created_at']))
            db.execute('UPDATE conversations SET head=?,updated_at=? WHERE id=?',
                       (value['id'], value['created_at'], conversation_id))
            if parent_id and _inspection_only(db,parent):
                # Only an actual follow-up promotes an inspection to the chat list.
                db.execute('UPDATE conversations SET title=? WHERE id=?',(request['question'][:80],conversation_id))
        _append(db, value, 'turn/start', {})
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?)', (value['id'], key, fingerprint, INSTANCE, packed(value)))
    return value, True


def get_run(identifier):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT instance,body FROM runs WHERE id=?', (identifier,)).fetchone()
        value = _read_run(db, identifier, row)
    return value


def _read_run(db, identifier, row=None):
    row = row or db.execute('SELECT instance,body FROM runs WHERE id=?', (identifier,)).fetchone()
    if not row:
        raise DatasetContextError(404, '问答任务不存在。')
    value = json.loads(row[1])
    if value.get('conversation_id'):
        _ensure_visible(db, value['conversation_id'])
    if _inspection_only(db,value):
        value['conversation_origin']='greenhouse_design_inspection'
    if row[0] != INSTANCE and value['status'] in ('queued', 'running'):
        value.update(status='interrupted', detail='服务已重启，本次问答已中断，请重新提问。')
        if isinstance(value.get('thinking'), dict):
            value['thinking']['status'] = 'interrupted'
        value['analysis'] = analysis.finish(value.get('analysis'), 'interrupted')
        _append(db, value, 'turn/end', {})
        db.execute('UPDATE runs SET body=? WHERE id=?', (packed(value), identifier))
    return value


def update_run(identifier, **changes):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT body FROM runs WHERE id=?', (identifier,)).fetchone()
        value = json.loads(row[0])
        if value['cancelled']:
            return value  # A late model response can never overwrite cancellation.
        before = public_run(value)
        value.update(changes)
        if value['status'] in analysis.TERMINAL:
            value['analysis'] = analysis.finish(value.get('analysis'), value['status'], value.get('detail', ''))
            if isinstance(value.get('thinking'), dict):
                value['thinking']['status'] = 'completed' if value['status']=='answered' else value['status']
        if before != public_run(value):
            _append(db, value, 'turn/end' if value['status'] in analysis.TERMINAL else 'turn/checkpoint', {},
                    f"{identifier}:step:{value.get('cycle', 0)}")
        db.execute('UPDATE runs SET body=? WHERE id=?', (packed(value), identifier))
    return value


def cancel(identifier):
    value = get_run(identifier)
    if value['status'] in ('queued', 'running'):
        return update_run(identifier, status='cancelled', cancelled=True, detail='已取消本次问答。')
    return value


def ancestors(run, limit=64):
    """Only follow server-owned parent links inside the same conversation."""
    result, seen = [], {run['id']}
    identifier = run.get('parent_run_id')
    while identifier and len(result) < limit:
        if identifier in seen:
            raise DatasetContextError(409, '会话关联异常，请开启新对话。')
        seen.add(identifier)
        parent = get_run(identifier)
        if not run.get('conversation_id') or parent.get('conversation_id') != run['conversation_id']:
            raise DatasetContextError(409, '会话上下文不匹配。')
        result.append(parent)
        identifier = parent.get('parent_run_id')
    return result


def _inspection_only(db, run):
    """A saved-design inspection is a task preview until the user follows up.

    Infer the old records from their immutable snapshot; no history is deleted.
    A normal manually-created question using a design snapshot remains a chat.
    """
    if run.get('parent_run_id'):
        return False
    if run.get('conversation_origin')=='greenhouse_design_inspection':
        return True
    from .design_inspection import QUESTION
    if run.get('question')!=QUESTION or not run.get('snapshot_id'):
        return False
    row=db.execute('SELECT body FROM snapshots WHERE id=?',(run['snapshot_id'],)).fetchone()
    if not row:return False
    snapshot=json.loads(row[0])
    return snapshot.get('data_mode')=='greenhouse_design' and bool(snapshot.get('inspection_id'))


def list_conversations():
    with connect() as db:
        rows=db.execute('SELECT c.id,c.head,c.title,c.created_at,c.updated_at,r.body FROM conversations c '
                        'LEFT JOIN runs r ON r.id=c.head WHERE NOT EXISTS '
                        '(SELECT 1 FROM deleted_conversations d WHERE d.id=c.id) ORDER BY c.updated_at DESC')
        visible=[]
        for row in rows:
            if row[5] and _inspection_only(db,json.loads(row[5])):continue
            visible.append({'id':row[0],'head_run_id':row[1],'title':row[2],'created_at':row[3],'updated_at':row[4]})
            if len(visible)==100:break
        return visible


def get_conversation(identifier):
    with connect() as db:
        # Snapshot and cursor must share a transaction, including restart recovery.
        db.execute('BEGIN IMMEDIATE')
        _ensure_visible(db, identifier)
        row = db.execute('SELECT head,title,updated_at FROM conversations WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise DatasetContextError(404, '会话不存在。')
        runs, seen, current = [], set(), row[0]
        while current and len(runs) < 100:
            if current in seen:
                raise DatasetContextError(409, '会话关联异常。')
            seen.add(current)
            run = _read_run(db, current)
            if run.get('conversation_id') != identifier:
                raise DatasetContextError(409, '会话上下文不匹配。')
            runs.append(public_run(run))
            current = run.get('parent_run_id')
        events = _event_rows(db, identifier, 'ORDER BY seq DESC LIMIT 128')
        cursor = events[0]['seq'] if events else 0
        return {'id': identifier, 'title': row[1], 'head_run_id': row[0], 'updated_at':row[2],
                'runs': list(reversed(runs)), 'has_older': bool(current),
                'cursor': cursor, 'timeline': list(reversed(events)), 'protocol_version': 1}


def _event_rows(db, identifier, suffix, args=()):
    rows = db.execute('SELECT seq,turn_id,step_id,type,time,data FROM assistant_events WHERE conversation_id=? '
                      + suffix, (identifier, *args)).fetchall()
    return [{'seq': r[0], 'turn_id': r[1], 'step_id': r[2], 'type': r[3], 'time': r[4],
             'data': json.loads(r[5])} for r in rows]


def conversation_events(identifier, after=0, limit=100):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _ensure_visible(db, identifier)
        chat = db.execute('SELECT head FROM conversations WHERE id=?', (identifier,)).fetchone()
        if not chat:
            raise DatasetContextError(404, '会话不存在。')
        _read_run(db, chat[0])
        head = db.execute('SELECT COALESCE(MAX(seq),0) FROM assistant_events WHERE conversation_id=?',
                          (identifier,)).fetchone()[0]
        if after < 0 or after > head:
            raise DatasetContextError(409, '事件游标已失效，请重新加载会话。')
        return {'events': _event_rows(db, identifier, 'AND seq>? ORDER BY seq LIMIT ?', (after, limit)),
                'cursor': head, 'protocol_version': 1}


def _ensure_visible(db, identifier):
    if db.execute('SELECT 1 FROM deleted_conversations WHERE id=?',(identifier,)).fetchone():
        raise DatasetContextError(404, '会话不存在或已删除。')


def rename_conversation(identifier, title):
    title=title.strip()
    if not title or len(title)>80:
        raise DatasetContextError(422,'会话名称需为1至80个字符。')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _ensure_visible(db,identifier)
        if not db.execute('SELECT 1 FROM conversations WHERE id=?',(identifier,)).fetchone():
            raise DatasetContextError(404,'会话不存在。')
        db.execute('UPDATE conversations SET title=? WHERE id=?',(title,identifier))
    return {'id':identifier,'title':title}


def delete_conversation(identifier):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT head FROM conversations WHERE id=?',(identifier,)).fetchone()
        if not row:raise DatasetContextError(404,'会话不存在。')
        if db.execute('SELECT 1 FROM deleted_conversations WHERE id=?',(identifier,)).fetchone():
            return {'id':identifier,'deleted':True}
        if row[0] and _read_run(db,row[0])['status'] in ('queued','running'):
            raise DatasetContextError(409,'会话正在回答中，请先等待完成或取消回答。')
        db.execute('INSERT INTO deleted_conversations VALUES (?,?)',(identifier,time.time()))
    return {'id':identifier,'deleted':True}
