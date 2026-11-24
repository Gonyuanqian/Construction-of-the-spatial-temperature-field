import pickle
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tfield import config as C
from tfield import independent_training as independent
from tfield.weather_training import arrays, options, train


def sample(n=90):
    t=np.arange(n)
    wide=pd.DataFrame({C.COL_TIMESTAMP:pd.date_range('2026-07-23',periods=n,freq='5min'),
        C.BG_TEMP:25+np.sin(t/8), C.BG_RH:60+np.cos(t/6), C.BG_LIGHT:100+2*t})
    for house_index,house in enumerate(C.SHED_ORDER):
        for position_index,position in enumerate(C.SENSOR_LAYOUT):
            wide[f'{house}_{position}_{C.VAR_TEMP}']=wide[C.BG_TEMP]+position_index*.1+house_index*.25
    return SimpleNamespace(wide=wide)


CONFIG=dict(spatial_protocol=independent.PROTOCOL,algorithm='ridge',n_estimators=16,seed=42)


@pytest.fixture(scope='module')
def fitted():
    return train(sample(),CONFIG)


def test_protocol_has_three_house_groups_but_eight_outputs_and_no_longitudinal_claim(fitted):
    report,models=fitted
    assert report['protocol_version']==2 and report['output_nodes']==8
    assert report['house_ids']==['p1','p2','p3']
    assert report['geometry']['length_m']==6
    assert report['geometry']['longitudinal_sampling']=='single_cross_section'
    assert report['geometry']['section_y_m'] is None
    weather,_,_=arrays(sample())
    for key in ('current','history'):
        model=pickle.loads(pickle.dumps(models[key]))
        assert model.predict(weather.tail(13)).shape==(13,8)
        assert not any(feature in ('house_id','x','y','z') for feature in model.feature_names)
    field=pickle.loads(pickle.dumps(models['field']))
    assert field.protocol==independent.PROTOCOL
    assert 'y' not in field.trend.get_booster().feature_names


def test_hidden_target_is_excluded_from_both_f_trend_and_idw(monkeypatch):
    weather,raw,_=arrays(sample());weather=weather.iloc[:20]
    houses={h:raw[:20,i*8:(i+1)*8] for i,h in enumerate(C.SHED_ORDER)}
    held=0;sources=list(range(1,8));cfg=options(CONFIG)
    candidate=dict(max_depth=3,lx=.5,lz=.2,power=2)
    first=independent.fit_field(weather,houses,sources,cfg,candidate)
    altered={h:y.copy() for h,y in houses.items()}
    for values in altered.values():values[:,held]+=10000
    second=independent.fit_field(weather,altered,sources,cfg,candidate)
    x=independent.field_features(weather,independent.local_positions())
    np.testing.assert_array_equal(first.trend.predict(x),second.trend.predict(x))
    observed=[]
    original=independent.IDWCorrector.fit
    def audit(self,coords,resid):
        observed.append(len(coords));return original(self,coords,resid)
    monkeypatch.setattr(independent.IDWCorrector,'fit',audit)
    a=first.predict(weather,houses['p1'],source_indices=sources)
    b=first.predict(weather,altered['p1'],source_indices=sources)
    np.testing.assert_array_equal(a,b);assert observed==[7,7]


def test_idw_sources_are_one_house_and_f_reproduces_supplied_virtual_nodes(fitted):
    _,models=fitted;weather,raw,_=arrays(sample());weather=weather.tail(4).reset_index(drop=True)
    virtual=models['current'].predict(weather)
    np.testing.assert_allclose(models['field'].predict(weather,virtual),virtual,atol=1e-7)
    with pytest.raises(ValueError,match='一座棚'):
        models['field'].predict(weather,raw[-4:])
    with pytest.raises(ValueError,match='互不重复'):
        models['field'].predict(weather,virtual,source_indices=[1,1])


def test_future_labels_never_change_artifacts_or_parameter_selection(fitted):
    first,m1=fitted;changed=sample();_,_,columns=arrays(changed)
    changed.wide.loc[72:,columns]+=500
    second,m2=train(changed,CONFIG)
    assert first['field_validation']['trials']==second['field_validation']['trials']
    weather,_,_=arrays(sample())
    for key in ('current','history'):
        np.testing.assert_array_equal(m1[key].predict(weather),m2[key].predict(weather))
    x=independent.field_features(weather,independent.local_positions())
    np.testing.assert_array_equal(m1['field'].trend.predict(x),m2['field'].trend.predict(x))
    assert second['variants'][0]['validation']['mae']>400


def test_held_house_labels_never_influence_its_outer_predictions(fitted):
    first,_=fitted;changed=sample()
    for position in C.SENSOR_LAYOUT:changed.wide[f'p3_{position}_{C.VAR_TEMP}']+=50
    second,_=train(changed,CONFIG)
    for before,after in zip(first['variants'],second['variants']):
        a=next(f for f in before['cross_house'] if f['house_id']=='p3')
        b=next(f for f in after['cross_house'] if f['house_id']=='p3')
        assert a['training_houses']==['p1','p2']
        assert a['prediction_sha256']==b['prediction_sha256']
        assert b['mae']>a['mae']+40


def test_b_positions_never_select_parameters_and_only_source_nodes_are_visible(fitted):
    report,_=fitted
    assert len(report['field_validation']['trials'])==4
    assert report['field_validation']['source_policy']=='same_house_only'
    assert {r['position'] for r in report['field_validation']['per_point']}==set(C.REPORT_POSITIONS)
    assert {r['house_id'] for r in report['field_validation']['per_point']}==set(C.SHED_ORDER)


@pytest.mark.parametrize('schema',['two','full'])
def test_both_input_schemas_and_gap_history_are_supported(schema):
    ds=sample();ds.wide.loc[40:,C.COL_TIMESTAMP]+=pd.Timedelta(hours=2)
    report,models=train(ds,CONFIG|{'external_schema':schema})
    weather,_,_=arrays(ds);nodes,rh=models['current'].predict_with_humidity(weather.tail(1))
    assert nodes.shape==(1,8) and rh.shape==(1,)
    assert len(report['variants'][0]['cross_house'])==3


def test_cancellation_checkpoint_interrupts_long_training():
    def cancel(_):raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError,match='cancelled'):train(sample(),CONFIG,cancel)
