import base64
import hashlib
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from test_weather_training import api, wait
from tfield import config as C, weather_runtime as runtime
from tfield.artifact import PipelineArtifact
from tfield.features import add_feature_groups
from tfield.models.idw import AnisoMetric
from tfield.pipeline import FieldPipeline
from api import weather_training as jobs


class FrozenTrend:
    def predict(self, X):
        return np.full(len(X), 25.)


def field_bytes(names=None):
    columns = pd.DataFrame({k: [0.] for k in ('x','y','z','bg_temp','bg_rh','bg_light','hour','frac_day')})
    return PipelineArtifact('test', 'xgboost', C.DEFAULT_FEATURE_GROUPS,
        names or tuple(add_feature_groups(columns).columns), AnisoMetric(1,1,1,2), False, 80, FrozenTrend()).to_bytes()


def completed(client, headers, schema='two'):
    id = str(uuid4())
    assert client.post('/internal/v1/weather-training/jobs/'+id, headers=headers,
                       json={'algorithm':'ridge','external_schema':schema}).status_code == 200
    assert wait(client, headers, id)['state'] == 'done'
    return id


def request(raw=None):
    raw = raw or field_bytes()
    return dict(package_id=str(uuid4()), name='可部署气象模型', model_id=3,
                artifact_base64=base64.b64encode(raw).decode(), artifact_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('schema', ['two','full'])
def test_completed_g_packages_exact_f_and_constructs_a_field_without_retraining(api, monkeypatch, schema):
    client, headers, directory = api
    id = completed(client, headers, schema)
    body = request(); url = '/internal/v1/weather-training/jobs/'+id+'/package'
    monkeypatch.setattr(jobs, 'train', lambda *a, **kw: pytest.fail('Publishing must not train G'))
    monkeypatch.setattr(FieldPipeline, 'fit', lambda *a, **kw: pytest.fail('Publishing must not train F'))
    response = client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    manifest = response.json()
    assert manifest['g_training_job_id'] == id and manifest['model_id'] == 3
    assert manifest['files']['field.bin'] == body['artifact_sha256']
    assert manifest['bounds'] == jobs.get(id)['result']['bounds']
    for key, digest in jobs.get(id)['artifacts'].items():
        assert manifest['files'][key+'.pkl'] == digest
    for n, mode in ((1,'current_only'), (13,'history_1h')):
        frames = [dict(timestamp=t.isoformat(), bg_temp=25., bg_light=150., bg_rh=60. if schema=='full' else None)
                  for t in pd.date_range('2026-07-23T00:00:00Z', periods=n, freq='5min')]
        result = runtime.infer(manifest['package_id'], manifest['package_sha256'], frames)
        assert result['summary']['stage1_mode'] == mode
        assert len(result['summary']['node_temperatures']) == 24
        assert len(result['field']['planes']) == 37 and np.isfinite(result['summary']['mean'])
    jobs.recover()
    assert client.post(url, headers=headers, json=body).json() == manifest
    assert len(list((directory/'packages').glob('*/manifest.json'))) == 1
    assert client.post(url, headers=headers, json=body | {'name':'同编号换名'}).status_code == 409
    assert client.post(url, json=body).status_code == 403


def test_damaged_g_or_incompatible_f_never_becomes_a_package(api):
    client, headers, directory = api
    id = completed(client, headers); url = '/internal/v1/weather-training/jobs/'+id+'/package'
    bad = request(field_bytes(('wrong_feature',)))
    assert client.post(url, headers=headers, json=bad).status_code == 409
    source = directory/'g'/id/'current.pkl'
    source.write_bytes(source.read_bytes()+b'tamper')
    assert client.post(url, headers=headers, json=request()).status_code == 409
    assert not list((directory/'packages').glob('*/manifest.json'))


def test_only_completed_records_and_server_supplied_artifacts_are_accepted(api):
    client, headers, _ = api
    id = completed(client, headers); url = '/internal/v1/weather-training/jobs/'+id+'/package'
    body = request()
    assert client.post(url, headers=headers, json=body | {'path':'external.pkl'}).status_code == 422
    assert client.post(url, headers=headers, json=body | {'artifact_sha256':'0'*64}).status_code == 422
    with jobs.LOCK:
        jobs.STATES[id]['state'] = 'cancelled'
    assert client.post(url, headers=headers, json=body).status_code == 409
