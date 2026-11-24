import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest

from api.assistant import runtime, store, model_stream
from api.assistant.model_stream import ModelProtocolError, collect
from api.dataset_context import DatasetContextError
from assistant_fixtures import snapshot_body
from test_assistant_conversation import provider


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    snap = store.snapshot(snapshot_body())
    return store.create_run(str(uuid4()), {'conversation_id': str(uuid4()), 'question': '查询 x=0.5 y=1 z=0.25 的温度',
        'snapshot_id': snap['snapshot_id'], 'position': {'x': .5, 'y': 1, 'z': .25}})[0]


def frames(*chunks, done=True):
    lines = []
    for chunk in chunks:
        lines += ['data: ' + json.dumps(chunk), '']
    return lines + (['data: [DONE]', ''] if done else [])


def delta(value, finish=None):
    return {'choices': [{'index': 0, 'delta': value, 'finish_reason': finish}]}


def part(index, args, identifier=None, name=None):
    value = {'index': index, 'function': {'arguments': args}}
    if identifier: value['id'] = identifier
    if name: value['function']['name'] = name
    return value


def test_interleaved_fragments_settle_before_dispatch_and_drop_private_reasoning():
    received = []
    out = collect(frames(
        delta({'reasoning_content': 'PRIVATE', 'tool_calls': [part(0, '{"x":', 'a', 'point'), part(1, '{', 'b', 'read')]}),
        delta({'tool_calls': [part(1, '}'), part(0, '1}')]}),
        {**delta({}, 'tool_calls'), 'usage': {'total_tokens': 80}}), lambda: None,
        lambda chars, tools: received.append((chars, tools)))
    message = out['choices'][0]['message']
    assert [(c['id'], json.loads(c['function']['arguments'])) for c in message['tool_calls']] == [('a', {'x': 1}), ('b', {})]
    assert 'PRIVATE' not in json.dumps(out) and out['usage']['total_tokens'] == 80
    assert received[-1][1] == 2


@pytest.mark.parametrize('retain',[True,False])
def test_fragmented_reasoning_over_old_wire_limit_keeps_small_message(retain):
    chunks=[{'id':'completion-'+'x'*100,'object':'chat.completion.chunk','model':'model-with-native-thinking',
             'created':1794664800,**delta({'reasoning_content':'片段'})} for _ in range(2500)]
    lines=frames(*chunks,delta({'content':'通过核验前的候选'},'stop'))
    assert sum(len(line.encode('utf-8')) for line in lines)>524288
    output=collect(lines,lambda:None,retain_reasoning=retain)
    assert output['choices'][0]['message']['content']=='通过核验前的候选'
    assert output['stream_metrics']['message_bytes']<20000
    if retain:assert output['choices'][0]['message']['reasoning_content']=='片段'*2500
    else:assert 'reasoning_content' not in output['choices'][0]['message']


@pytest.mark.parametrize('retain',[True,False])
def test_decoded_message_limit_includes_private_reasoning_even_when_discarded(monkeypatch,retain):
    monkeypatch.setattr(model_stream,'MAX_MESSAGE_BYTES',20)
    with pytest.raises(ModelProtocolError) as error:
        collect(frames(delta({'reasoning_content':'私密'*3}),delta({'content':'正文'})),lambda:None,retain_reasoning=retain)
    assert error.value.code=='model_stream_size'
    assert error.value.metrics['limit_kind']=='message'
    assert '私密' not in json.dumps(error.value.metrics)


@pytest.mark.parametrize('lines', [['data: '+'x'*256,''],['data: '+'x'*100,'data: '+'x'*100,'']])
def test_oversized_sse_event_is_bounded_before_json_parse(monkeypatch,lines):
    monkeypatch.setattr(model_stream,'MAX_EVENT_BYTES',180)
    with pytest.raises(ModelProtocolError) as error:collect(lines,lambda:None)
    assert error.value.code=='model_stream_size' and error.value.metrics['limit_kind']=='event'


def test_total_wire_limit_still_counts_heartbeat_and_metadata(monkeypatch):
    monkeypatch.setattr(model_stream,'MAX_STREAM_BYTES',80)
    with pytest.raises(ModelProtocolError) as error:collect([': '+'x'*40,': '+'x'*40],lambda:None)
    assert error.value.metrics['limit_kind']=='stream'


def test_full_http_native_message_can_exceed_old_sse_limit_without_early_tool_execution(run,monkeypatch):
    def upstream(request):
        chunks=[{'id':'completion-'+'x'*800,**delta({'reasoning_content':'PRIVATE'})} for _ in range(700)]
        chunks += [delta({'tool_calls':[part(0,'{}','tool-a','read_snapshot')]},'tool_calls')]
        return httpx.Response(200,text='\n'.join(frames(*chunks))+'\n')
    monkeypatch.setattr(runtime.config,'api_key',lambda:'test-only')
    runner=runtime.Runner(run)
    runner.client=httpx.Client(transport=httpx.MockTransport(upstream))
    try:message=runner.model([{'role':'user','content':'读取固定快照'}],runtime.TOOLS)
    finally:runner.client.close()
    assert message['tool_calls'][0]['function']['name']=='read_snapshot'
    assert runner.last_model_response['stream_metrics']['stream_bytes']>524288
    assert runner.last_model_response['stream_metrics']['message_bytes']<10000
    assert runner.tool_calls==0 and store.get_run(run['id'])['result'] is None
    assert 'PRIVATE' not in store.packed(store.get_run(run['id']))


@pytest.mark.parametrize('lines', [
    frames(delta({'tool_calls': [part(0, '{', 'a', 'read')]}), done=False),
    frames(delta({'tool_calls': [part(0, '{', 'a', 'read')]}, 'tool_calls')),
    frames(delta({'tool_calls': [part(0, '{}', 'a', 'read')]}), delta({'tool_calls': [part(0, '', 'changed')]})),
    frames(delta({'tool_calls': [part(0, '{}', 'a', 'read'), part(1, '{}', 'a', 'read')]}, 'tool_calls')),
    frames(delta({'tool_calls': [part(8, '{}', 'a', 'read')]}, 'tool_calls')),
])
def test_partial_corrupt_or_ambiguous_tools_are_never_dispatchable(lines):
    with pytest.raises(ModelProtocolError): collect(lines, lambda: None)


def test_length_discards_even_syntactically_complete_tools():
    out = collect(frames(delta({'tool_calls': [part(0, '{}', 'a', 'read')]}, 'length')), lambda: None)
    assert 'tool_calls' not in out['choices'][0]['message']


def test_cancel_during_stream_prevents_any_tool_result():
    calls = []
    def guard():
        calls.append(1)
        if len(calls) > 2: raise runtime.BudgetExceeded('cancelled')
    with pytest.raises(runtime.BudgetExceeded):
        collect(frames(delta({'tool_calls': [part(0, '{', 'a', 'read')]}), delta({}, 'tool_calls')), guard)


def test_journal_is_transactional_ordered_deduplicated_and_public(run):
    chat = run['conversation_id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: store.emit_activity(run['id'], f'tool:{i}', 'tool', 'completed', '固定快照查询',
                                                    evidence_count=1, secret='NEVER_PUBLIC'), range(12)))
    store.update_run(run['id'], last_evaluation={'private': 'NEVER_PUBLIC'})
    events = store.conversation_events(chat)['events']
    assert [e['seq'] for e in events] == list(range(1, 14))
    assert all(e['turn_id'] == run['id'] for e in events)
    assert 'NEVER_PUBLIC' not in store.packed(events)
    snapshot = store.get_conversation(chat)
    assert snapshot['cursor'] == events[-1]['seq'] and len(snapshot['timeline']) == len(events)
    store.cancel(run['id'])
    before = store.conversation_events(chat)['cursor']
    store.emit_activity(run['id'], 'late', 'model', 'completed', '迟到结果')
    store.update_run(run['id'], status='answered', result={'invalid': True})
    assert store.conversation_events(chat)['cursor'] == before
    assert store.get_conversation(chat)['runs'][0]['status'] == 'cancelled'
    with pytest.raises(DatasetContextError): store.conversation_events(chat, before + 1)


def test_restart_interrupt_is_durable_and_emitted_once(run, monkeypatch):
    monkeypatch.setattr(store, 'INSTANCE', 'restarted')
    one = store.get_conversation(run['conversation_id'])
    two = store.get_conversation(run['conversation_id'])
    assert one['cursor'] == two['cursor'] == 2
    assert two['timeline'][-1]['type'] == 'turn/end'
    assert two['runs'][0]['status'] == 'interrupted'


def test_real_runtime_path_uses_streaming_and_replay_has_only_approved_answer(run, monkeypatch):
    observed = []
    def upstream(request):
        body = json.loads(request.content)
        observed.append(body['stream'])
        message = provider(body)['choices'][0]['message']
        if message.get('tool_calls'):
            call = message['tool_calls'][0]
            args = call['function']['arguments']; mid = len(args)//2
            chunks = [delta({'tool_calls': [part(0, args[:mid], call['id'], call['function']['name'])]}),
                      delta({'tool_calls': [part(0, args[mid:])]}, 'tool_calls')]
        else:
            chunks = [delta({'content': message['content']}, 'stop')]
        return httpx.Response(200, text='\n'.join(frames(*chunks))+'\n', headers={'Content-Type': 'text/event-stream'})
    monkeypatch.setattr(runtime.config, 'api_key', lambda: 'test-only')
    runner = runtime.Runner(run)
    runner.client = httpx.Client(transport=httpx.MockTransport(upstream))
    result = runner.execute()
    assert result['status'] == 'answered' and all(observed) and len(observed) == 5
    events = store.conversation_events(run['conversation_id'])['events']
    assert any(e['type'] == 'activity/update' and e['data']['kind'] == 'model' for e in events)
    assert all(not e['data'].get('run', {}).get('result') for e in events[:-1])
    assert events[-1]['type'] == 'turn/end' and events[-1]['data']['run']['result']['claims']
    assert 'last_evaluation' not in store.packed(events)


def test_http_stream_auth_cursor_and_resume(run, monkeypatch):
    from fastapi.testclient import TestClient
    from api.main import create_app
    from api.routes import assistant
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN', 'test-stream-only')
    monkeypatch.setattr(assistant, 'STREAM_SECONDS', .05)
    store.cancel(run['id'])
    headers = {'x-tfield-internal-key': 'test-stream-only'}
    path = f"/internal/v1/assistant/conversations/{run['conversation_id']}/stream"
    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 403
        assert client.get(path+'?after=999', headers=headers).status_code == 409
        response = client.get(path+'?after=1', headers=headers)
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/event-stream')
    assert 'id: 2\n' in response.text and 'id: 1\n' not in response.text
    assert 'turn/end' in response.text and 'cancelled' in response.text
