"""Deployment integrity, isolated inference and Java compute boundary tests."""
import pickle
import uuid

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from tfield import config as C
from tfield.artifact import PipelineArtifact
from tfield.features import add_feature_groups
from tfield.models.idw import AnisoMetric
from tfield.pipeline import FieldPipeline
from tfield.weather_chain import WeatherFeatureSpec, WeatherNodeModel
from tfield import weather_runtime as runtime


class Constant:
    def fit(self, X, y):
        self.value = np.asarray(y).mean(axis=0)
        return self

    def predict(self, X):
        return np.tile(self.value, (len(X), 1))


class FrozenTrend:
    def predict(self, X):
        return np.full(len(X), 24.)


@pytest.fixture
def package(tmp_path, monkeypatch):
    monkeypatch.setenv('TFIELD_WEATHER_MODEL_ROOT', str(tmp_path / 'packages'))
    monkeypatch.setenv('TFIELD_WEATHER_RESULT_ROOT', str(tmp_path / 'results'))
    w = pd.DataFrame({'timestamp': pd.date_range('2026-07-23', periods=13, freq='5min'),
                      'bg_temp': np.full(13, 24.), 'bg_light': np.zeros(13), 'bg_rh': np.full(13, 70.)})
    for history, name in [(False, 'current'), (True, 'history')]:
        model = WeatherNodeModel(WeatherFeatureSpec(False, history), Constant()).fit(w, np.full((13, 24), 25.))
        (tmp_path / f'{name}.pkl').write_bytes(pickle.dumps(model))
    names = tuple(add_feature_groups(pd.DataFrame({name: [0] for name in
                  ['x', 'y', 'z', 'bg_temp', 'bg_light', 'bg_rh', 'hour', 'frac_day']})).columns)
    artifact = PipelineArtifact('test', 'xgboost', C.DEFAULT_FEATURE_GROUPS, names,
                                AnisoMetric(1, 1, 1, 2), False, 1, FrozenTrend())
    (tmp_path / 'field.bin').write_bytes(artifact.to_bytes())
    return runtime.package_models(runtime.model_root(), tmp_path / 'current.pkl', tmp_path / 'history.pkl',
                                  tmp_path / 'field.bin', 3, 'two', {'bg_temp': [20, 30]})


def frames(count=1):
    return [{'timestamp': t.isoformat(), 'bg_temp': 24., 'bg_light': 0., 'bg_rh': None}
            for t in pd.date_range('2026-11-04T04:00:00Z', periods=count, freq='5min')]


def test_stateless_frozen_inference_without_measured_indoor_values(package, monkeypatch):
    monkeypatch.setattr(FieldPipeline, 'fit', lambda *a, **k: pytest.fail('Frozen field must not be fitted'))
    result = runtime.infer(package['package_id'], package['package_sha256'], frames())
    assert result['summary']['stage1_mode'] == 'current_only'
    assert result['summary']['source'] == 'virtual_weather_prediction'
    assert result['summary']['humidity_source'] == 'predicted_external'
    assert result['summary']['node_temperatures'] == [25.] * 24
    assert len(result['field']['planes']) == 37
    assert all(not p['measured'] for p in result['field']['planes'])
    assert result['field']['time'] == '2026-11-04T04:00:00+00:00'
    assert runtime.infer(package['package_id'], package['package_sha256'], frames(13))['summary']['stage1_mode'] == 'history_1h'


def test_discontinuous_out_of_range_weather_constructs_without_range_warning(package):
    data = frames(13)
    data.pop(4)
    data[-1]['bg_temp'] = 40.
    result = runtime.infer(package['package_id'], package['package_sha256'], data)
    assert result['summary']['stage1_mode'] == 'current_only'
    assert result['summary']['warnings'] == []


def test_legacy_bounds_are_read_only_from_matching_g_training_artifacts(tmp_path, monkeypatch):
    import json
    job = str(uuid.uuid4())
    monkeypatch.setenv('TFIELD_WEATHER_TRAINING_ROOT', str(tmp_path))
    folder = tmp_path / job
    folder.mkdir()
    state = dict(id=job, state='done', dataset_sha256='dataset', artifacts={'current': 'a', 'history': 'b'},
                 result={'bounds': {'bg_temp': [24., 42.]}})
    path = folder / 'state.json'
    path.write_text(json.dumps(state))
    manifest = dict(bounds={}, g_training_job_id=job, g_dataset_sha256='dataset', files={'current.pkl': 'a', 'history.pkl': 'b'})
    assert runtime.training_bounds(manifest) == ({'bg_temp': [24., 42.]}, 'g_training_record')
    state['artifacts']['current'] = 'changed'
    path.write_text(json.dumps(state))
    assert runtime.training_bounds(manifest) == ({}, 'unavailable')
    assert runtime.training_bounds({'bounds': {'bg_temp': [42., 24.]}}) == ({}, 'unavailable')
    assert runtime.training_bounds({'bounds': {}}) == ({}, 'unavailable')


def test_checksum_and_manifest_pin_reject_changes_before_deserialization(package):
    path = runtime.model_root() / package['package_id'] / 'current.pkl'
    path.write_bytes(path.read_bytes() + b'tamper')
    with pytest.raises(ValueError, match='checksum'):
        runtime.infer(package['package_id'], package['package_sha256'], frames())
    with pytest.raises(ValueError, match='manifest changed'):
        runtime.inspect_package(package['package_id'], 'f' * 64)


def test_paths_and_results_are_isolated(package):
    with pytest.raises(ValueError):
        runtime.inspect_package('../field.bin')
    fid = str(uuid.uuid4())
    runtime.save_result(fid, {'id': fid})
    assert runtime.read_result(fid) == {'id': fid}
    with pytest.raises(FileNotFoundError):
        runtime.read_result(str(uuid.uuid4()))


def saved_weather(package):
    identifier=str(uuid.uuid4())
    result=runtime.infer(package['package_id'],package['package_sha256'],frames())
    runtime.save_result(identifier,result)
    return identifier,result


def test_live_views_use_saved_weather_without_replay_or_fit(package,monkeypatch):
    from api import weather_views,live
    identifier,result=saved_weather(package)
    before=(runtime.result_root()/f'{identifier}.json.gz').read_bytes()
    monkeypatch.setattr(live,'get_live_source',lambda:pytest.fail('Must not read 24-sensor replay'))
    monkeypatch.setattr(FieldPipeline,'fit',lambda *a,**k:pytest.fail('Must not retrain'))
    monkeypatch.setattr(runtime,'infer',lambda *a,**k:pytest.fail('Must not infer on read'))
    section=weather_views.sections(identifier)
    assert section['time']=='2026-11-04T12:00:00+08:00' and section['frame']['time']==section['time']
    assert section['frame']['sensor_temps']==[None]*24
    assert section['frame']['predicted_sensor_temps']==[25.]*24
    assert section['frame']['bg_temp']==24
    assert section['frame']['bg_rh']==70
    assert len(section['sheds'])==3
    for shed in section['sheds']:
        original=next(p for p in result['field']['planes'] if p['y']==shed['y'])
        assert shed['values']==original['values'] and not shed['measured']
    _,volume=weather_views.saved_volume(identifier,y_step=3.)
    assert len(volume['planes'])==7 and all(not p['measured'] for p in volume['planes'])
    point=weather_views.point(identifier,1.,9.,.7)
    assert point['kind']=='value' and point['value']==pytest.approx(25.) and not point['measured_plane']
    assert before==(runtime.result_root()/f'{identifier}.json.gz').read_bytes()


@pytest.mark.parametrize('profile',[{'preset':'export'},{'y_step':.25},
                                    {'y_step':float('nan')},{'y_min':-.5},{'y_step':7.}])
def test_live_view_rejects_changed_calculation_profiles_before_loading(profile,monkeypatch):
    from api import weather_views
    monkeypatch.setattr(runtime,'read_result',lambda *a:pytest.fail('Validate before loading'))
    with pytest.raises(ValueError): weather_views.saved_volume(str(uuid.uuid4()),**profile)

@pytest.mark.parametrize('profile',[{'monotonic':False},{'y_step':.7},{'y_max':19.},{'preset':'experimental_transfer'}])
def test_legacy_view_still_rejects_profiles_outside_its_saved_grid(profile,monkeypatch):
    from api import weather_views
    monkeypatch.setattr(runtime,'read_result',lambda *a:{'summary':{}})
    with pytest.raises(ValueError):weather_views.saved_volume(str(uuid.uuid4()),**profile)


def test_live_point_reference_and_virtual_assistant_snapshot(package,monkeypatch):
    from fastapi import HTTPException
    from api import weather_views
    from api.assistant import field_tools
    identifier,_=saved_weather(package)
    _,volume=weather_views.saved_volume(identifier)
    with pytest.raises(HTTPException) as wrong:
        weather_views.point(identifier,1.,9.,.7,expected_ref='another-observation')
    assert wrong.value.status_code==409
    assert weather_views.point(identifier,1.,9.,.7,expected_ref=volume['field_ref'])['value']==pytest.approx(25.)
    captured={}
    def capture(body):
        captured.update(body)
        return {**body,'snapshot_id':str(uuid.uuid4())}
    monkeypatch.setattr(weather_views.store,'snapshot',capture)
    source={'observed_at':'2026-11-14T00:00:00Z','light_time':'2026-11-14T01:00:00Z'}
    public=weather_views.snapshot(identifier,{'location':{'city_code':'220600'},'weather':{'bg_temp':22.5,'bg_rh':None,'bg_light':55000},'weather_source':source,'light_conversion':{'factor':110}})
    assert public['source']=='virtual_weather_prediction' and 'volume' not in public
    assert public['data_mode']=='external_weather'
    facts={f['id']:f for f in captured['facts']}
    assert facts['F:external:bg_temp']['value']==22.5
    assert facts['F:external:bg_temp']['source_time']==source['observed_at']
    assert 'F:external:bg_rh' not in facts  # Never substitute predicted humidity.
    assert facts['F:external:bg_light']['unit']=='lux'
    assert facts['F:external:bg_light']['source_time']==source['light_time']
    assert facts['F:weather-source']['light_conversion']=={'factor':110}
    assert all(f.get('origin')!='recorded_sensor' for f in public['facts'])
    assert not field_tools.point(captured,{'x':1.,'y':9.,'z':.7})['measured_plane']


def test_weather_view_routes_require_internal_key(package,monkeypatch):
    from api.main import create_app
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','test-internal-secret')
    identifier,_=saved_weather(package)
    client=TestClient(create_app())
    base=f'/internal/v1/weather/results/{identifier}'
    assert client.get(base+'/sections').status_code==403
    assert client.get(base+'/sections',headers={'X-TField-Internal-Key':'test-internal-secret'}).status_code==200
    assert client.get(base+'/volume?y_step=.25',headers={'X-TField-Internal-Key':'test-internal-secret'}).status_code==422


@pytest.mark.parametrize('mode', [None, 'java', 'JAVA'])
def test_java_compute_api_cannot_bypass_gateway(monkeypatch, mode):
    from api.main import create_app
    if mode is None:
        monkeypatch.delenv('TFIELD_MODEL_STORE_MODE', raising=False)
    else:
        monkeypatch.setenv('TFIELD_MODEL_STORE_MODE', mode)
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN', 'test-internal-secret')
    client = TestClient(create_app())
    assert client.get('/api/models').status_code == 403
    assert client.post('/api/field/volume').status_code == 403
    assert client.get('/api/health').status_code == 200
    assert client.get('/internal/v1/weather/info').status_code == 403
    assert client.get('/internal/v1/weather/info', headers={'X-TField-Internal-Key': 'test-internal-secret'}).json()['protocol_version'] == 1
    assert client.get(f'/internal/v1/weather/packages/{uuid.uuid4()}').status_code == 403
    assert client.get(f'/internal/v1/weather/packages/{uuid.uuid4()}',
                      headers={'X-TField-Internal-Key': 'test-internal-secret'}).status_code == 404
