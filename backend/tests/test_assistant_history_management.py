from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.assistant import store
from api.assistant.ownership import owner_scope
from api.dataset_context import DatasetContextError


@pytest.fixture
def history(tmp_path,monkeypatch):
    monkeypatch.setenv('TFIELD_ASSISTANT_STATE_ROOT',str(tmp_path))
    chat=str(uuid4())
    run,_=store.create_run(str(uuid4()),{'conversation_id':chat,'question':'原始标题'})
    store.update_run(run['id'],status='answered',result={'claims':[]})
    return chat,run


def test_rename_survives_followups_and_invalid_titles(history):
    chat,run=history
    assert store.rename_conversation(chat,'  非切面温度讨论  ')['title']=='非切面温度讨论'
    store.create_run(str(uuid4()),{'conversation_id':chat,'parent_run_id':run['id'],'question':'追问'})
    assert store.get_conversation(chat)['title']=='非切面温度讨论'
    for title in ('   ','x'*81):
        with pytest.raises(DatasetContextError):store.rename_conversation(chat,title)


def test_delete_hides_all_entrypoints_and_prevents_resurrection(history):
    chat,run=history
    assert store.delete_conversation(chat)['deleted']
    assert store.delete_conversation(chat)['deleted']
    assert not store.list_conversations()
    for read in (lambda:store.get_conversation(chat),lambda:store.get_run(run['id']),
                 lambda:store.conversation_events(chat),lambda:store.rename_conversation(chat,'新的名字'),
                 lambda:store.create_run(str(uuid4()),{'conversation_id':chat,'question':'重新创建'})):
        with pytest.raises(DatasetContextError) as error:read()
        assert error.value.status==404


def test_running_conversation_cannot_be_deleted(history):
    chat,run=history
    store.create_run(str(uuid4()),{'conversation_id':chat,'parent_run_id':run['id'],'question':'继续'})
    with pytest.raises(DatasetContextError) as error:store.delete_conversation(chat)
    assert error.value.status==409
    assert store.get_conversation(chat)['title']=='原始标题'


def test_management_http_owner_isolation(history,monkeypatch):
    chat,_=history
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','history-test')
    own=str(uuid4()); other=str(uuid4())
    with owner_scope(own):
        run,_=store.create_run(str(uuid4()),{'conversation_id':chat,'question':'用户私有标题'})
        store.update_run(run['id'],status='answered')
    headers={'X-TField-Internal-Key':'history-test','X-TField-Assistant-Owner':own}
    with TestClient(create_app()) as client:
        path=f'/internal/v1/assistant/conversations/{chat}'
        assert client.post(path+'/rename',json={'title':'更名'},headers=headers).status_code==200
        assert client.post(path+'/delete',headers={**headers,'X-TField-Assistant-Owner':other}).status_code==404
        assert client.post(path+'/rename',json={'title':'恶意覆盖'},headers={**headers,'X-TField-Assistant-Owner':other}).status_code==404
        assert client.post(path+'/delete',headers=headers).status_code==200
        assert client.get(path,headers=headers).status_code==404
        assert client.post(path+'/rename',json={'title':'未登录'}).status_code==403
    assert store.get_conversation(chat)['title']=='原始标题'
