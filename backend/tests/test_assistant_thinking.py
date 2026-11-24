"""Native reasoning is a private wire channel, never a public analysis transcript."""
import json
from uuid import uuid4

import httpx
import pytest

from api.assistant import runtime, store
from api.assistant.model_stream import collect, ModelProtocolError
from assistant_fixtures import snapshot_body
from test_assistant_conversation import provider
from test_assistant_protocol import is_intent, intent_reply, text_reply
from test_assistant_stream import frames, delta, part


PRIVATE = 'PRIVATE_NATIVE_REASONING_DO_NOT_PUBLISH'


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    monkeypatch.delenv('TFIELD_ASSISTANT_THINKING_ENABLED', raising=False)
    snap = store.snapshot(snapshot_body())
    return store.create_run(str(uuid4()), {'conversation_id':str(uuid4()),
        'question':'查询 x=0.5 y=1 z=0.25 的温度', 'snapshot_id':snap['snapshot_id'],
        'position':{'x':.5,'y':1,'z':.25}, 'web_search_enabled':False})[0]


def assert_private(run):
    assert PRIVATE not in store.packed(store.get_run(run['id']))
    assert PRIVATE not in store.packed(store.get_conversation(run['conversation_id']))
    with store.connect() as db:
        assert all(PRIVATE not in row[0] for row in db.execute('SELECT data FROM assistant_events'))


def test_native_stream_keeps_channels_separate_and_reports_only_counts():
    counts = []
    result = collect(frames(delta({'reasoning_content':PRIVATE}),
        delta({'content':'public draft', 'reasoning_content':' continued'}),
        delta({'tool_calls':[part(0, '{}', 'a', 'read')]}, 'tool_calls')),
        lambda:None, retain_reasoning=True, reasoning_progress=counts.append)
    message = result['choices'][0]['message']
    assert message['reasoning_content'] == PRIVATE+' continued'
    assert message['content'] == 'public draft'
    assert message['tool_calls'][0]['function']['arguments'] == '{}'
    assert counts == [len(PRIVATE), len(PRIVATE+' continued')]
    with pytest.raises(ModelProtocolError):
        collect(frames(delta({'reasoning_content':PRIVATE}), done=False), lambda:None, retain_reasoning=True)


def test_native_tool_loop_echoes_exact_reasoning_and_journal_has_metadata_only(run):
    seen = []
    def transport(body):
        seen.append(json.loads(store.packed(body)))
        if is_intent(body): return intent_reply(body)
        result = provider(body)
        if 'tools' in body:
            assert body['thinking']['type'] == 'enabled' and body['tool_choice'] == 'auto'
            assert body['reasoning_effort'] == 'low' and body['max_tokens'] >= 8192
            result['choices'][0]['message']['reasoning_content'] = PRIVATE+str(len(seen))
        else:
            assert body['thinking']['type'] == 'disabled'
            assert PRIVATE not in store.packed(body)
        return result
    runner = runtime.Runner(run, transport)
    out = runner.execute()
    main = [b for b in seen if 'tools' in b]
    echoed = [m for m in main[1]['messages'] if m['role']=='assistant']
    assert echoed[0]['reasoning_content'] == PRIVATE+'2'
    assert any(m['role']=='tool' and m['tool_call_id']==echoed[0]['tool_calls'][0]['id'] for m in main[1]['messages'])
    assert out['status']=='answered' and runner.evaluations==2
    assert store.get_run(run['id'])['thinking']['status']=='completed'
    assert out['thinking']['calls']==2 and out['thinking']['reasoning_chars']>0
    assert_private(run)


def test_native_plain_final_is_normalized_reviewed_and_echoed_without_fake_tools(run):
    seen, candidate = [], None
    def transport(body):
        nonlocal candidate
        seen.append(json.loads(store.packed(body)))
        if is_intent(body): return intent_reply(body)
        if 'tools' in body:
            candidate = json.loads(provider(body)['choices'][0]['message']['tool_calls'][0]['function']['arguments'])
            result = text_reply('指定位置温度 15.00 °C。')
            result['choices'][0]['message']['reasoning_content'] = PRIVATE
            return result
        assert PRIVATE not in store.packed(body)
        if '将给定的公开答案草稿' in body['messages'][0]['content']:
            return text_reply(json.dumps(candidate))
        return provider(body)
    runner = runtime.Runner(run, transport)
    out = runner.execute()
    assert out['status']=='answered' and runner.evaluations==2
    assert runner.protocol_repairs==0 and runner.tool_calls==1  # deterministic field preflight only
    second = [b for b in seen if 'tools' in b][1]
    previous = next(m for m in second['messages'] if m['role']=='assistant')
    assert previous['reasoning_content']==PRIVATE and 'tool_calls' not in previous
    assert not any(m['role']=='tool' for m in second['messages'])
    assert any('candidate_review' in m.get('content','') for m in second['messages'] if m['role']=='user')
    assert_private(run)


def test_native_invalid_final_never_publishes_unchecked_prose(run):
    def transport(body):
        if is_intent(body): return intent_reply(body)
        return text_reply('unapproved answer')
    with pytest.raises(ModelProtocolError, match='候选格式整理'):
        runtime.Runner(run, transport).execute()
    assert store.get_run(run['id'])['result'] is None


def test_native_empty_submission_retry_still_echoes_reasoning(run):
    main=[]
    def transport(body):
        if is_intent(body): return intent_reply(body)
        if 'tools' in body:
            main.append(json.loads(store.packed(body)))
            if len(main)==1:
                result=text_reply(None)
                result['choices'][0]['message']['reasoning_content']=PRIVATE
                return result
        return provider(body)
    runner=runtime.Runner(run,transport)
    assert runner.execute()['status']=='answered'
    echoed=next(m for m in main[1]['messages'] if m['role']=='assistant')
    assert echoed['content'] is None and echoed['reasoning_content']==PRIVATE
    assert runner.protocol_repairs==1
    assert_private(run)


def test_native_cancel_during_reasoning_prevents_tools_and_late_publication(run, monkeypatch):
    def upstream(request):
        body=json.loads(request.content)
        if 'tools' not in body:
            return httpx.Response(200, text='\n'.join(frames(delta({'content':intent_reply(body)['choices'][0]['message']['content']},'stop')))+'\n')
        store.cancel(run['id'])
        return httpx.Response(200, text='\n'.join(frames(delta({'reasoning_content':PRIVATE}),
            delta({'tool_calls':[part(0,'{}','a','read_snapshot')]},'tool_calls')))+'\n')
    monkeypatch.setattr(runtime.config,'api_key',lambda:'test')
    runner=runtime.Runner(run)
    runner.client=httpx.Client(transport=httpx.MockTransport(upstream))
    with pytest.raises(runtime.BudgetExceeded, match='cancelled'): runner.execute()
    assert runner.tool_calls==1 and store.get_run(run['id'])['result'] is None
    assert store.get_run(run['id'])['thinking']['status']=='cancelled'
    assert_private(run)


def test_native_context_budget_includes_full_private_echo(run):
    runner=runtime.Runner(run, lambda _:pytest.fail('oversize context must not be sent'))
    with pytest.raises(runtime.BudgetExceeded, match='context_budget'):
        runner.model([{'role':'assistant','content':None,'reasoning_content':PRIVATE*2000}], runtime.TOOLS)
    assert runner.calls==0


def test_global_rollback_disables_thinking_even_for_default_native_run(run, monkeypatch):
    monkeypatch.setenv('TFIELD_ASSISTANT_THINKING_ENABLED','false')
    runner=runtime.Runner(run, provider)
    assert not runner.native_enabled
    assert runner.execute()['status']=='answered'


def test_native_http_stream_echo_and_new_turn_use_public_history_only(run, monkeypatch):
    seen=[]
    def upstream(request):
        body=json.loads(request.content)
        seen.append(body)
        assert body['stream'] is True
        response=intent_reply(body) if is_intent(body) else provider(body)
        message=response['choices'][0]['message']
        if 'tools' in body:
            call=message['tool_calls'][0]
            chunks=[delta({'reasoning_content':PRIVATE}),
                delta({'tool_calls':[part(0,call['function']['arguments'],call['id'],call['function']['name'])]},'tool_calls')]
        else:
            assert PRIVATE not in store.packed(body)
            chunks=[delta({'content':message['content']},'stop')]
        return httpx.Response(200,text='\n'.join(frames(*chunks))+'\n')
    monkeypatch.setattr(runtime.config,'api_key',lambda:'test')
    def execute(turn):
        runner=runtime.Runner(turn)
        runner.client=httpx.Client(transport=httpx.MockTransport(upstream))
        return runner.execute()
    assert execute(run)['status']=='answered'
    main=[b for b in seen if 'tools' in b]
    assert next(m for m in main[1]['messages'] if m['role']=='assistant')['reasoning_content']==PRIVATE
    assert_private(run)
    seen.clear()
    follow=store.create_run(str(uuid4()),{'conversation_id':run['conversation_id'],
        'parent_run_id':run['id'],'question':'那 x=1.5 呢？','web_search_enabled':False})[0]
    assert execute(follow)['status']=='answered'
    first=next(b for b in seen if 'tools' in b)
    history=next(m for m in first['messages'] if m['role']=='assistant')
    assert history['reasoning_content']=='' and '15' in history['content']
    assert PRIVATE not in store.packed(first)
    assert_private(follow)
