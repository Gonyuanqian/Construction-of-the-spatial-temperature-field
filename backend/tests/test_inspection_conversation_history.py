"""Inspection tasks stay available without crowding the user's chat list."""
import json
from uuid import uuid4
import pytest
from api.assistant import store,design_inspection
from api.assistant.ownership import owner_scope
from api.dataset_context import DatasetContextError


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('TFIELD_ASSISTANT_STATE_ROOT',str(tmp_path))


def inspection():
    snapshot=store.snapshot({'data_mode':'greenhouse_design','inspection_id':str(uuid4()),'facts':[]})
    request={'conversation_id':str(uuid4()),'snapshot_id':snapshot['snapshot_id'],'question':design_inspection.QUESTION}
    key=str(uuid4());run=store.create_run(key,request)[0]
    return run,key,request


@pytest.mark.parametrize('status',['queued','running','answered','partial','failed','cancelled','interrupted'])
def test_single_inspection_is_hidden_in_every_state_without_removing_results(isolated,status):
    run,_,_=inspection()
    store.update_run(run['id'],status=status,result={'claims':[{'text':'保存的检验结果','evidence_ids':[]}]})
    assert store.list_conversations()==[]
    assert store.get_conversation(run['conversation_id'])['runs'][0]['result']['claims'][0]['text']=='保存的检验结果'
    assert store.get_run(run['id'])['conversation_origin']=='greenhouse_design_inspection'


def test_first_followup_promotes_once_with_meaningful_title_and_preserves_root(isolated):
    root,key,request=inspection();store.update_run(root['id'],status='answered')
    followup={'conversation_id':root['conversation_id'],'parent_run_id':root['id'],'question':'通道布局该怎么调整？'}
    followup_key=str(uuid4());child=store.create_run(followup_key,followup)[0]
    items=store.list_conversations()
    assert len(items)==1 and items[0]['title']==followup['question'] and items[0]['head_run_id']==child['id']
    assert store.create_run(followup_key,followup)[1] is False
    assert store.create_run(key,request)[1] is False
    assert len(store.list_conversations())==1
    assert len(store.get_conversation(root['conversation_id'])['runs'])==2


def test_existing_single_inspection_without_origin_is_inferred_without_deletion(isolated):
    root,_,_=inspection();store.update_run(root['id'],status='failed')
    with store.connect() as db:
        value=json.loads(db.execute('SELECT body FROM runs WHERE id=?',(root['id'],)).fetchone()[0])
        value.pop('conversation_origin')
        db.execute('UPDATE runs SET body=? WHERE id=?',(store.packed(value),root['id']))
    assert not store.list_conversations()
    assert store.get_conversation(root['conversation_id'])['runs'][0]['conversation_origin']=='greenhouse_design_inspection'


def test_inspections_are_filtered_before_visible_list_limit(isolated):
    normal=store.create_run(str(uuid4()),{'conversation_id':str(uuid4()),'question':'正常对话'})[0]
    for _ in range(102):inspection()
    assert [c['id'] for c in store.list_conversations()]==[normal['conversation_id']]


def test_manual_design_question_and_other_entrypoints_remain_visible(isolated):
    snapshot=store.snapshot({'data_mode':'greenhouse_design','inspection_id':str(uuid4()),'facts':[]})
    for question in ('我想讨论这个棚的通道布局。','普通农业问题'):
        store.create_run(str(uuid4()),{'conversation_id':str(uuid4()),'snapshot_id':snapshot['snapshot_id'],'question':question})
    weather=store.snapshot({'data_mode':'external_weather','facts':[]})
    store.create_run(str(uuid4()),{'conversation_id':str(uuid4()),'snapshot_id':weather['snapshot_id'],'question':'农事建议'})
    assert len(store.list_conversations())==3


def test_hidden_inspection_and_followup_stay_in_the_same_owner_namespace(isolated):
    owner,other=str(uuid4()),str(uuid4())
    with owner_scope(owner):
        root,_,_=inspection();store.update_run(root['id'],status='answered')
    with owner_scope(other):
        assert not store.list_conversations()
        with pytest.raises(DatasetContextError):store.get_conversation(root['conversation_id'])
    with owner_scope(owner):
        store.create_run(str(uuid4()),{'conversation_id':root['conversation_id'],'parent_run_id':root['id'],'question':'继续解释'})
        assert len(store.list_conversations())==1
