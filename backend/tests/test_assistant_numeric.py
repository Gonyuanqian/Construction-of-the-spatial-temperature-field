"""Display precision is not a new measured value; unsafe numbers remain blocked."""
import json
from uuid import uuid4

import pytest
from api.assistant import runtime,store

def candidate(text,ids=None):
    return runtime.Candidate(claims=[{'text':text,'evidence_ids':ids or ['F:min','F:max']}],missing_conditions=[])

FACTS={'F:min':{'value':24.585685263888884,'unit':'°C'},'F:max':{'value':24.871185489057222,'unit':'°C'}}

@pytest.mark.parametrize('text',[
    '模型估算温度约24.6至24.9°C。','模型估算温度24.59-24.87°C。',
    '模型估算温度24.59–24.87°C。','模型估算温度24.59～24.87°C。',
    '1、估算最低温约24.6°C，最高温约24.9°C。',
])
def test_saved_model_statistics_allow_faithful_display_rounding_and_range_separators(text):
    assert runtime.validate_candidate(candidate(text),FACTS)==[]

@pytest.mark.parametrize('text,value',[
    ('估算温度-2.5°C。',-2.46),('估算温度−2.5°C。',-2.46),
    ('估算温度0.2°C。',.15),('估算照度42,800 lux。',42800),
    ('值为0.001。',.001),('值为1e-3。',.001),
])
def test_signs_utf8_units_grouped_digits_and_scientific_notation(text,value):
    assert not runtime.validate_candidate(candidate(text,['F:value']),{'F:value':{'value':value}})

@pytest.mark.parametrize('text',['最低温为24.5°C。','最高温为24.8°C。','应设为25°C。','温度为24.586°C。'])
def test_wrong_rounding_invented_thresholds_and_extra_precision_are_not_licensed(text):
    issues=runtime.validate_candidate(candidate(text),FACTS)
    assert issues and '第1段' in issues[0] and 'evidence_ids' in issues[0]

def test_negative_ranges_keep_both_signs_and_literature_cannot_supply_rounded_thresholds():
    assert runtime.numeric_tokens('温度-5--2°C，另一个区间-5-2°C。')==['-5','-2','-5','2']
    source={'W:one':{'text':'实验温度为24.71°C。','original_verified':True,'value':24.71}}
    assert runtime.validate_candidate(candidate('实验温度约24.7°C。',['W:one']),source)
    assert not runtime.validate_candidate(candidate('实验温度为24.71°C。',['W:one']),source)

def test_hash_metadata_that_resembles_scientific_notation_does_not_break_review():
    source={'F:model':{'text':'可信模型配置','prototype_reference':'1e'+'9'*90+'abcdef'}}
    assert not runtime.validate_candidate(candidate('模型配置已固定。',['F:model']),source)
    assert runtime.validate_candidate(candidate('温度为1e'+ '9'*90 +'°C。',['F:model']),source)

@pytest.fixture
def run(tmp_path,monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    return store.create_run(str(uuid4()),{'question':'请结合当前环境给人参出苗展叶期的农事建议。','crop':'人参','stage':'出苗展叶期','web_search_enabled':False})[0]

def reply(value):return {'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(value)}}]}

def test_conservative_recovery_reviews_safe_parts_and_keeps_snapshot_and_limitations(run):
    seen=[]
    def model(body):
        seen.append(body)
        if len(seen)==1:
            return reply({'claims':[
                {'text':'应设置999°C。','basis':'general_knowledge','evidence_ids':[]},
                {'text':'管理建议：先核对棚内实测环境，再结合栽培条件调整管理。','basis':'inference','conditions':['参龄与土壤墒情尚待确认'],'evidence_ids':[]}],
                'missing_conditions':['参龄与土壤墒情']})
        data=json.loads(body['messages'][1]['content'])
        assert len(data['candidate']['claims'])==1 and '999' not in json.dumps(data['candidate'])
        assert data['snapshot']['partial_answer'] is True
        return reply({'semantic_verdict':'pass','checks':[{'check':c,'verdict':'pass'} for c in runtime.CHECKS]})
    runner=runtime.Runner(run,model)
    runner.snapshot={'snapshot_id':'frozen-weather','source_time':'2026-11-14','data_mode':'external_weather','volume':{'private':'grid'}}
    runner.resolved={'route':{'mode':'mixed'}}
    out=runner.failure('连续核验未通过','review_stalled')
    assert out['status']=='partial' and len(seen)==2 and len(out['result']['claims'])==1
    assert out['result']['missing_conditions']==['参龄与土壤墒情']
    assert out['result']['snapshot']['snapshot_id']=='frozen-weather' and 'volume' not in out['result']['snapshot']
    assert out['diagnostic']['recovery']=={'status':'published','omitted_claim_count':1}
    assert '999°C' not in store.packed(store.get_run(run['id']))

def test_safe_part_still_requires_independent_semantic_review(run):
    def model(body):
        if '现有资料给出简短保守回答' in body['messages'][0]['content']:
            return reply({'claims':[{'text':'管理建议：核对棚内实际环境。','basis':'general_knowledge','evidence_ids':[]}],'missing_conditions':[]})
        return reply({'semantic_verdict':'fail','checks':[{'check':c,'verdict':'fail','reason':'不满足适用条件'} for c in runtime.CHECKS]})
    runner=runtime.Runner(run,model);runner.resolved={'route':{'mode':'mixed'}}
    out=runner.failure('连续核验未通过','review_stalled')
    assert out['status']=='failed' and not out.get('result')
    assert out['diagnostic']['recovery']['phase']=='review'
    assert run['question'] not in out['detail']

def test_full_weather_advice_turn_can_publish_rounded_facts_after_two_reviews(tmp_path,monkeypatch):
    monkeypatch.setattr(store.paths,'PROJECT',tmp_path)
    snapshot=store.snapshot({'session_id':str(uuid4()),'frame_index':0,'source_time':'2026-11-14T20:13:15+08:00',
        'data_mode':'external_weather','facts':[dict(id=key,**value) for key,value in FACTS.items()]})
    run=store.create_run(str(uuid4()),{'question':'请结合当前环境判断人参出苗展叶期的适宜条件并给出农事建议。',
        'crop':'人参','stage':'出苗展叶期','snapshot_id':snapshot['snapshot_id'],'web_search_enabled':False})[0]
    reviews=[]
    def model(body):
        if 'understand_request' in body['messages'][-1].get('content',''):
            return reply({'task_kind':'mixed','user_goal':'结合人参阶段给有条件的环境建议','answer_outline':[],'information_needs':[]})
        if 'tools' in body:
            value={'claims':[{'text':'估算温度约24.6-24.9°C，管理前应核对棚内实际环境。','evidence_ids':['F:min','F:max']}],
                'missing_conditions':['参龄、栽培方式和土壤墒情']}
            return {'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':str(uuid4()),'type':'function','function':{'name':'finish_answer','arguments':json.dumps(value)}}]}}]}
        reviews.append(json.loads(body['messages'][1]['content']))
        return reply({'semantic_verdict':'pass','checks':[{'check':c,'verdict':'pass'} for c in runtime.CHECKS]})
    output=runtime.Runner(run,model).execute()
    assert output['status']=='answered' and len(reviews)==2
    assert output['result']['snapshot']['data_mode']=='external_weather'
    assert '24.6-24.9' in output['result']['claims'][0]['text']
    assert {fact['id'] for fact in output['result']['citations']}=={'F:min','F:max'}
