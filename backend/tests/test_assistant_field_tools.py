import copy
import json
from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.assistant import field_tools, routing, runtime, store
from assistant_fixtures import snapshot_body


@pytest.fixture
def snap(tmp_path,monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    return store.snapshot(snapshot_body())


def test_continuous_point_matches_independent_analytic_truth(snap):
    result=field_tools.point(snap,{'x':.5,'y':1.,'z':.25})
    assert result['value']==pytest.approx(15.)
    assert (result['x'],result['y'],result['z'])==(.5,1.,.25)


@pytest.mark.parametrize('point,kind',[
    ({'x':0,'y':0,'z':1},'outside'),({'x':1,'y':0,'z':1.1},'unmeasured'),
    ({'x':.5,'y':1,'z':.75},'unavailable')])
def test_invalid_domains_do_not_report_temperatures(snap,point,kind):
    result=field_tools.point(snap,point)
    assert result['kind']==kind and result['value'] is None


@pytest.mark.parametrize('x',[-1,3,float('nan'),float('inf')])
def test_point_out_of_bounds_rejected(snap,x):
    with pytest.raises(ValueError): field_tools.point(snap,{'x':x,'y':0,'z':0})


def test_extrema_exclude_unmeasured_and_nulls(snap):
    snap['volume']['planes'][0]['values'][3][1]=999
    result=field_tools.statistics(snap)
    assert result['valid_count']==21
    assert result['minimum']['value']==10
    assert result['maximum']['value']==28
    assert result['maximum']['tied_count']==2


def test_region_and_comparison_are_grid_arithmetic(snap):
    first=dict(x_min=1,x_max=1,y_min=0,y_max=4,z_min=0,z_max=1)
    second=dict(first,y_min=0,y_max=0)
    assert field_tools.statistics(snap,first)['mean']==20
    facts=field_tools.tool_facts(snap,'compare_regions',{'first':first,'second':second})
    assert facts[0]['value']==6
    assert facts[0]['first_mean']==20 and facts[0]['second_mean']==14


def test_region_without_valid_samples(snap):
    result=field_tools.statistics(snap,dict(x_min=0,x_max=0,y_min=0,y_max=4,z_min=1,z_max=1))
    assert result['status']=='no_data' and result['mean'] is None


def test_storage_and_view_ignore_later_source_changes(snap):
    original=store.get_snapshot(snap['snapshot_id'])
    original['volume']['planes'][0]['values'][0][0]=999
    assert field_tools.point(store.get_snapshot(snap['snapshot_id']),{'x':0,'y':0,'z':0})['value']==10
    assert 'volume' not in field_tools.public_snapshot(snap)


@pytest.mark.parametrize('q,mode,tool',[
    ('现在最热位置的坐标和温度是什么？','field','find_temperature_extrema'),
    ('当前 x=0.5 y=1 z=0.25 的温度？','field','get_temperature_point'),
    ('为什么自然通风也会温度不均？','knowledge',None),
    ('这个棚现在最热在哪里，为什么会这样？','mixed','find_temperature_extrema'),
    ('明天下午棚温是多少？','unsupported',None),
    ('过去两小时温度趋势？','unsupported',None),
    ('现在前部比后部热吗？','clarification',None),
    ('这个位置多少度？','clarification',None)])
def test_new_question_routing(q,mode,tool):
    out=routing.plan(q)
    assert out['mode']==mode and out.get('tool')==tool


def model_reply(message):
    return {'choices':[{'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop','message':message}],
            'usage':{'total_tokens':100}}


def grounded_transport(body):
    if 'tools' not in body:
        return model_reply({'role':'assistant','content':json.dumps({'semantic_verdict':'pass',
            'checks':[{'check':key,'verdict':'pass'} for key in runtime.CHECKS]})})
    data=json.loads(body['messages'][1]['content'])
    fact=next(f for f in data['facts'] if f['id'].startswith(('F:maximum:','F:point:')))
    return model_reply({'role':'assistant','content':None,'tool_calls':[{'id':str(uuid4()),'type':'function',
        'function':{'name':'finish_answer','arguments':json.dumps({'claims':[{'text':fact['text']+' '+format(fact['value'],'.2f')+' °C',
                'evidence_ids':[fact['id']]}],'missing_conditions':[]})}}]})


def test_runner_requires_site_fact_and_never_offers_knowledge_for_hotspot(snap):
    run,_=store.create_run(str(uuid4()),{'snapshot_id':snap['snapshot_id'],'question':'现在最热位置在哪里？'})
    observed=[]
    def provider(body):
        observed.append(body)
        return grounded_transport(body)
    runner=runtime.Runner(run,provider)
    result=runner.execute()
    assert result['status']=='answered'
    assert runner.evaluations==2
    assert all('search_agri_knowledge' not in [t['function']['name'] for t in body['tools']]
               for body in observed if 'tools' in body)
    assert result['result']['actions'][0]['snapshot_id']==snap['snapshot_id']
    assert result['result']['citations'][0]['value']==28


def test_missing_snapshot_does_not_call_model(snap):
    run,_=store.create_run(str(uuid4()),{'snapshot_id':None,'question':'现在最热位置？'})
    runner=runtime.Runner(run,lambda _:pytest.fail('must not call model'))
    assert runner.execute()['status']=='needs_snapshot'


def test_provider_failure_retains_only_verified_site_facts(snap):
    import httpx
    run,_=store.create_run(str(uuid4()),{'snapshot_id':snap['snapshot_id'],'question':'当前x=0.5 y=1 z=0.25温度？'})
    runner=runtime.Runner(run,lambda _:(_ for _ in ()).throw(httpx.ConnectError('test')))
    with pytest.raises(httpx.ConnectError): runner.execute()
    result=runner.failure('连接失败。')
    assert result['status']=='partial' and result['result']['citations'][0]['value']==15
    assert result['result']['generation']=='verified_tool_fallback'


def test_http_run_to_pinned_volume_and_point(snap,monkeypatch):
    from api.main import create_app
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','test')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake-not-sent')
    original=runtime.Runner
    monkeypatch.setattr(runtime,'Runner',partial(original,transport=grounded_transport))
    class ImmediatePool:
        def submit(self,fn,*args): fn(*args)
    monkeypatch.setattr(runtime,'POOL',ImmediatePool())
    client=TestClient(create_app()); headers={'X-TField-Internal-Key':'test'}
    submitted=client.post('/internal/v1/assistant/runs',headers=headers,json={
        'snapshot_id':snap['snapshot_id'],'request_key':str(uuid4()),'question':'现在最热位置在哪里？'})
    assert submitted.status_code==200
    result=client.get('/internal/v1/assistant/runs/'+submitted.json()['id'],headers=headers).json()
    assert result['status']=='answered' and result['result']['citations'][0]['value']==28
    volume=client.get(f'/internal/v1/assistant/snapshots/{snap["snapshot_id"]}/volume',headers=headers)
    assert volume.json()['field_ref']=='analytic-linear-field'
    point=client.get(f'/internal/v1/assistant/snapshots/{snap["snapshot_id"]}/point?x=.5&y=1&z=.25',headers=headers)
    assert point.json()['value']==15
