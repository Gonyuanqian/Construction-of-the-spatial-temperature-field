import json
from uuid import uuid4
import pytest
from api.assistant import runtime, store, knowledge
from assistant_fixtures import snapshot_body


def test_user_goal_precedes_sources_and_general_answer_does_not_need_database(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths, 'PROJECT', tmp_path)
    monkeypatch.setattr(knowledge, 'search', lambda *a, **k: pytest.fail('no retrieval needed'))
    question='温度与植被生长的关系'
    snapshot=store.snapshot(snapshot_body())
    run=store.create_run(str(uuid4()), {'question':question,'snapshot_id':snapshot['snapshot_id'],'web_search_enabled':False})[0]
    seen=[]
    def provider(body):
        seen.append(body)
        if 'understand_request' in body['messages'][-1]['content']:
            value={'user_goal':'解释温度如何影响植物的生理过程与生长。',
                   'answer_outline':['生理活动与生长过程','低温和高温影响','条件与物种差异'], 'information_needs':[]}
        elif 'tools' in body:
            assert 'read_snapshot' not in [t['function']['name'] for t in body['tools']]
            context=json.loads(next(m['content'] for m in body['messages'] if m['role']=='user' and '"facts"' in m['content']))
            assert context['context']['answer_goal']['user_goal'].startswith('解释温度')
            assert 'source_time' not in context['context'] and 'model_id' not in context['context']
            value={'claims':[{'text':'温度通过影响酶促反应、光合作用与呼吸等生理过程，影响植物生长。',
                              'basis':'general_knowledge','evidence_ids':[]}], 'missing_conditions':[]}
            return {'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':str(uuid4()),'type':'function','function':{'name':'finish_answer','arguments':json.dumps(value)}}]}}]}
        else:
            value={'semantic_verdict':'pass','checks':[{'check':c,'verdict':'not_applicable' if c=='citation_entailment' else 'pass'} for c in runtime.CHECKS]}
        return {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(value)}}]}
    out=runtime.Runner(run,provider).execute()
    assert out['status']=='answered' and out['tool_calls']==1
    assert out['result']['citations']==[]
    saved=store.get_run(run['id'])
    assert saved['analysis']['steps'][0]['summary'].startswith('解释温度')
    assert saved['answer_plan']['answer_outline'][0]=='生理活动与生长过程'
    assert saved['evaluations']==2
    with store.connect() as db:
        rows=db.execute("SELECT data FROM assistant_events WHERE type='activity/update' ORDER BY seq").fetchall()
    assert json.loads(rows[0][0])['label']=='理解本轮问题'


def test_claim_types_keep_grounding_and_inference_boundaries():
    def candidate(**kwargs): return runtime.Candidate(claims=[kwargs],missing_conditions=[])
    assert not runtime.validate_candidate(candidate(text='温度影响植物生理活动。',basis='general_knowledge'),{})
    assert not runtime.validate_candidate(candidate(text='光照与CO2会影响温度响应。',basis='general_knowledge'),{})
    assert runtime.validate_candidate(candidate(text='本棚温度为 30 °C。',basis='general_knowledge'),{})
    assert runtime.validate_candidate(candidate(text='应保持 25 °C。',basis='general_knowledge'),{})
    assert runtime.validate_candidate(candidate(text='可能抑制生长。',basis='inference'),{})
    assert not runtime.validate_candidate(candidate(text='可能抑制生长。',basis='inference',conditions=['持续高温且供水受限']),{})
    assert runtime.validate_candidate(candidate(text='资料证明适宜。',basis='evidence'),{})
    sources={'K:a':{'text':'温度影响生理活动。','evidence_kind':'qualitative'},
             'W:b':{'text':'Responses depend on species.','original_verified':True}}
    assert not runtime.validate_candidate(candidate(text='温度对生长的影响与植物种类有关。',evidence_ids=['K:a','W:b']),sources)


def test_reviewer_still_rejects_unsupported_scope_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    run=store.create_run(str(uuid4()),{'question':'温度影响生长的过程'})[0]
    def reviewer(body):
        value={'semantic_verdict':'fail','checks':[{'check':c,'verdict':'fail' if c=='object_and_scope_consistency' else 'pass'} for c in runtime.CHECKS]}
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
    runner=runtime.Runner(run,reviewer)
    runner.evidence={'K:a':{'text':'湿帘利用水分蒸发降温。','evidence_kind':'qualitative'}}
    claim=runtime.Candidate(claims=[{'text':'所以证明植物蒸腾一定提高产量。','evidence_ids':['K:a']}],missing_conditions=[])
    assert runner.review(claim,{})['pass'] is False


def test_general_knowledge_still_requires_accuracy_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    run=store.create_run(str(uuid4()),{'question':'温度与植物生长'})[0]
    def reviewer(body):
        value={'semantic_verdict':'pass','checks':[{'check':c,'verdict':'not_applicable' if c in ('factual_grounding','citation_entailment') else 'pass'} for c in runtime.CHECKS]}
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}
    runner=runtime.Runner(run,reviewer)
    claim=runtime.Candidate(claims=[{'text':'温度影响生长。','basis':'general_knowledge'}],missing_conditions=[])
    assert runner.review(claim,{})['pass'] is False
