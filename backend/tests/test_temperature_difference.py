import pickle
import numpy as np
import pandas as pd
import pytest
from tfield.temperature_difference import TemperatureDifferenceFormula
from tfield.weather_chain import WeatherNodeModel, WeatherFeatureSpec
from tfield.weather_training import train, arrays
from test_training_workbench import sample, cfg
from test_prototype_runtime import configured


def test_formula_recovers_per_node_difference_and_keeps_cold_response():
    weather=pd.DataFrame({'bg_temp':[25.,26.,28.,30.], 'bg_light':[0.,10000.,20000.,40000.]})
    delta=np.array([.5,1.5])+weather.bg_light.to_numpy()[:,None]/10000*np.array([.2,.8])
    labels=weather.bg_temp.to_numpy()[:,None]+delta
    model=TemperatureDifferenceFormula().fit(weather,labels)
    np.testing.assert_allclose(model.predict(weather),labels)
    cold=weather.assign(bg_temp=weather.bg_temp-35)
    np.testing.assert_allclose(model.predict(cold),labels-35)
    restored=pickle.loads(pickle.dumps(model))
    np.testing.assert_allclose(restored.predict(cold),model.predict(cold))
    assert model.report()['winter_validated'] is False


@pytest.mark.parametrize('humidity',[True,False])
def test_delta_model_restores_temperature_but_never_offsets_humidity(humidity):
    from test_weather_chain import MeanEstimator,external
    weather=external()
    labels=weather.bg_temp.to_numpy()[:,None]+np.array([1.,2.])
    model=WeatherNodeModel(WeatherFeatureSpec(humidity,False),MeanEstimator(),prediction_target='delta').fit(weather,labels)
    cold=weather.assign(bg_temp=-5.)
    if not humidity:cold=cold.drop(columns='bg_rh')
    values,rh=pickle.loads(pickle.dumps(model)).predict_with_humidity(cold)
    np.testing.assert_allclose(values,np.tile([-4.,-3.],(len(cold),1)))
    np.testing.assert_allclose(rh,weather.bg_rh if humidity else 70.)


def test_old_absolute_pickle_without_target_remains_compatible():
    from test_weather_chain import MeanEstimator,external
    model=WeatherNodeModel(WeatherFeatureSpec(),MeanEstimator()).fit(external(),np.full((20,2),27.))
    del model.prediction_target
    np.testing.assert_array_equal(pickle.loads(pickle.dumps(model)).predict(external().assign(bg_temp=-5)),np.full((20,2),27.))


def test_comparisons_exclude_test_labels_and_keep_same_sample_population():
    request=cfg('mapping','ridge');request['workbench']['prediction_target']='delta'
    a,models=train(sample(),request)
    changed=sample();_,_,columns=arrays(changed);changed.wide.loc[72:,columns]+=100
    b,changed_models=train(changed,request)
    weather,_,_=arrays(sample())
    np.testing.assert_array_equal(models['current'].predict(weather),changed_models['current'].predict(weather))
    assert a['mapping_comparison']['formula']==b['mapping_comparison']['formula']
    rows=a['mapping_comparison']['rows']
    assert [r['key'] for r in rows]==['outside','formula','absolute','delta']
    assert all(r['n']==a['test']['n'] for r in rows)
    assert rows[-1]['mae']==pytest.approx(a['test']['mae'])
    assert a['prediction_target']=='delta'


def test_delta_auto_tuning_never_uses_final_test_labels():
    request=cfg('mapping',mode='auto',search={'alpha':[1,10]})
    request['workbench']['prediction_target']='delta'
    a,_=train(sample(),request)
    changed=sample();_,_,columns=arrays(changed);changed.wide.loc[72:,columns]+=500
    b,_=train(changed,request)
    assert a['tuning']==b['tuning']


def test_out_of_range_weather_still_constructs_field_without_range_warning(configured):
    from tfield import prototype_runtime
    _,weather=configured
    result=prototype_runtime.infer(weather.assign(bg_temp=-5).to_dict('records'),dict(length_m=6,width_m=2.1,height_m=1.3017),prototype_runtime.info()['reference_id'])
    assert result['field']['planes']
    assert np.isfinite(result['summary']['mean'])
    assert result['summary']['warnings'] == []


def test_saved_out_of_range_field_remains_readable(configured,monkeypatch):
    from api import weather_views
    from tfield import weather_runtime,prototype_runtime
    from uuid import uuid4
    _,weather=configured
    result=prototype_runtime.infer(weather.to_dict('records'),dict(length_m=6,width_m=2.1,height_m=1.3017),prototype_runtime.info()['reference_id'])
    result['input']['bg_temp']=-5
    result['summary']['warnings']=['bg_temp_outside_training_range','training_range_unavailable','other_warning']
    result['field']['provenance']={'warnings':['bg_light_outside_training_range','other_warning']}
    identifier=str(uuid4());weather_runtime.save_result(identifier,result)
    monkeypatch.setattr(prototype_runtime,'infer',lambda *a:pytest.fail('Saved result must not be recomputed'))
    saved,volume=weather_views.saved_volume(identifier)
    assert saved['input']['bg_temp']==-5
    assert volume['mean']==result['field']['mean']
    assert saved['summary']['warnings']==['other_warning']
    assert saved['field']['provenance']['warnings']==['other_warning']
    assert volume['provenance']['warnings']==['other_warning']
