import json
from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.assistant import conversation, runtime, store
from api.dataset_context import DatasetContextError
from assistant_fixtures import snapshot_body
from test_assistant_field_tools import model_reply


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    return store.snapshot(snapshot_body())


def turn(chat, q, parent=None, **kw):
    return store.create_run(str(uuid4()), dict(conversation_id=chat, parent_run_id=parent,
                                               question=q, **kw))[0]


def complete(run, text='空气温度不能直接替代叶片温度。', **kw):
    return store.update_run(run['id'], status='answered', result={'claims':[{'text':text,'evidence_ids':['K:old']}],
        'citations':[], 'missing_conditions':[], 'snapshot':{}}, **kw)


def provider(body):
    if 'tools' not in body:
        return model_reply({'role':'assistant','content':json.dumps({'semantic_verdict':'pass',
            'checks':[{'check':k,'verdict':'pass'} for k in runtime.CHECKS]})})
    data = next(json.loads(m['content']) for m in body['messages'] if m['role']=='user' and m['content'].startswith('{')
                and 'facts' in json.loads(m['content']))
    fact = next(f for f in data['facts'] if f['id'].startswith('F:point:'))
    return model_reply({'role':'assistant','content':None,'tool_calls':[{'id':str(uuid4()),'type':'function',
        'function':{'name':'finish_answer','arguments':json.dumps({'claims':[{'text':f"指定位置温度 {fact['value']:.2f} °C",
            'evidence_ids':[fact['id']]}],'missing_conditions':[]})}}]})


def test_continuation_reaches_model_as_real_history_and_requeries_point(env):
    chat=str(uuid4())
    first=turn(chat,'当前 x=0.5 y=1 z=0.25 的温度？',snapshot_id=env['snapshot_id'])
    saved=complete(first,'上一轮说温度为 999 °C。',resolved_context={
        'task_question':first['question'],'snapshot_id':env['snapshot_id'],
        'selection':{'position':{'x':.5,'y':1,'z':.25},'region':None,'regions':None},'crop':'番茄','stage':'苗期'})
    second=turn(chat,'继续',first['id'])
    seen=[]
    def observe(body):
        seen.append(body)
        return provider(body)
    result=runtime.Runner(second,observe).execute()
    assert result['status']=='answered'
    assert result['result']['citations'][0]['value']==15
    assert result['result']['snapshot']['crop']=='番茄'
    initial=next(b['messages'] for b in seen if 'tools' in b)
    assert initial[1]['role']=='user' and initial[1]['content']==first['question']
    assert initial[2]['role']=='assistant' and '999' in initial[2]['content']
    assert json.loads(initial[3]['content'])['question']=='继续'
    assert '999' not in json.dumps(result['result']['claims'])
    assert store.get_run(second['id'])['history_turns_in_model']==1


def test_correction_refers_to_previous_answer_without_blind_knowledge_search(env):
    chat=str(uuid4()); first=turn(chat,'空气温度能代表叶片温度吗？'); complete(first)
    second=turn(chat,'你回答错了',first['id'])
    result=runtime.Runner(second,lambda _:pytest.fail('bare correction asks for scope without model')).execute()
    assert result['status']=='needs_clarification'
    assert '空气温度能代表叶片温度吗' in result['detail']
    assert '具体哪一句' in result['detail']
    assert store.get_run(second['id'])['resolved_context']['previous_run_id']==first['id']


def test_new_chat_and_cross_chat_links_are_isolated(env):
    first=turn(str(uuid4()),'原问题'); complete(first)
    with pytest.raises(DatasetContextError,match='其他会话'):
        turn(str(uuid4()),'继续',first['id'])
    fresh=turn(str(uuid4()),'继续')
    assert conversation.resolve(fresh)['route']['mode']=='clarification'
    assert conversation.messages(store.ancestors(fresh))==[]
    runtime.Runner(fresh,lambda _:pytest.fail('no model needed')).execute()
    repeated=turn(fresh['conversation_id'],'继续',fresh['id'])
    assert conversation.resolve(repeated)['route']['mode']=='clarification'


def test_head_concurrency_idempotency_and_cancel(env):
    chat=str(uuid4()); first=turn(chat,'原问题')
    with pytest.raises(DatasetContextError,match='仍在进行'):
        turn(chat,'继续',first['id'])
    store.cancel(first['id'])
    args={'conversation_id':chat,'parent_run_id':first['id'],'question':'继续'}; key=str(uuid4())
    one,_=store.create_run(key,args); two,created=store.create_run(key,args)
    assert two['id']==one['id'] and not created
    with pytest.raises(DatasetContextError,match='新的问答'):
        turn(chat,'另一个标签页的追问',first['id'])
    assert len(store.list_conversations())==1


def test_restart_restores_server_history(env,monkeypatch):
    chat=str(uuid4()); first=turn(chat,'原问题'); complete(first)
    second=turn(chat,'继续',first['id'])
    monkeypatch.setattr(store,'INSTANCE','new-server')
    history=store.get_conversation(chat)
    assert [r['id'] for r in history['runs']]==[first['id'],second['id']]
    assert history['runs'][-1]['status']=='interrupted'
    assert history['head_run_id']==second['id']


def test_rebinding_recomputes_values_and_partial_coordinate_followup(env):
    chat=str(uuid4()); first=turn(chat,'当前 x=0.5 y=1 z=0.25 的温度？',snapshot_id=env['snapshot_id'])
    resolved=conversation.resolve(first); complete(first,resolved_context={k:v for k,v in resolved.items() if k not in ('history','route')})
    body=snapshot_body()
    for plane in body['volume']['planes']:
        for row in plane['values']:
            for i,value in enumerate(row):
                if value is not None: row[i]=value+10
    body['source_time']='new-fixture-time'; body['volume']['time']='new-fixture-time'
    new=store.snapshot(body)
    second=turn(chat,'那 x=1.5 呢？',first['id'],snapshot_id=new['snapshot_id'])
    result=runtime.Runner(second,provider).execute()
    assert result['status']=='answered'
    assert result['result']['citations'][0]['value']==27
    assert result['result']['snapshot']['snapshot_changed'] is True
    assert store.get_run(second['id'])['resolved_context']['selection']['position']=={'x':1.5,'y':1,'z':.25}


def test_current_unsupported_request_not_hidden_by_previous_explanation(env):
    chat=str(uuid4()); first=turn(chat,'为什么自然通风也可能温度不均？'); complete(first)
    second=turn(chat,'那明天棚内是多少度？',first['id'])
    assert conversation.resolve(second)['route']['mode']=='unsupported'


def test_explicit_crop_clear_and_no_selection_leak_to_new_question(env):
    chat=str(uuid4()); first=turn(chat,'原问题',crop='番茄'); complete(first,resolved_context={'task_question':'原问题','crop':'番茄'})
    second=turn(chat,'另外解释空气与叶片的温度区别。',first['id'],crop=None)
    resolved=conversation.resolve(second)
    assert resolved['crop'] is None and resolved['followup']=='new_question'


def test_budgeted_history_has_no_traces_candidates_or_failed_answers(env):
    chat=str(uuid4()); head=None
    for i in range(8):
        current=turn(chat,'问题'+str(i)+'长问题'*900,head)
        saved=complete(current,'回答'*900)
        store.update_run(current['id'],analysis={**saved['analysis'],'SECRET_TRACE':True},last_evaluation={'SECRET_REVIEW':True})
        head=current['id']
    followup=turn(chat,'继续',head)
    messages=conversation.messages(store.ancestors(followup))
    assert len(messages)<=conversation.MAX_TURNS*2
    assert len(store.packed(messages).encode())<=conversation.MAX_BYTES
    assert '问题7' in messages[-2]['content']
    assert 'SECRET_' not in store.packed(messages)


def test_legacy_browser_history_imports_ids_but_uses_server_content(env):
    old,_=store.create_run(str(uuid4()),{'question':'真正的上一轮问题'})
    complete(old,'服务端保存的回答')
    failed,_=store.create_run(str(uuid4()),{'question':'你回答错了'})
    store.update_run(failed['id'],status='failed')
    chat=str(uuid4())
    followup=turn(chat,'继续解释',failed['id'],legacy_run_ids=[old['id'],failed['id']])
    resolved=conversation.resolve(followup)
    assert resolved['previous_run_id']==old['id']
    assert resolved['task_question']=='真正的上一轮问题'
    assert len(store.get_conversation(chat)['runs'])==3
    with pytest.raises(DatasetContextError):
        turn(str(uuid4()),'继续',old['id'],legacy_run_ids=[old['id']])


def test_api_conversations_and_specific_protocol_failure(env,monkeypatch):
    from api.main import create_app
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','private-test')
    monkeypatch.setenv('DEEPSEEK_API_KEY','not-sent')
    original=runtime.Runner
    monkeypatch.setattr(runtime,'Runner',partial(original,transport=lambda _:model_reply({'role':'assistant','content':'unstructured'})))
    class ImmediatePool:
        def submit(self,fn,*args):fn(*args)
    monkeypatch.setattr(runtime,'POOL',ImmediatePool())
    client=TestClient(create_app()); headers={'X-TField-Internal-Key':'private-test'}; chat=str(uuid4())
    submitted=client.post('/internal/v1/assistant/runs',headers=headers,json={
        'conversation_id':chat,'request_key':str(uuid4()),'thinking_enabled':False,'question':'空气温度与叶温区别是什么？'})
    assert submitted.status_code==200
    record=client.get('/internal/v1/assistant/conversations/'+chat,headers=headers).json()
    assert record['runs'][0]['error_code']=='model_tool_protocol'
    assert record['runs'][0]['diagnostic']['exception_type']=='ModelProtocolError'
    assert record['runs'][0]['diagnostic']['finish_reason']=='stop'
    assert record['runs'][0]['diagnostic']['tool_call_count']==0
    assert record['runs'][0]['protocol_repairs']==1
    assert record['runs'][0]['model_calls']==3
    assert 'unstructured' not in json.dumps(record)
    assert '工具协议' in record['runs'][0]['detail']
    assert client.get('/internal/v1/assistant/conversations').status_code==403
    assert client.get('/internal/v1/assistant/conversations',headers=headers).json()[0]['id']==chat
