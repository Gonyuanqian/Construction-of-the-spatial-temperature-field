import json
from uuid import uuid4

import pytest

from api.assistant import runtime, store
from assistant_fixtures import snapshot_body
from test_assistant_conversation import provider


def is_intent(body):
    return 'understand_request' in body['messages'][-1].get('content', '')


def intent_reply(body):
    return text_reply(json.dumps({'user_goal': '查询指定位置的温度', 'answer_outline': ['报告本轮点温与数据口径'], 'information_needs': ['固定快照']}))


def with_intent(fn):
    return lambda body: intent_reply(body) if is_intent(body) else fn(body)


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    snapshot = store.snapshot(snapshot_body())
    return store.create_run(str(uuid4()), {'conversation_id': str(uuid4()),
        'question': '查询 x=0.5 y=1 z=0.25 的温度', 'snapshot_id': snapshot['snapshot_id'],
        'position': {'x': .5, 'y': 1, 'z': .25}, 'web_search_enabled': False, 'thinking_enabled':False})[0]


def text_reply(text='unreviewed private draft: 999 °C'):
    return {'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': text}}]}


@pytest.mark.parametrize('draft', ['unreviewed private draft: 999 °C', '', '{"claims":[{"text":"999 °C"}]}'])
def test_non_tool_reply_recovers_without_publishing_or_parsing_plaintext(run, draft):
    observed = []
    def model(body):
        if is_intent(body): return intent_reply(body)
        observed.append(json.loads(store.packed(body)))
        if len(observed) == 1: return text_reply(draft)
        if 'tools' in body:
            assert body['tool_choice'] == 'required' and body['thinking']['type'] == 'disabled'
        else:
            assert 'tool_choice' not in body and body['response_format']['type'] == 'json_object'
        return provider(body)
    runner = runtime.Runner(run, model)
    result = runner.execute()
    assert result['status'] == 'answered' and result['protocol_repairs'] == 1
    assert runner.evaluations == 2 and runner.calls == 6
    assert result['result']['citations'][0]['value'] == 15
    # One preflight and two reviewed finish calls. No tool was invented from the text or JSON.
    assert runner.tool_calls == 3
    events = store.conversation_events(run['conversation_id'], limit=200)['events']
    assert all(not e['data'].get('run', {}).get('result') for e in events[:-1])
    persisted = store.packed(store.get_run(run['id'])) + store.packed(events)
    assert '999 °C' not in persisted and 'unreviewed private draft' not in persisted
    assert any('结构化工具调用' in m.get('content', '') for m in observed[1]['messages'] if m['role'] == 'user')


def test_recovery_does_not_rerun_successful_tools_or_lose_their_observations(run):
    observed = []
    def model(body):
        if is_intent(body): return intent_reply(body)
        observed.append(json.loads(store.packed(body)))
        if len(observed) == 1:
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
                'tool_calls': [{'id': 'snapshot-call', 'type': 'function',
                    'function': {'name': 'read_snapshot', 'arguments': '{}'}}]}}]}
        if len(observed) == 2: return text_reply()
        return provider(body)
    runner = runtime.Runner(run, model)
    out = runner.execute()
    assert out['status'] == 'answered' and runner.protocol_repairs == 1
    tools = [m for m in observed[2]['messages'] if m['role'] == 'tool']
    assert len(tools) == 1 and tools[0]['tool_call_id'] == 'snapshot-call'
    assert any(e['value'] == 15 for e in json.loads(tools[0]['content'])['facts'] if e.get('kind') == 'value')
    assert runner.evaluations == 2


def test_two_non_tool_replies_stop_with_bounded_cost_and_no_result(run):
    attempts = []
    def model(body):
        if is_intent(body): return intent_reply(body)
        attempts.append(1)
        assert body['tool_choice'] == 'required'
        return text_reply()
    runner = runtime.Runner(run, model)
    with pytest.raises(runtime.ModelProtocolError, match='格式纠正'):
        runner.execute()
    assert len(attempts) == 2 and runner.protocol_repairs == 1
    assert runner.calls == 3 and runner.evaluations == 0
    assert runner.last_model_response['tool_call_count'] == 0
    assert runner.last_model_response['finish_reason'] == 'stop'
    assert store.get_run(run['id'])['result'] is None
    assert '999 °C' not in store.packed(store.get_run(run['id']))


def test_cancellation_during_plain_reply_prevents_recovery_call(run):
    attempts = []
    def model(body):
        if is_intent(body): return intent_reply(body)
        attempts.append(1); store.cancel(run['id']); return text_reply()
    runner = runtime.Runner(run, model)
    with pytest.raises(runtime.BudgetExceeded, match='cancelled'):
        runner.execute()
    assert len(attempts) == 1 and runner.protocol_repairs == 0
    assert store.get_run(run['id'])['status'] == 'cancelled'


def test_protocol_repair_is_at_most_once_per_run(run):
    replies = []
    def model(body):
        if is_intent(body): return intent_reply(body)
        replies.append(1)
        if len(replies) in (1, 3): return text_reply()
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': 'read-one', 'type': 'function',
                           'function': {'name': 'read_snapshot', 'arguments': '{}'}}]}}]}
    runner = runtime.Runner(run, model)
    with pytest.raises(runtime.ModelProtocolError): runner.execute()
    assert len(replies) == 3 and runner.protocol_repairs == 1


def test_invalid_structured_call_count_is_not_repaired_or_partially_dispatched(run):
    calls = [{'id': str(i), 'type': 'function', 'function': {'name': 'read_snapshot', 'arguments': '{}'}} for i in range(5)]
    runner = runtime.Runner(run, with_intent(lambda body: {'choices': [{'finish_reason': 'tool_calls',
                                            'message': {'role': 'assistant', 'content': None, 'tool_calls': calls}}]}))
    with pytest.raises(runtime.ModelProtocolError): runner.execute()
    assert runner.calls == 2 and runner.protocol_repairs == 0 and runner.tool_calls == 1
