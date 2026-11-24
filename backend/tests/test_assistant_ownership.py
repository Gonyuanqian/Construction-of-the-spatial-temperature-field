"""User-mode assistant history, background jobs and streaming stay private."""
from threading import Event
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.assistant import store, runtime, config
from api.assistant.ownership import OWNER, owner_scope
from api.routes import assistant as routes
from assistant_fixtures import snapshot_body

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','ownership-test-key')
    monkeypatch.setenv('TFIELD_ASSISTANT_STATE_ROOT',str(tmp_path))
    return TestClient(create_app())

def headers(owner=None):
    out={'X-TField-Internal-Key':'ownership-test-key'}
    if owner: out['X-TField-Assistant-Owner']=owner
    return out

def seed(owner,title):
    with owner_scope(owner):
        snapshot=store.snapshot(snapshot_body())
        chat=str(uuid4())
        run,_=store.create_run(str(uuid4()),{'conversation_id':chat,'question':title,'snapshot_id':snapshot['snapshot_id']})
        store.update_run(run['id'],status='answered',result={'claims':[],'citations':[],'snapshot':{}})
        return chat,run['id'],snapshot['snapshot_id']

def test_user_history_does_not_expose_legacy_admin_or_another_user(env):
    first,second=str(uuid4()),str(uuid4())
    legacy=seed(None,'管理员既有记录'); a=seed(first,'第一用户的问题'); b=seed(second,'第二用户的问题')
    for owner,expected in [(None,legacy),(first,a),(second,b)]:
        response=env.get('/internal/v1/assistant/conversations',headers=headers(owner))
        assert response.status_code==200 and [c['id'] for c in response.json()]==[expected[0]]
    paths=[f'/conversations/{a[0]}',f'/conversations/{a[0]}/events',f'/conversations/{a[0]}/stream',
           f'/runs/{a[1]}',f'/snapshots/{a[2]}',f'/snapshots/{a[2]}/volume',f'/snapshots/{a[2]}/point?x=1&y=2&z=.5']
    for path in paths: assert env.get('/internal/v1/assistant'+path,headers=headers(second)).status_code==404
    assert env.post(f'/internal/v1/assistant/runs/{a[1]}/cancel',headers=headers(second)).status_code==404
    assert OWNER.get() is None

def test_internal_key_and_canonical_owner_are_required(env):
    assert env.get('/internal/v1/assistant/info',headers={'X-TField-Assistant-Owner':str(uuid4())}).status_code==403
    assert env.get('/internal/v1/assistant/info',headers=headers('../another-user')).status_code==422

def test_background_worker_retains_owner_and_request_keys_are_private(env,monkeypatch):
    monkeypatch.setattr(config,'api_key',lambda:'test-key-not-sent')
    done=Event(); seen=[]
    def work(run):
        try:
            seen.append(OWNER.get())
            store.update_run(run['id'],status='answered',result={'claims':[],'citations':[],'snapshot':{}})
        finally: runtime.SLOTS.release(); done.set()
    monkeypatch.setattr(runtime,'work',work)
    key=str(uuid4()); identifiers=[]
    for owner in [str(uuid4()),str(uuid4())]:
        done.clear()
        response=env.post('/internal/v1/assistant/runs',json={'request_key':key,'question':'解释空气温度'},headers=headers(owner))
        assert response.status_code==200 and done.wait(10)
        identifier=response.json()['id']; identifiers.append(identifier)
        assert env.get('/internal/v1/assistant/runs/'+identifier,headers=headers(owner)).json()['status']=='answered'
        assert seen[-1]==owner
    assert identifiers[0]!=identifiers[1]

def test_stream_uses_the_same_owner_after_response_starts(env,monkeypatch):
    owner=str(uuid4()); chat,_,_=seed(owner,'私有 SSE 记录')
    monkeypatch.setattr(routes,'STREAM_SECONDS',.03)
    response=env.get(f'/internal/v1/assistant/conversations/{chat}/stream',headers=headers(owner))
    assert response.status_code==200 and 'event: session' in response.text

def test_weather_snapshot_is_saved_in_request_owner_namespace(env,monkeypatch):
    from api import weather_views
    from api.assistant import field_tools
    monkeypatch.setattr(weather_views,'snapshot',lambda *args:field_tools.public_snapshot(store.snapshot(snapshot_body())))
    owner=str(uuid4()); other=str(uuid4())
    response=env.post(f'/internal/v1/weather/results/{uuid4()}/snapshot',headers=headers(owner),json={})
    assert response.status_code==200
    sid=response.json()['snapshot_id']
    assert env.get('/internal/v1/assistant/snapshots/'+sid,headers=headers(owner)).status_code==200
    assert env.get('/internal/v1/assistant/snapshots/'+sid,headers=headers(other)).status_code==404
