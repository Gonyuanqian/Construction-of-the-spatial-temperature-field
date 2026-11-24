import json
from uuid import uuid4
import pytest
from api.assistant import design_inspection as design,store,runtime
from api.assistant.ownership import owner_scope
from api.dataset_context import DatasetContextError

@pytest.fixture
def body(tmp_path,monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    return design.DesignSnapshotRequest(inspection_id=uuid4(),design_id=uuid4(),revision=3,captured_at='2026-11-17T09:00:00Z',
        spec={'name':'PRIVATE_PROJECT','location':{'longitude':126.42,'latitude':41.94,'opening_azimuth':180,'coordinate_system':'GCJ-02'},
            'structure':{'type':'arch','length_m':18,'width_m':6,'arch_height_m':2.4,'span_count':99,'covering':'film_shade'},
            'planting':{'cultivar':'','plant_spacing_m':.2,'band_width_m':1.2},'irrigation':{'drip_enabled':True,'sprinkler_enabled':False}},
        layout={'area_m2':108,'usable_length_m':16.6,'plant_count':996,'bed_count':3,'row_count':12,'sprinkler_count':0,'notices':[]})

def test_snapshot_is_frozen_idempotent_and_namespace_isolated(body):
    owner=str(uuid4())
    with owner_scope(owner):
        one=design.snapshot(body);assert one==design.snapshot(body)
        body.spec['structure']['length_m']=20
        with pytest.raises(DatasetContextError):design.snapshot(body)
        assert store.get_snapshot(one['snapshot_id'])['facts']==one['facts']
    with owner_scope(str(uuid4())):
        with pytest.raises(DatasetContextError):store.get_snapshot(one['snapshot_id'])

def test_design_facts_preserve_units_missing_fields_and_no_temperature(body):
    body.spec['lighting']={'enabled':True,'spacing_m':3,'mounting_height_m':1.6}
    body.layout['light_count']=18
    snap=design.snapshot(body);facts={f['id']:f for f in snap['facts']}
    assert snap['data_mode']=='greenhouse_design' and snap['design_revision']==3
    assert facts['F:design:planting:plant_spacing_m']['value']==.2
    assert facts['F:design:planting:plant_spacing_m']['display_value_cm']==20
    assert '未填写' in facts['F:design:planting:cultivar']['text']
    assert 'F:design:structure:span_count' not in facts
    assert 'PRIVATE_PROJECT' not in json.dumps(snap)
    assert all(f.get('unit')!='°C' for f in facts.values())
    assert 'volume' not in snap
    assert facts['F:design:lighting:mounting_height_m']['value']==1.6
    assert facts['F:design:layout:light_count']['value']==18

def test_search_query_is_public_vocabulary_only():
    query=design.public_query('PRIVATE_PROJECT 126.42 41.94 喷灌 水压')
    assert query=='人参 温室 设计 喷灌 水压'

def test_real_runner_uses_design_facts_and_reviewed_sections_without_temperature_tools(body):
    snapshot=design.snapshot(body)
    run=store.create_run(str(uuid4()),{'question':design.QUESTION,'snapshot_id':snapshot['snapshot_id'],'web_search_enabled':False,'crop':'人参'})[0]
    candidate={'claims':[{'text':'【检验结果】棚宽为6 m，几何可生成不证明农艺或结构适宜性。','evidence_ids':['F:design:structure:width_m']},
        {'text':'【调整建议】建议补充品种与栽培制度，再判断种植布局是否适合。','basis':'general_knowledge','evidence_ids':[]}],
        'missing_conditions':['材料性能与当地载荷资料']}
    seen=[]
    def model(request):
        seen.append(request)
        if json.loads(request['messages'][-1]['content']).get('task')=='greenhouse_design_inspection':
            assert 'tools' not in request
            assert 'F:design:structure:width_m' in json.dumps(request,ensure_ascii=False)
            return reply(candidate)
        return reply({'semantic_verdict':'pass','checks':[{'check':c,'verdict':'pass'} for c in design.CHECKS]})
    runner=runtime.Runner(run,model);out=runner.execute()
    assert out['status']=='answered' and runner.evaluations==1 and len(seen)==2
    assert out['result']['snapshot']['data_mode']=='greenhouse_design'
    assert out['result']['snapshot']['design_revision']==3
    assert not out['result']['actions']
    assert all('understand_request' not in m['messages'][-1]['content'] for m in seen)

def test_generic_template_and_uncited_numbers_are_rejected(body):
    snap=design.snapshot(body);evidence={f['id']:f for f in snap['facts']}
    c=runtime.Candidate(claims=[{'text':'【检验结果】全部合适。','basis':'general_knowledge'}],missing_conditions=[])
    assert design.issues(c)
    c=runtime.Candidate(claims=[{'text':'【调整建议】建议株距为25 cm。','evidence_ids':['F:design:planting:plant_spacing_m']}],missing_conditions=[])
    assert runtime.validate_candidate(c,evidence)


def reply(value):
    return {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(value,ensure_ascii=False)}}]}


def advisory():
    return {'claims':[
        {'text':'【检验结果】薄膜与遮阳网的组合同时影响透光和通风，应把遮阴与散热作为协调目标。',
         'basis':'inference','evidence_ids':['F:design:structure:covering'],'conditions':['以当前覆盖组合为前提，实际效果依赖材料与通风条件']},
        {'text':'【调整建议】一般可先核对作业通道是否满足人员通行，再结合参龄与栽培方式评估密度。',
         'basis':'general_knowledge','evidence_ids':[]}],
        'missing_conditions':['覆盖材料性能、参龄与作业方式']}


def run_design(body):
    snap=design.snapshot(body)
    return store.create_run(str(uuid4()),{'question':design.QUESTION,'snapshot_id':snap['snapshot_id'],
        'web_search_enabled':True,'crop':'人参'})[0]


def accepted():return {'semantic_verdict':'pass','checks':[{'check':c,'verdict':'pass'} for c in design.CHECKS]}


def test_without_design_knowledge_general_analysis_can_publish_after_one_independent_review(body,monkeypatch):
    from api.assistant import knowledge
    monkeypatch.setattr(knowledge,'configured',lambda:False)
    calls=[]
    def model(request):
        task=json.loads(request['messages'][-1]['content'])['task'];calls.append(task)
        if task=='greenhouse_design_inspection':
            assert '不强制文献引用' in request['messages'][0]['content']
            return reply(advisory())
        return reply(accepted())
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='answered' and calls==['greenhouse_design_inspection','review_greenhouse_design']
    assert out['result']['knowledge_status']=='not_configured'
    assert out['result']['analysis_level']=='preliminary_advisory'
    assert out['web_search_calls']==0 and out['result']['missing_conditions']


def test_unavailable_knowledge_cannot_trigger_a_search_loop_or_prevent_analysis(body,monkeypatch):
    from api.assistant import knowledge
    monkeypatch.setattr(knowledge,'configured',lambda:True)
    calls=[]
    def search(*args,**kwargs):calls.append((args,kwargs));raise OSError('local unavailable')
    monkeypatch.setattr(knowledge,'search',search)
    def model(request):
        return reply(advisory() if json.loads(request['messages'][-1]['content'])['task']=='greenhouse_design_inspection' else accepted())
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='answered' and len(calls)==1
    assert calls[0][1]['timeout']==3 and out['web_search_calls']==0
    assert out['result']['knowledge_status']=='unavailable'


def test_one_unsupported_numeric_suggestion_is_omitted_without_losing_reviewed_analysis(body):
    value=advisory();value['claims'].append({'text':'【调整建议】喷头水压设为999 MPa。','basis':'general_knowledge','evidence_ids':[]})
    def model(request):
        data=json.loads(request['messages'][-1]['content'])
        if data['task']=='greenhouse_design_inspection':return reply(value)
        assert len(data['candidate']['claims'])==2 and '999' not in store.packed(data['candidate'])
        return reply(accepted())
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='partial' and out['result']['omitted_claim_count']==1
    assert len(out['result']['claims'])==2 and '999' not in store.packed(out['result'])


def test_design_review_rejection_is_not_bypassed_and_repairs_are_bounded(body):
    calls=[]
    def model(request):
        data=json.loads(request['messages'][-1]['content']);calls.append(data['task'])
        if data['task']=='greenhouse_design_inspection':return reply(advisory())
        result=accepted();result['semantic_verdict']='fail'
        result['checks'][1].update(verdict='fail',reason='候选误解了材料性能')
        return reply(result)
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='failed' and not out.get('result')
    assert out['error_code']=='design_review_incomplete' and len(calls)==4
    assert calls.count('review_greenhouse_design')==2


def test_missing_independent_review_check_cannot_pass(body):
    def model(request):
        data=json.loads(request['messages'][-1]['content'])
        if data['task']=='greenhouse_design_inspection':return reply(advisory())
        result=accepted();result['checks']=result['checks'][:-1]
        return reply(result)
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='failed' and out['evaluations']==2


def test_malformed_generation_repairs_once_and_never_searches_for_format(body):
    generated=0
    def model(request):
        nonlocal generated
        data=json.loads(request['messages'][-1]['content'])
        if data['task']=='greenhouse_design_inspection':
            generated+=1
            if generated==1:return reply({'wrong':'shape'})
            assert data['revision_feedback']['issues']
            value=advisory();value['claims'][0]['text']=value['claims'][0]['text'].replace('【检验结果】','检验结果：')
            return reply(value)
        return reply(accepted())
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='answered' and out['model_calls']==3


def test_design_citations_still_observe_knowledge_release_withdrawal(body,monkeypatch):
    from api.assistant import knowledge
    monkeypatch.setattr(knowledge,'configured',lambda:True)
    monkeypatch.setattr(knowledge,'search',lambda *args,**kwargs:{'status':'ok','evidence':[
        {'id':'K:prior','text':'覆盖会影响棚内环境。','release_sha256':'old'}]})
    monkeypatch.setattr(knowledge,'release',lambda:{'sha256':'changed'})
    generated=0
    def model(request):
        nonlocal generated
        data=json.loads(request['messages'][-1]['content'])
        if data['task']=='greenhouse_design_inspection':
            generated+=1;value=advisory()
            if generated==1:value['claims'][0]['evidence_ids'].append('K:prior')
            else:assert 'K:prior' not in data['evidence']
            return reply(value)
        return reply(accepted())
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='answered' and generated==2
    assert all(e['id']!='K:prior' for e in out['result']['citations'])


@pytest.mark.parametrize('count',[7,12,24])
def test_many_field_citations_are_preserved_and_reviewed_without_regeneration(body,count):
    snap=design.snapshot(body)
    identifiers=[f['id'] for f in snap['facts'] if f['id'].startswith('F:design:')
                 and f['id']!='F:design:structure:arch_height_m'][:count-1]+['F:design:structure:arch_height_m']
    value=advisory()
    value['claims'][0]={'text':'【检验结果】棚体拱高为2.4 m；覆盖、种植和通道配置应结合现场作业协调评估。',
        'basis':'inference','evidence_ids':identifiers,'conditions':['当前是设计参数，实际适宜性依赖现场条件']}
    calls=[]
    def model(request):
        data=json.loads(request['messages'][-1]['content']);calls.append(data['task'])
        if data['task']=='greenhouse_design_inspection':return reply(value)
        assert data['candidate']['claims'][0]['evidence_ids']==identifiers
        return reply(accepted())
    out=runtime.Runner(run_design(body),model).execute()
    assert out['status']=='answered' and out['result']['omitted_claim_count']==0
    assert out['result']['claims'][0]['evidence_ids']==identifiers
    assert len(calls)==2 and out['evaluations']==1


def test_design_citation_schema_is_bounded_and_does_not_change_general_chat():
    value=advisory();value['claims'][0]['evidence_ids']=['F:design:field:'+str(n) for n in range(7)]
    with pytest.raises(ValueError):runtime.parse_candidate(json.dumps(value))
    assert len(runtime.parse_candidate(json.dumps(value),candidate_type=design.candidate_type()).claims[0].evidence_ids)==7
    value['claims'][0]['evidence_ids']=['F:design:field:'+str(n) for n in range(65)]
    with pytest.raises(ValueError):runtime.parse_candidate(json.dumps(value),candidate_type=design.candidate_type())


def test_many_citations_do_not_allow_a_fabricated_reference_or_unsupported_number(body):
    snap=design.snapshot(body);evidence={f['id']:f for f in snap['facts']}
    value=advisory();value['claims'][0]['evidence_ids']=list(evidence)[:8]+['F:design:invented']
    candidate=runtime.parse_candidate(json.dumps(value),candidate_type=design.candidate_type())
    assert '存在无效引用' in runtime.validate_candidate(candidate,evidence)
    value['claims'][0]['evidence_ids']=list(evidence)[:8];value['claims'][0]['text']='【检验结果】棚内温度为999°C。'
    candidate=runtime.parse_candidate(json.dumps(value),candidate_type=design.candidate_type())
    assert runtime.validate_candidate(candidate,evidence)
