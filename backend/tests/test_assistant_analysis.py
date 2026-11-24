import json
from uuid import uuid4

import httpx
import pytest

from api.assistant import analysis, knowledge, runtime, store
from assistant_fixtures import snapshot_body
from test_assistant_field_tools import grounded_transport, model_reply


@pytest.fixture
def snap(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    return store.snapshot(snapshot_body())


def run_for(snap, question, **extra):
    return store.create_run(str(uuid4()), {'snapshot_id': snap['snapshot_id'] if snap else None,
        'question': question, **extra})[0]


def test_dynamic_nodes_update_by_identity_and_close_on_cancel():
    record=analysis.Analysis()
    record.node('goal','解释温度与生长的关系','围绕用户原问题。')
    record.node('point:1','指定点温查询','正在读取快照。','running')
    record.node('point:1','指定点温查询','已取得点温。','completed')
    record.node('review:1','候选检查','正在核验。','running')
    finished=analysis.finish(record.body,'cancelled')
    nodes=finished['public_nodes']
    assert [n['id'] for n in nodes]==['goal','point:1','review:1','outcome']
    assert nodes[1]['summary']=='已取得点温。' and nodes[2]['status']=='cancelled'
    assert not any(n['title'] in ('数据获取','对比分析') for n in nodes)


def test_simple_answer_summary_does_not_invent_tool_steps():
    record=analysis.Analysis()
    record.node('goal','解释一般生长机制','无需查询现场数据。')
    finished=analysis.finish(record.body,'answered')
    assert [n['id'] for n in finished['public_nodes']]==['goal','outcome']


def test_public_stages_are_persisted_before_model_and_exclude_provider_reasoning(snap):
    run = run_for(snap, '当前最热位置在哪里？')
    observed = []
    def provider(body):
        observed.append(store.get_run(run['id'])['analysis'])
        reply = grounded_transport(body)
        reply['choices'][0]['message']['reasoning_content'] = 'PRIVATE_REASONING_DO_NOT_PUBLISH'
        return reply
    out = runtime.Runner(run, provider).execute()
    assert observed[0]['steps'][0]['status'] == 'running'
    before = observed[1]['steps']
    assert before[0]['status'] == before[1]['status'] == 'completed'
    assert before[-1]['status'] == 'pending'  # No conclusion published before candidate/review.
    record = out['analysis']
    assert out['status'] == 'answered' and record['finished_at'] is not None
    assert [s['title'] for s in record['steps']] == ['需求解析', '数据获取', '对比分析', '得出结论']
    assert all(s['status'] == 'completed' for s in record['steps'])
    encoded = json.dumps(record, ensure_ascii=False)
    assert '28.00' in encoded and 'find_temperature_extrema' in encoded
    assert 'PRIVATE_REASONING' not in encoded and 'volume' not in encoded
    assert '本题无需农业标准对比' in observed[1]['steps'][2]['summary']
    saved = store.get_run(run['id'])
    assert saved['analysis'] == record and saved['status'] == 'answered'
    assert saved['result'] == out['result']


@pytest.mark.parametrize('question,with_snapshot,status', [
    ('当前最冷在哪里？', False, 'needs_snapshot'),
    ('明天下午温度是多少？', True, 'unsupported'),
    ('这个位置现在几度？', True, 'needs_clarification')])
def test_early_exit_does_not_claim_data_or_comparison_completed(snap, question, with_snapshot, status):
    run = run_for(snap if with_snapshot else None, question)
    out = runtime.Runner(run, lambda _: pytest.fail('no model needed')).execute()
    assert out['status'] == status
    assert out['analysis']['steps'][2]['status'] == 'skipped'
    assert out['analysis']['steps'][3]['status'] == 'blocked'


def test_failure_keeps_real_data_but_marks_review_and_conclusion_incomplete(snap):
    run = run_for(snap, '当前最高温度？')
    runner = runtime.Runner(run, lambda _: (_ for _ in ()).throw(httpx.ConnectError('private detail')))
    with pytest.raises(httpx.ConnectError):
        runner.execute()
    out = runner.failure('模型连接中断。')
    assert out['status'] == 'partial'
    assert [s['status'] for s in out['analysis']['steps']] == ['completed', 'completed', 'blocked', 'blocked']
    assert 'private detail' not in json.dumps(out['analysis'])


def test_cancel_freezes_analysis_and_restart_closes_active_stages(snap, monkeypatch):
    run = run_for(snap, '当前最高温度？')
    record = analysis.Analysis(run['analysis'])
    record.set('intent', 'running', '正在解析。')
    store.update_run(run['id'], status='running', analysis=record.body)
    cancelled = store.cancel(run['id'])
    assert cancelled['analysis']['steps'][0]['status'] == 'cancelled'
    store.update_run(run['id'], analysis=analysis.new(), status='answered')
    assert store.get_run(run['id'])['analysis'] == cancelled['analysis']
    another = run_for(snap, '当前均温？')
    store.update_run(another['id'], status='running', analysis=record.body)
    monkeypatch.setattr(store, 'INSTANCE', 'other-instance')
    interrupted = store.get_run(another['id'])
    assert interrupted['status'] == 'interrupted'
    assert interrupted['analysis']['steps'][0]['status'] == 'interrupted'


def test_qualitative_retrieval_reports_sources_without_claiming_expert_threshold(snap, monkeypatch):
    run = run_for(None, '叶片温度为什么与空气不同？')
    evidence = {'id': 'K:leaf', 'text': '叶片温度可能不同于空气温度。', 'title': '温度对象区分',
                'locator': 'p.31', 'evidence_kind': 'qualitative', 'release_sha256': 'approved'}
    monkeypatch.setattr(knowledge, 'search', lambda *a, **kw: {'status': 'ok', 'evidence': [evidence]})
    monkeypatch.setattr(knowledge, 'release', lambda: {'sha256': 'approved'})
    planners = []
    def provider(body):
        if 'tools' not in body:
            return model_reply({'role': 'assistant', 'content': json.dumps({'semantic_verdict': 'pass',
                'checks': [{'check': k, 'verdict': 'pass'} for k in runtime.CHECKS]})})
        planners.append(1)
        name = 'search_agri_knowledge' if len(planners) == 1 else 'finish_answer'
        args = {'query': '叶温'} if name == 'search_agri_knowledge' else {
            'claims': [{'text': evidence['text'], 'evidence_ids': ['K:leaf']}], 'missing_conditions': []}
        return model_reply({'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(uuid4()),
            'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]})
    out = runtime.Runner(run, provider).execute()
    assert out['status'] == 'answered'
    record = out['analysis']
    encoded = json.dumps(record, ensure_ascii=False)
    assert '温度对象区分' in encoded and 'p.31' in encoded and 'search_agri_knowledge' in encoded
    assert '未执行作物数值阈值' in encoded
    assert '不能替代本棚实测或作物数值标准' in encoded
    assert '已读取回放测点' not in encoded
