"""Public execution summaries. Never ingest provider reasoning, prompts or raw errors."""
from __future__ import annotations

from copy import deepcopy
import time

STEPS = (('intent', '需求解析'), ('data', '数据获取'), ('comparison', '对比分析'), ('conclusion', '得出结论'))
TERMINAL = {'answered', 'partial', 'failed', 'cancelled', 'interrupted', 'needs_snapshot',
            'needs_clarification', 'unsupported'}


def new():
    return {'version': 1, 'kind': 'execution_summary', 'started_at': None, 'finished_at': None,
            'public_nodes': [],
            'elapsed_ms': 0, 'steps': [{'id': key, 'title': title, 'status': 'pending',
                'summary': '等待执行。', 'items': []} for key, title in STEPS]}


class Analysis:
    def __init__(self, body=None):
        self.body = deepcopy(body) if body else new()

    def set(self, key, status, summary, items=()):
        now = time.time()
        self.body['started_at'] = self.body['started_at'] or now
        self.body['updated_at'] = now
        self.body['elapsed_ms'] = max(0, round((now-self.body['started_at'])*1000))
        step = next(s for s in self.body['steps'] if s['id'] == key)
        step.update(status=status, summary=summary)
        for item in items:
            if item not in step['items']:
                step['items'].append(deepcopy(item))
        step['items'] = step['items'][-8:]

    def node(self, identifier, title, summary, status='completed', items=()):
        """Public task/action summaries, never provider reasoning or a fabricated stage sequence."""
        nodes = self.body.setdefault('public_nodes', [])
        value = next((n for n in nodes if n['id'] == identifier), None)
        if value is None:
            if len(nodes) >= 48:
                return
            value = {'id': identifier}
            nodes.append(value)
        value.update(title=title[:180], summary=summary[:700], status=status,
                     items=deepcopy(list(items)[:6]))


def finish(body, status, detail=''):
    """Close unfinished stages on every terminal path, including cancellation/restart."""
    body = deepcopy(body)
    if not body or status not in TERMINAL or body.get('finished_at') is not None:
        return body
    now = time.time()
    if status == 'interrupted':
        now = body.get('updated_at') or body.get('started_at') or now
    body['finished_at'] = now
    body['elapsed_ms'] = max(0, round((now-(body.get('started_at') or now))*1000))
    for step in body['steps']:
        if step['status'] == 'pending':
            step.update(status='skipped', summary='本次流程未执行此阶段。')
        elif step['status'] == 'running':
            step.update(status=status if status in ('cancelled', 'interrupted') else 'blocked',
                        summary='本阶段未完成，未将候选内容作为结论发布。')
    for node in body.get('public_nodes', []):
        if node['status'] == 'running':
            node['status'] = status if status in ('cancelled','interrupted') else 'blocked'
    if 'public_nodes' in body and not any(n['id']=='outcome' for n in body['public_nodes']):
        body['public_nodes'].append({'id':'outcome','title':{
            'answered':'回答已通过检查','partial':'已保留确认的事实','cancelled':'任务已取消',
            'interrupted':'任务已中断','needs_clarification':'需要澄清问题','needs_snapshot':'需要现场数据',
            'unsupported':'当前能力边界'}.get(status,'本次分析未完成'),
            'summary': detail or ('综合回答与引用见下方。' if status=='answered' else '未发布未经检查的候选正文。'),
            'status':'completed' if status=='answered' else 'blocked','items':[]})
    conclusion = body['steps'][-1]
    conclusion.update(status={'answered': 'completed', 'partial': 'blocked', 'failed': 'failed',
        'cancelled': 'cancelled', 'interrupted': 'interrupted'}.get(status, 'blocked'),
        summary={'answered': '已完成复核，最终回答及引用见下方。',
                 'partial': detail or '仅保留工具确认的事实，模型解释未完成。',
                 'cancelled': '用户已取消，未继续发布回答。',
                 'interrupted': '服务已重启，本次分析已中断。',
                 'failed': '执行或证据检查未完成，未发布模型答案。'}.get(status, detail or '需要补充条件。'))
    return body


TOOL_LABELS = {'get_temperature_point': '指定坐标温度查询', 'find_temperature_extrema': '有效网格极值查询',
               'get_region_statistics': '区域统计', 'compare_regions': '双区域比较',
               'read_snapshot': '固定快照读取', 'search_agri_knowledge': '农业知识库检索',
               'search_web': '联网搜索', 'read_web_source': '联网原文读取'}


def field_items(name, facts):
    items = [{'text': f'已执行{TOOL_LABELS[name]}，返回 {len(facts)} 条事实。', 'tool': name,
              'evidence_ids': [f['id'] for f in facts]}]
    for fact in facts[:4]:
        value = fact.get('value')
        text = fact['text'] + (f'：{value:.2f} °C。' if isinstance(value, (float, int)) else '：该位置或区域无可报告数值。')
        pos = fact.get('position')
        if pos is None and fact.get('kind') == 'value':
            pos = {axis: fact[axis] for axis in ('x', 'y', 'z')}
        if pos:
            text += ' 坐标 (' + ', '.join(str(pos[a]) for a in ('x', 'y', 'z')) + ') m。'
        items.append({'text': text, 'evidence_ids': [fact['id']]})
    return items
