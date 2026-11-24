import base64
import hashlib
import pickle
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tfield import config as C
from tfield.weather_training import arrays, causal_features, describe, train
from tfield.weather_chain import WeatherFeatureSpec
from api import weather_training as jobs
from api.main import create_app


def sample(n=100):
    t = np.arange(n)
    wide = pd.DataFrame({C.COL_TIMESTAMP: pd.date_range('2026-07-23', periods=n, freq='5min'),
        C.BG_TEMP: 25 + np.sin(t/10), C.BG_LIGHT: np.maximum(0, 100+t*2), C.BG_RH: 60 + np.cos(t/8)})
    for i, (shed, point) in enumerate((s,p) for s in C.SHED_ORDER for p in C.SENSOR_LAYOUT):
        wide[f'{shed}_{point}_{C.VAR_TEMP}'] = wide[C.BG_TEMP] + i*.08 + np.sin(t/11)*.2
    return SimpleNamespace(wide=wide)


@pytest.mark.parametrize('schema', ['two', 'full'])
@pytest.mark.parametrize('algorithm', ['ridge', 'extra_trees'])
def test_trains_two_independent_deployable_variants(schema, algorithm):
    ds = sample()
    result, models = train(ds, dict(external_schema=schema, algorithm=algorithm, n_estimators=16))
    assert result['split']['train_frames'] == 80
    assert result['split']['train_end'] < result['split']['validation_start']
    assert len(result['variants']) == 2 and all(len(v['per_node']) == 24 for v in result['variants'])
    weather, _, _ = arrays(ds)
    for name, model in models.items():
        restored = pickle.loads(pickle.dumps(model))
        nodes, rh = restored.predict_with_humidity(weather.tail(13))
        assert nodes.shape == (13,24) and rh.shape == (13,)
        assert model.spec.history == (name == 'history')
        assert all('p1_' not in feature for feature in model.feature_names)


def test_holdout_indoor_values_and_humidity_labels_never_change_two_input_fit():
    ds = sample()
    first, m1 = train(ds, dict(external_schema='two', algorithm='ridge'))
    changed = sample()
    _, _, columns = arrays(changed)
    changed.wide.loc[80:, columns] += 1000
    changed.wide.loc[80:, C.BG_RH] = 2
    second, m2 = train(changed, dict(external_schema='two', algorithm='ridge'))
    w, _, _ = arrays(ds)
    for key in m1:
        np.testing.assert_array_equal(m1[key].predict(w), m2[key].predict(w))
    assert second['variants'][0]['validation']['mae'] > first['variants'][0]['validation']['mae'] + 900


def test_history_is_causal_and_resets_at_time_gaps():
    weather, _, _ = arrays(sample())
    spec = WeatherFeatureSpec(True, True)
    first = causal_features(weather, spec)
    weather.loc[80:, 'bg_temp'] += 50
    second = causal_features(weather, spec)
    pd.testing.assert_frame_equal(first.iloc[:80], second.iloc[:80])
    weather.loc[50:, 'timestamp'] += pd.Timedelta(hours=4)
    gap = causal_features(weather, spec)
    assert gap.iloc[50]['bg_temp_lag12'] == weather.iloc[50].bg_temp


@pytest.mark.parametrize('column,value', [(C.BG_LIGHT, -1), (C.BG_RH, 101), (C.BG_TEMP, np.nan)])
def test_invalid_weather_does_not_silently_drop_rows(column, value):
    ds = sample(); ds.wide.loc[5, column] = value
    assert not describe(ds)['ready']
    with pytest.raises(ValueError): train(ds, {})


@pytest.fixture
def api(tmp_path, monkeypatch):
    for variable, child in [('TFIELD_WEATHER_TRAINING_ROOT','g'), ('TFIELD_TRAINING_ROOT','f'), ('TFIELD_LIVE_SESSION_ROOT','live'), ('TFIELD_DATASET_STORAGE_ROOT','datasets'), ('TFIELD_WEATHER_MODEL_ROOT','packages'), ('TFIELD_WEATHER_RESULT_ROOT','results')]:
        monkeypatch.setenv(variable, str(tmp_path/child))
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','g-test-key')
    dataset = str(uuid4()); path = tmp_path/'datasets'/dataset/'source.xlsx'
    path.parent.mkdir(parents=True); path.write_bytes(b'isolated-registered-dataset')
    monkeypatch.setattr(jobs, 'load_dataset', lambda _: sample())
    headers = {'X-TField-Internal-Key':'g-test-key', 'X-TField-Dataset-Id':dataset,
        'X-TField-Dataset-Signature':'a'*16, 'X-TField-Dataset-Hash':hashlib.sha256(path.read_bytes()).hexdigest(),
        'X-TField-Dataset-Name':base64.urlsafe_b64encode('训练.xlsx'.encode()).decode()}
    with TestClient(create_app()) as client:
        yield client, headers, tmp_path


def wait(client, headers, id):
    for _ in range(200):
        response = client.get('/internal/v1/weather-training/jobs/'+id, headers=headers)
        assert response.status_code == 200, response.text
        value = response.json()
        if value['state'] != 'running': return value
        time.sleep(.02)
    raise AssertionError('G job did not finish')


def test_api_requires_internal_key_and_registered_context(api):
    client, headers, _ = api
    assert client.get('/internal/v1/weather-training').status_code == 403
    assert client.get('/internal/v1/weather-training',headers={'X-TField-Internal-Key':'g-test-key'}).status_code == 409
    r = client.get('/internal/v1/weather-training', headers=headers)
    assert r.status_code == 200 and r.json()['dataset']['ready']
    bad = headers | {'X-TField-Dataset-Hash':'b'*64}
    assert client.get('/internal/v1/weather-training',headers=bad).status_code == 409


def test_job_idempotence_artifacts_and_restart_recovery(api):
    client, headers, directory = api
    id = str(uuid4()); url = '/internal/v1/weather-training/jobs/'+id
    cfg = dict(algorithm='ridge', name='独立 G 模型')
    assert client.post(url, headers=headers, json=cfg).status_code == 200
    assert client.post(url, headers=headers, json=cfg).json()['id'] == id
    assert client.post(url, headers=headers, json=cfg | {'name':'不同配置'}).status_code == 409
    result = wait(client, headers, id)
    assert result['state'] == 'done' and set(result['artifacts']) == {'current','history'}
    for key, digest in result['artifacts'].items():
        raw = (directory/'g'/id/(key+'.pkl')).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
    jobs.recover()
    assert client.get(url,headers=headers).json()['result'] == result['result']
    assert client.get('/internal/v1/weather-training',headers=headers).json()['jobs'][0]['id'] == id
    for invalid in ({'path':'arbitrary.pkl'}, {'n_estimators':10000}):
        assert client.post('/internal/v1/weather-training/jobs/'+str(uuid4()),headers=headers,json=invalid).status_code == 422


def test_running_job_conflict_and_cancel_are_persisted(api, monkeypatch):
    client, headers, _ = api
    entered, proceed = threading.Event(), threading.Event()
    original = jobs.train
    def delayed(ds, options, checkpoint):
        entered.set(); proceed.wait(5); checkpoint('继续训练'); return original(ds,options,checkpoint)
    monkeypatch.setattr(jobs,'train',delayed)
    id = str(uuid4()); url='/internal/v1/weather-training/jobs/'+id
    try:
        assert client.post(url,headers=headers,json={'algorithm':'ridge'}).status_code == 200
        assert entered.wait(2)
        assert client.post('/internal/v1/weather-training/jobs/'+str(uuid4()),headers=headers,json={}).status_code == 409
        assert client.post(url+'/cancel',headers=headers).json()['cancel_requested']
    finally: proceed.set()
    assert wait(client,headers,id)['state'] == 'cancelled'
    jobs.recover()
    assert client.get(url,headers=headers).json()['state'] == 'cancelled'


def test_corrected_training_archives_all_three_artifacts_and_blocks_legacy_publication(api):
    client,headers,directory=api
    id=str(uuid4());url='/internal/v1/weather-training/jobs/'+id
    cfg=dict(spatial_protocol='independent_house_section_v2',algorithm='ridge',n_estimators=16)
    assert client.post(url,headers=headers,json=cfg).status_code==200
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        value=client.get(url,headers=headers).json()
        if value['state']!='running':break
        time.sleep(.05)
    assert value['state']=='done',value
    assert set(value['artifacts'])=={'current','history','field'}
    for key,digest in value['artifacts'].items():
        raw=(directory/'g'/id/(key+'.pkl')).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==digest
    assert pickle.loads((directory/'g'/id/'current.pkl').read_bytes()).n_nodes==8
    assert value['result']['geometry']['length_m']==6
    body=dict(package_id=str(uuid4()),name='incompatible',model_id=1,
        artifact_base64=base64.b64encode(b'old-field').decode(),artifact_sha256=hashlib.sha256(b'old-field').hexdigest())
    response=client.post(url+'/package',headers=headers,json=body)
    assert response.status_code==409 and '单棚 8 点' in response.json()['detail']
    jobs.recover()
    assert client.get(url,headers=headers).json()['result']==value['result']


def test_old_job_without_protocol_remains_idempotent(api):
    client,headers,_=api;id=str(uuid4());url='/internal/v1/weather-training/jobs/'+id
    cfg=dict(algorithm='ridge')
    client.post(url,headers=headers,json=cfg);value=wait(client,headers,id)
    assert value['state']=='done'
    jobs.STATES[id]['options'].pop('spatial_protocol')
    assert client.post(url,headers=headers,json=cfg).status_code==200
