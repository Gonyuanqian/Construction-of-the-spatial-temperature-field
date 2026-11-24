import json
from uuid import uuid4

import httpx
import pytest

from api.assistant import knowledge, routing, runtime, store, web_research as web


PAGE = ('根区温度会影响番茄生长，其效应受到根部供氧、营养及气温等条件的共同影响。'
        '本研究讨论温室番茄的根区环境，不等同于对所有作物和设施的管理处方。\n\n'
        'Root-zone temperature affects tomato growth. Experimental root temperature was 17 °C. '
        'This experimental condition must not be treated as a greenhouse control setpoint.')


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    monkeypatch.setattr(web.config, 'api_key', lambda: 'test-only')
    monkeypatch.delenv('TFIELD_ASSISTANT_WEB_SEARCH', raising=False)
    requests = []
    original = httpx.Client
    def respond(request):
        requests.append(request)
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': [
                {'title': '广告', 'url': 'https://farm-blog.example/unsupported', 'summary': '999 °C'},
                *[{'title': f'University tomato research {i}', 'url': f'https://extension.purdue.edu/research/tomato-{i}?utm_source=test#part',
                   'summary': '搜索摘要不是正文 999 °C', 'date': '2026-10-01T00:00:00Z'} for i in range(4)]]})
        return httpx.Response(200, json={'title': 'University tomato research', 'content': PAGE})
    monkeypatch.setattr(web.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    return requests


@pytest.mark.parametrize('url', [
    'http://extension.purdue.edu/test', 'https://127.0.0.1/test', 'https://localhost/test',
    'https://user:pass@extension.purdue.edu/test', 'https://extension.purdue.edu:8503/test',
    'https://extension.purdue.edu.evil.test/x', 'https://fao.org.evil.test/x',
    'https://news-blog.example/test', 'file:///etc/passwd'])
def test_only_public_primary_source_urls_are_eligible(url):
    assert web.public_url(url) is None


def test_original_read_required_summary_never_becomes_evidence(environment):
    session = web.WebResearch()
    result = session.search('tomato root zone temperature')
    assert result['status'] == 'ok' and 'evidence' not in result
    assert len(result['sources']) == 4
    assert result['sources'][0]['url'] == 'https://extension.purdue.edu/research/tomato-0'
    read = session.read(result['sources'][0]['source_id'])
    evidence = read['evidence'][0]
    assert evidence['id'].startswith('W:') and evidence['original_verified']
    assert '999' not in evidence['text'] and '17' in evidence['text']
    assert evidence['retrieved_at'] and evidence['content_sha256']
    assert '未入本地' in evidence['usage_limitations'][0]
    assert len(evidence['text'].encode()) < 2300
    assert all(str(request.url).startswith(web.API) for request in environment)


def test_search_read_budgets_cache_and_per_run_source_isolation(environment):
    session = web.WebResearch()
    first = session.search('root zone')
    assert session.search('root zone')['cached'] and session.search_calls == 1
    session.search('tomato temperature')
    assert session.search('greenhouse root')['status'] == 'budget_exhausted'
    for source in first['sources'][:3]: session.read(source['source_id'])
    assert session.read(first['sources'][0]['source_id'])['cached']
    assert session.read(first['sources'][3]['source_id'])['status'] == 'budget_exhausted'
    assert session.read_calls == 3 and len(environment) == 5
    with pytest.raises(ValueError): web.WebResearch().read(first['sources'][0]['source_id'])
    with pytest.raises(ValueError): session.read('https://extension.purdue.edu/arbitrary')


@pytest.mark.parametrize('query', ['sk-never-send-this-key', 'mail me@example.com', 'https://example.com/private', 'x'*129])
def test_private_or_unbounded_query_rejected_before_network(environment, query):
    with pytest.raises(ValueError): web.WebResearch().search(query)
    assert environment == []


def test_failures_are_nonfatal_and_do_not_leak_provider_body(monkeypatch):
    monkeypatch.setattr(web.config, 'api_key', lambda: 'test')
    original = httpx.Client
    monkeypatch.setattr(web.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(
        lambda req: httpx.Response(402, text='PRIVATE_PROVIDER_BODY sk-private'))))
    result = web.WebResearch().search('tomato temperature')
    assert result['status'] == 'unavailable' and 'PRIVATE' not in json.dumps(result)


def test_search_without_readable_original_cannot_produce_web_evidence(environment, monkeypatch):
    session = web.WebResearch(); source = session.search('root temperature')['sources'][0]
    monkeypatch.setattr(web, '_post', lambda *args: {'title': 'title', 'content': ''})
    assert session.read(source['source_id'])['evidence'] == []


def test_search_original_content_is_readable_even_when_fetch_is_unavailable(environment, monkeypatch):
    calls = []
    def post(operation, body, *args):
        calls.append(operation)
        assert operation == 'search' and body['need_content'] is True
        return {'results': [{'title': 'Original university research', 'url': 'https://extension.purdue.edu/original',
                             'content': PAGE, 'summary': 'unsupported 999 °C'}]}
    monkeypatch.setattr(web, '_post', post)
    session = web.WebResearch()
    found = session.search('root temperature')
    assert 'evidence' not in found and 'content' not in store.packed(found)
    evidence = session.read(found['sources'][0]['source_id'])['evidence'][0]
    assert evidence['retrieval_channel'] == 'search_original_content'
    assert '999' not in evidence['text'] and calls == ['search']


def test_web_numeric_guard_uses_original_text_not_timestamp_or_url():
    source = {'id': 'W:one', 'text': 'Experimental root temperature was 17 °C.', 'original_verified': True,
              'retrieved_at': '2026-10-31', 'source_url': 'https://extension.purdue.edu/999'}
    def claim(text, ids=None):
        return runtime.Candidate(claims=[{'text': text, 'evidence_ids': ids or ['W:one']}], missing_conditions=[])
    assert not runtime.validate_candidate(claim('该研究的实验根温为 17 °C。'), {'W:one': source})
    assert runtime.validate_candidate(claim('温度为 2026 °C。'), {'W:one': source})
    assert runtime.validate_candidate(claim('温度为 999 °C。'), {'W:one': source})
    assert runtime.validate_candidate(claim('根温影响生长'), {'W:one': {**source, 'original_verified': False}})
    assert runtime.validate_candidate(claim('根温影响生长', ['S:lead']), {'W:one': source})


def reply(message):
    return {'choices': [{'finish_reason': 'tool_calls' if message.get('tool_calls') else 'stop', 'message': message}]}


def call(name, args):
    return reply({'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(uuid4()), 'type': 'function',
                  'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}]})


def model_provider(body):
    if 'tools' not in body:
        return reply({'role': 'assistant', 'content': json.dumps({'semantic_verdict': 'pass',
                      'checks': [{'check': key, 'verdict': 'pass'} for key in runtime.CHECKS]})})
    results = [json.loads(m['content']) for m in body['messages'] if m['role'] == 'tool']
    if not results:
        return call('search_agri_knowledge', {'query': 'tomato root zone temperature'})
    external = next((e for r in results for e in r.get('evidence', []) if e['id'].startswith('W:')), None)
    return call('finish_answer', {'claims': [{'text': '根区温度会影响番茄生长。' if external else '本轮未取得可用资料。',
        'evidence_ids': [external['id'] if external else 'F:knowledge_status']}], 'missing_conditions': []})


@pytest.mark.parametrize('local_error', [False, True])
def test_runtime_local_miss_or_outage_automatically_searches_reads_and_reviews(environment, monkeypatch, local_error):
    def local(*args, **kwargs):
        if local_error: raise httpx.ConnectError('unavailable local test')
        return {'status': 'no_evidence', 'evidence': []}
    monkeypatch.setattr(knowledge, 'search', local)
    run = store.create_run(str(uuid4()), {'conversation_id': str(uuid4()), 'question': '根区温度如何影响番茄生长？'})[0]
    runner = runtime.Runner(run, model_provider)
    out = runner.execute()
    assert out['status'] == 'answered' and runner.evaluations == 2
    assert runner.online.search_calls == 1 and runner.online.read_calls == 2
    assert out['result']['citations'][0]['origin'] == 'web_original'
    assert out['result']['citations'][0]['review_status'] == 'claim_review_passed'
    events = store.conversation_events(run['conversation_id'], limit=200)['events']
    labels = [e['data'].get('label') for e in events if e['type'] == 'activity/update']
    assert '联网搜索' in labels and '联网原文读取' in labels


def test_disabled_network_registers_no_web_tools_and_never_makes_network_calls(environment, monkeypatch):
    monkeypatch.setattr(knowledge, 'search', lambda *a, **k: {'status': 'no_evidence', 'evidence': []})
    run = store.create_run(str(uuid4()), {'question': '根区温度如何影响生长？', 'web_search_enabled': False})[0]
    def model(body):
        if 'tools' in body:
            assert not {'search_web', 'read_web_source'}.intersection(t['function']['name'] for t in body['tools'])
        return model_provider(body)
    out = runtime.Runner(run, model).execute()
    assert out['status'] == 'answered' and environment == []


def test_latest_literature_route_does_not_require_live_snapshot():
    assert routing.plan('现在有哪些关于番茄根区温度的最新论文？')['mode'] == 'knowledge'
    assert routing.plan('当前 x=1 y=2 z=0.1 的温度是多少？')['mode'] == 'field'


@pytest.mark.parametrize('question',['简要解释温度影响生长，不必检索资料。','不要联网搜索，解释一般原理。','无需查文献，先说明机制。'])
def test_explicit_retrieval_opt_out_is_not_forced_online(question, environment):
    assert web.retrieval_opt_out(question) and not web.required(question)
    run=store.create_run(str(uuid4()),{'question':question})[0]
    runner=runtime.Runner(run,model_provider)
    assert not runner.web_enabled and not runner.retrieval_allowed
    assert environment==[]


def test_exhausted_web_does_not_prohibit_a_reviewed_answer(environment, monkeypatch):
    monkeypatch.setattr(knowledge, 'search', lambda *a, **k: {'status':'no_evidence','evidence':[]})
    run=store.create_run(str(uuid4()),{'question':'根区温度如何影响生长？'})[0]
    runner=runtime.Runner(run,model_provider)
    runner.online.search_calls=2
    result=runner.execute()
    assert result['status']=='answered' and runner.evaluations==2
