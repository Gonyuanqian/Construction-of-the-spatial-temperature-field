import json
from uuid import uuid4

import httpx
import pytest

from api.assistant import conversation, routing, runtime, store
from assistant_fixtures import snapshot_body


@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    return store.snapshot(snapshot_body())


def turn(snapshot,question,**kw):
    return store.create_run(str(uuid4()),{'conversation_id':str(uuid4()),'question':question,
        'snapshot_id':snapshot['snapshot_id'] if snapshot else None,'web_search_enabled':False,**kw})[0]


def reply(value):
    return {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(value)}}]}


def finish(text,basis='evidence',ids=None):
    value={'claims':[{'text':text,'basis':basis,'evidence_ids':ids or [],'conditions':[]}],'missing_conditions':[]}
    return {'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
        'tool_calls':[{'id':str(uuid4()),'type':'function','function':{'name':'finish_answer','arguments':json.dumps(value)}}]}}]}


def review(passed=True,reason='需要核实出处'):
    return reply({'semantic_verdict':'pass' if passed else 'fail','repair_action':'只回答可确认的定性内容',
        'checks':[{'check':c,'verdict':'fail' if not passed and c=='factual_grounding' else 'pass','reason':reason} for c in runtime.CHECKS]})


@pytest.mark.parametrize('question',[
    '你只能处理切面吗？','你只能切面的测点吗，非切面的测点不知道吗',
    '那你是否支持非切面位置的查询？','这个系统支持3D区域统计吗？',
])
@pytest.mark.parametrize('bound',[True,False])
def test_capability_question_never_reads_sensor_overview(env,question,bound):
    seen=[]
    run=turn(env if bound else None,question,position={'x':.5,'y':1,'z':.25})
    def model(body):
        seen.append(body)
        if 'understand_request' in body['messages'][-1]['content']:
            return reply({'task_kind':'capability','user_goal':'了解非切面位置是否在助手的支持范围内。',
                'answer_outline':[],'information_needs':[]})
        if 'tools' in body:
            assert [t['function']['name'] for t in body['tools']]==['finish_answer']
            data=json.loads(next(m['content'] for m in body['messages'] if m['role']=='user' and '"facts"' in m['content']))
            assert [f['id'] for f in data['facts']]==['F:capabilities']
            assert 'source_time' not in data['context']
            return finish('不只支持切面，也支持有效3D重建网格中的点位和区域查询；重建值不等于新增传感器实测。',ids=['F:capabilities'])
        return review()
    runner=runtime.Runner(run,model)
    result=runner.execute()
    assert result['status']=='answered' and not runner.field_facts
    assert result['result']['route']=='capability'
    assert not {'source_time','model_id','frame_index','facts'}.intersection(result['result']['snapshot'])
    assert all(not e['id'].startswith('F:sensor:') for e in result['result']['citations'])
    assert '回放测点概览' not in store.packed(result['analysis'])


def test_semantic_intent_can_correct_initial_selection_route_before_preflight(env):
    question='这些功能是不是仅限于图中的剖面范围？'
    assert routing.plan(question,position={'x':.5,'y':1,'z':.25})['mode']=='field'
    run=turn(env,question,position={'x':.5,'y':1,'z':.25})
    def model(body):
        if 'understand_request' in body['messages'][-1]['content']:
            return reply({'task_kind':'capability','user_goal':'确认空间查询的能力范围。','answer_outline':[],'information_needs':[]})
        if 'tools' in body:
            assert len(body['tools'])==1
            return finish('可以查询有效网格中的非切面重建位置，并不是新增实测点。',ids=['F:capabilities'])
        return review()
    runner=runtime.Runner(run,model)
    assert runner.execute()['status']=='answered' and not runner.field_facts
    assert store.get_run(run['id'])['route']=='capability'


def test_capability_followup_does_not_reuse_previous_data_query(env):
    first=turn(env,'当前 x=0.5 y=1 z=0.25 的温度是多少？')
    store.update_run(first['id'],status='answered',result={'claims':[{'text':'点温15°C','evidence_ids':[]}],
        'snapshot':{},'citations':[],'missing_conditions':[]},resolved_context={
            'task_question':first['question'],'selection':{'position':{'x':.5,'y':1,'z':.25}}})
    second=turn(env,'那你只能处理切面吗？',conversation_id=first['conversation_id'],parent_run_id=first['id'])
    resolved=conversation.resolve(second)
    assert resolved['route']['mode']=='capability'
    assert resolved['effective_question']==second['question']
    assert routing.plan('你帮我查一下当前 x=0.5 y=1 z=0.25 的温度')['mode']=='field'


def test_concept_names_are_not_measurement_values_and_soft_words_do_not_license_numbers():
    def candidate(text):return runtime.Candidate(claims=[{'text':text,'basis':'general_knowledge'}],missing_conditions=[])
    assert not runtime.validate_candidate(candidate('支持2D、3D解释，C3/C4植物和CO2是常用术语。'),{})
    assert not runtime.validate_candidate(candidate('一般来说，温度影响生理活动，具体范围因作物而异。'),{})
    assert runtime.validate_candidate(candidate('一般来说，本棚温度是29.75°C。'),{})
    assert runtime.validate_candidate(candidate('基于常规经验，应设为25°C。'),{})
    assert runtime.validate_candidate(candidate('测点为25°C。'),{})


def test_two_same_category_failures_stop_even_when_candidate_text_changes(env):
    run=turn(None,'温度对植物生长有什么影响？')
    main=[]
    def model(body):
        if 'understand_request' in body['messages'][-1]['content']:
            return reply({'task_kind':'knowledge','user_goal':'解释温度对生长的影响。','answer_outline':[],'information_needs':[]})
        if 'tools' in body:
            main.append(1)
            return finish(f'基于常规经验，温度应设为{20+len(main)}°C。','general_knowledge')
        if '现有资料给出简短保守回答' in body['messages'][0]['content']:
            return reply({'claims':[{'text':'一般来说，温度会影响植物生理过程；缺少具体作物和适用资料，不能给出统一设定值。',
                'basis':'general_knowledge','evidence_ids':[]}],'missing_conditions':[]})
        return review()
    runner=runtime.Runner(run,model)
    with pytest.raises(runtime.BudgetExceeded,match='review_stalled'):runner.execute()
    assert len(main)==2 and runner.evaluations==2
    result=runner.failure('连续两次同类检查未通过。','review_stalled')
    assert result['status']=='partial' and len(main)==2
    assert result['result']['generation']=='reviewed_conservative_answer'
    assert '21°C' not in store.packed(result) and '22°C' not in store.packed(result)
    assert runner.failure_category({'evaluation':{'checks':[{'check':'factual_grounding','verdict':'fail','reason':'缺文献'}]}})==runner.failure_category({'evaluation':{'checks':[{'check':'factual_grounding','verdict':'fail','reason':'出处不充分'}]}})
    assert runner.failure_category({'issues':['没有来源的通用知识不能报告精确数值']})==runner.failure_category({'evaluation':{'checks':[{'check':'citation_entailment','verdict':'fail'}]}})


def test_capability_failure_uses_contract_not_unrelated_bound_sensor_values(env):
    run=turn(env,'你只能切面的测点吗，非切面的测点不知道吗')
    runner=runtime.Runner(run,lambda _:(_ for _ in ()).throw(httpx.ConnectError('private upstream')))
    with pytest.raises(httpx.ConnectError):runner.execute()
    result=runner.failure('模型连接失败。','service_connection')
    assert result['status']=='partial'
    assert result['result']['generation']=='capability_contract_fallback'
    assert '不只限于切面' in result['result']['claims'][0]['text']
    assert 'F:sensor:' not in store.packed(result) and 'private upstream' not in store.packed(result)


def test_conservative_recovery_cannot_publish_a_softened_but_invented_number(env):
    run=turn(None,'温度影响植物生长的关系')
    def model(body):
        return reply({'claims':[{'text':'一般来说，应保持25°C。','basis':'general_knowledge','evidence_ids':[]}],
                      'missing_conditions':[]})
    runner=runtime.Runner(run,model)
    runner.resolved={'route':{'mode':'knowledge'}}
    result=runner.failure('连续两次同类审核失败','review_stalled')
    assert result['status']=='failed' and not result.get('result')
    assert '25°C' not in store.packed(store.get_run(run['id']))
    assert runner.calls==1  # No second recovery attempt or new Agent loop.
