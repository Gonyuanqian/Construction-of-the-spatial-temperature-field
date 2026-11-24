import hashlib
import json
import pickle
from uuid import uuid4
import numpy as np
import pandas as pd
import pytest
from tfield import prototype_runtime as runtime,weather_runtime
from tfield.independent_training import GEOMETRY,PROTOCOL,SectionFieldModel
from tfield.models.idw import AnisoMetric
from tfield.weather_chain import WeatherNodeModel,WeatherFeatureSpec,weather_features
from api import weather_views

class NodeEstimator:
    def predict(self,X):return X.bg_temp.to_numpy()[:,None]+np.arange(8)[None,:]*.1
class FieldEstimator:
    def predict(self,X):return X.bg_temp.to_numpy()+X.u.to_numpy()+X.w.to_numpy()

class DeltaNodeEstimator:
    def predict(self,X):return np.tile(1+np.arange(8)*.1,(len(X),1))

@pytest.fixture
def configured(tmp_path,monkeypatch):
    root=tmp_path/'models';root.mkdir()
    weather=pd.DataFrame([dict(timestamp='2026-07-26T17:00:00+08:00',bg_temp=25,bg_rh=60,bg_light=100)])
    models={'current':WeatherNodeModel(WeatherFeatureSpec(True,False),NodeEstimator(),tuple(weather_features(weather,WeatherFeatureSpec(True,False)).columns),8),
        'history':WeatherNodeModel(WeatherFeatureSpec(True,True),NodeEstimator(),('bg_temp',),8),
        'field':SectionFieldModel(FieldEstimator(),AnisoMetric(lx=.5,lz=.2),GEOMETRY.copy())}
    hashes={}
    for key,model in models.items():
        raw=pickle.dumps(model);(root/f'{key}.pkl').write_bytes(raw);hashes[f'{key}.pkl']=hashlib.sha256(raw).hexdigest()
    (root/'model-manifest.json').write_text(json.dumps(dict(protocol=PROTOCOL,geometry=GEOMETRY,files=hashes)))
    (root/'report.json').write_text(json.dumps(dict(spatial_protocol=PROTOCOL,options={'name':'test prototype'},bounds={'bg_temp':[20,30]})))
    monkeypatch.setenv('TFIELD_PROTOTYPE_MODEL_DIR',str(root))
    monkeypatch.setenv('TFIELD_WEATHER_RESULT_ROOT',str(tmp_path/'results'))
    return root,weather

def test_prototype_is_explicitly_server_configured(monkeypatch):
    monkeypatch.delenv('TFIELD_PROTOTYPE_MODEL_DIR',raising=False)
    assert not runtime.info()['ready']

def test_delta_g_restores_temperatures_once_before_f_and_saved_views(configured):
    from tfield.independent_training import local_positions
    root,weather=configured
    old_reference=runtime.info()['reference_id']
    model=pickle.loads((root/'current.pkl').read_bytes())
    model.estimator=DeltaNodeEstimator();model.prediction_target='delta'
    raw=pickle.dumps(model);(root/'current.pkl').write_bytes(raw)
    manifest=json.loads((root/'model-manifest.json').read_text())
    manifest['files']['current.pkl']=hashlib.sha256(raw).hexdigest()
    (root/'model-manifest.json').write_text(json.dumps(manifest))
    info=runtime.info()
    assert info['prediction_target']=='delta' and info['reference_id']!=old_reference
    dims=dict(length_m=6,width_m=2.1,height_m=1.3017)
    results=[]
    for outside in (-5.,35.):
        inputs=weather.assign(bg_temp=outside)
        result=runtime.infer(inputs.to_dict('records'),dims,info['reference_id'])
        expected=outside+1+np.arange(8)*.1
        np.testing.assert_allclose(result['summary']['node_temperatures'],expected)
        assert result['summary']['prediction_target']=='delta'
        assert result['summary']['warnings']==[]
        field=pickle.loads((root/'field.pkl').read_bytes())
        np.testing.assert_allclose(field.predict(inputs,expected[None,:],target_positions=local_positions())[0],expected)
        frame_id=str(uuid4());weather_runtime.save_result(frame_id,result)
        _,volume=weather_views.saved_volume(frame_id)
        assert volume['provenance']['prediction_target']=='delta'
        assert volume['mean']==pytest.approx(result['field']['mean'])
        results.append(result)
    assert results[1]['summary']['mean']-results[0]['summary']['mean']==pytest.approx(40.)

def test_inference_uses_frozen_eight_nodes_and_dimensions(configured):
    root,weather=configured;info=runtime.info();assert info['ready']
    dims=dict(length_m=7.2,width_m=3.,height_m=1.8)
    result=runtime.infer(weather.to_dict('records'),dims,info['reference_id'])
    assert result['summary']['dimensions']==dims and result['summary']['prototype']
    assert result['summary']['model_id'] is None
    assert len(result['summary']['node_temperatures'])==8
    assert result['field']['y_max']==7.2 and result['field']['x_max']==3
    id=str(uuid4());weather_runtime.save_result(id,result)
    _,view=weather_views.saved_volume(id,y_step=3)
    assert [p['y'] for p in view['planes']]==[0,3,6,7.2]
    assert [p['z'] for p in view['height_profile']]==view['z']
    assert view['height_profile'][0]['mean']==pytest.approx(np.mean(view['planes'][0]['values'][0]))
    assert view['height_profile'][-1]['mean'] is None
    upper=[p for p in view['height_profile'] if p['z']>view['max_measured_z'] and p['mean'] is not None]
    assert upper, 'Existing upper-band predictions must be included in the height chart'
    blocked={(ix,iz) for ix,iz in view['stripes']}
    iz=view['z'].index(upper[0]['z'])
    predicted=[v for ix,v in enumerate(view['planes'][0]['values'][iz]) if v is not None]
    assert predicted and all((ix,iz) in blocked for ix,v in enumerate(view['planes'][0]['values'][iz]) if v is not None)
    assert upper[0]['mean']==pytest.approx(np.mean(predicted))
    assert not view['monotonic'] and view['transfer']['accuracy_validated'] is False
    sections=weather_views.sections(id)
    assert len(sections['frame']['predicted_sensor_temps'])==8
    assert sections['frame']['sensor_temps']==[None]*8
    point=weather_views.point(id,1.5,2.66,.6,y_step=3,expected_ref=view['field_ref'])
    assert point['kind']=='value' and np.isfinite(point['value'])
    with pytest.raises(Exception) as error:weather_views.point(id,1,2,.4,expected_ref='old-reference')
    assert error.value.status_code==409
    # Saved geometry stays usable if the active reference is replaced or removed.
    (root/'current.pkl').write_bytes(b'changed')
    assert not runtime.info()['ready']
    assert weather_views.saved_volume(id)[1]['x_max']==3

@pytest.mark.parametrize('bad',[{'length_m':1},{'length_m':201,'width_m':3,'height_m':2},{'length_m':6,'width_m':3,'height_m':False},{'length_m':6,'width_m':float('nan'),'height_m':2}])
def test_bad_dimensions_rejected(bad):
    with pytest.raises(ValueError):runtime.dimensions(bad)

def test_reference_change_and_future_invalid_inputs_do_not_create_results(configured):
    _,weather=configured;info=runtime.info()
    with pytest.raises(ValueError,match='已变化'):runtime.infer(weather.to_dict('records'),dict(length_m=6,width_m=2.1,height_m=1.3017),'0'*64)
    with pytest.raises(ValueError):runtime.infer([weather.iloc[0].to_dict()]*2,dict(length_m=6,width_m=2.1,height_m=1.3017),info['reference_id'])

@pytest.mark.parametrize('length,width,height,y',[(6.,2.1,1.3017,6.),(7.2,3.,1.8,7.2),(30.,3.,2.,29.)])
def test_canvas_profile_can_be_echoed_to_point_query(configured,length,width,height,y):
    _,weather=configured
    result=runtime.infer(weather.to_dict('records'),dict(length_m=length,width_m=width,height_m=height),runtime.info()['reference_id'])
    id=str(uuid4());weather_runtime.save_result(id,result)
    _,view=weather_views.saved_volume(id)
    profile={key:view[key] for key in ('preset','monotonic','y_step','y_min','y_max')}
    # VolumeView.pointUrl sends the displayed profile, not the endpoint defaults.
    answer=weather_views.point(id,width/2,y,height*.3,**profile,expected_ref=view['field_ref'])
    assert answer['kind']=='value' and answer['field_ref']==view['field_ref']
    assert view['preset']=='standard'
    # Already-open pages may still send the previous prototype preset.
    legacy=weather_views.point(id,width/2,y,height*.3,**{**profile,'preset':'experimental_transfer'},expected_ref=view['field_ref'])
    assert legacy['value']==answer['value']

def test_private_http_routes(configured,monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from api.main import create_app
    for key,name in [('TFIELD_TRAINING_ROOT','train'),('TFIELD_WEATHER_TRAINING_ROOT','g'),('TFIELD_LIVE_SESSION_ROOT','live'),('TFIELD_ASSISTANT_STATE_ROOT','assistant')]:monkeypatch.setenv(key,str(tmp_path/name))
    monkeypatch.setenv('TFIELD_INTERNAL_TOKEN','prototype-test-key')
    headers={'X-TField-Internal-Key':'prototype-test-key'}
    _,weather=configured
    with TestClient(create_app()) as client:
        assert client.get('/internal/v1/weather/prototype').status_code==403
        info=client.get('/internal/v1/weather/prototype',headers=headers).json()
        id=str(uuid4());body=dict(frame_id=id,reference_id=info['reference_id'],dimensions=dict(length_m=30,width_m=3,height_m=2),frames=weather.to_dict('records'))
        response=client.post('/internal/v1/weather/prototype/infer',headers=headers,json=body)
        assert response.status_code==200,response.text
        view=client.get(f'/internal/v1/weather/results/{id}/volume',headers=headers).json()
        assert view['y_max']==30 and view['x_max']==3
        params={key:view[key] for key in ('preset','monotonic','y_step','y_min','y_max')}
        params.update(x=1.5,y=29,z=.6,expected_ref=view['field_ref'])
        point=client.get(f'/internal/v1/weather/results/{id}/point',headers=headers,params=params)
        assert point.status_code==200,point.text
        assert point.json()['kind']=='value'
        snapshot=client.post(f'/internal/v1/weather/results/{id}/snapshot',headers=headers,json={})
        assert snapshot.status_code==200,snapshot.text
