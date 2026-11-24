import json
from uuid import uuid4
import pytest
from api.assistant import runtime,store
from test_assistant_protocol import is_intent,intent_reply,text_reply
from test_assistant_conversation import provider

@pytest.mark.parametrize('wrap',[False,True])
def test_format_variants_keep_exact_text_references_and_conditions(wrap):
    body={'claims':[{'text':'模型估算温度为15°C。','basis':'evidence','evidence_ids':'F:point','conditions':'核对现场后再决策'}],
        'missing_conditions':None}
    text=json.dumps(body)
    candidate=runtime.parse_candidate('```json\n'+text+'\n```' if wrap else text)
    assert candidate.claims[0].text==body['claims'][0]['text']
    assert candidate.claims[0].evidence_ids==['F:point']
    assert candidate.claims[0].conditions==['核对现场后再决策']
    assert candidate.missing_conditions==[]

@pytest.mark.parametrize('value',[
    '未经审核的普通正文',json.dumps({'claims':['普通正文'],'missing_conditions':[]}),
    json.dumps({'claims':[{'text':'普通正文','basis':'invented'}],'missing_conditions':[]}),
    json.dumps({'claims':[{'text':'普通正文','conditions':['条件']*5}],'missing_conditions':[]}),
])
def test_prose_unknown_basis_and_excess_conditions_are_not_silently_rewritten(value):
    with pytest.raises(ValueError):runtime.parse_candidate(value)

@pytest.fixture
def run(tmp_path,monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    return store.create_run(str(uuid4()),{'question':'解释植物与温度的关系','web_search_enabled':False})[0]

def test_normalization_has_full_schema_and_failure_logs_shape_only(run):
    def model(body):
        if is_intent(body):return intent_reply(body)
        if 'tools' in body:return text_reply('公开草稿')
        schema=body['messages'][0]['content']
        assert 'maxItems' in schema and 'missing_conditions' in schema and 'maxLength' in schema
        return text_reply(json.dumps({'claims':[{'text':'SECRET_PRIVATE_DRAFT','basis':'bad-value'}],'missing_conditions':[]}))
    runner=runtime.Runner(run,model)
    with pytest.raises(runtime.ModelProtocolError) as error:runner.model_tools([{'role':'user','content':'用户请求'}],runtime.TOOLS)
    assert error.value.code=='model_candidate_format'
    assert error.value.validation_errors==[{'type':'string_pattern_mismatch','path':['claims',0,'basis']}]
    assert 'SECRET_PRIVATE_DRAFT' not in json.dumps(error.value.validation_errors)

def test_candidate_format_failure_can_publish_only_independently_reviewed_recovery(run):
    calls=[]
    def model(body):
        calls.append(body)
        if len(calls)==1:return text_reply(json.dumps({'claims':[{'text':'温度影响植物生理活动。','basis':'general_knowledge'}],'missing_conditions':[]}))
        return text_reply(json.dumps({'semantic_verdict':'pass','checks':[{'check':c,'verdict':'pass'} for c in runtime.CHECKS]}))
    runner=runtime.Runner(run,model);runner.resolved={'route':{'mode':'knowledge'}}
    out=runner.failure('候选格式整理失败','model_candidate_format')
    assert out['status']=='partial' and len(calls)==2
    assert out['result']['generation']=='reviewed_conservative_answer'
    assert out['diagnostic']['recovery']['status']=='published'

def test_native_fenced_json_is_reviewed_without_normalization_or_invented_tools(tmp_path,monkeypatch):
    from assistant_fixtures import snapshot_body
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    snap=store.snapshot(snapshot_body())
    run=store.create_run(str(uuid4()),{'question':'查询 x=0.5 y=1 z=0.25 的温度','snapshot_id':snap['snapshot_id'],
        'position':{'x':.5,'y':1,'z':.25},'web_search_enabled':False})[0]
    def model(body):
        if is_intent(body):return intent_reply(body)
        reply=provider(body)
        if 'tools' in body:
            arguments=reply['choices'][0]['message']['tool_calls'][0]['function']['arguments']
            return text_reply('```json\n'+arguments+'\n```')
        assert '将给定的公开答案草稿' not in body['messages'][0]['content']
        return reply
    runner=runtime.Runner(run,model)
    result=runner.execute()
    assert result['status']=='answered' and runner.evaluations==2 and runner.tool_calls==1
