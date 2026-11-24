import pickle
from types import SimpleNamespace
from uuid import uuid4
import numpy as np
import pandas as pd
import pytest
from tfield import config as C
from tfield.weather_training import train,arrays,options
from tfield.training_workbench import configuration,field_predictions
from tfield.independent_training import field_features,local_positions
from test_weather_training import api,wait

def sample(n=90):
    t=np.arange(n);wide=pd.DataFrame({C.COL_TIMESTAMP:pd.date_range('2026-07-23',periods=n,freq='5min'),C.BG_TEMP:25+np.sin(t/8),C.BG_RH:60+np.cos(t/6),C.BG_LIGHT:100+2*t})
    for hi,h in enumerate(C.SHED_ORDER):
        for pi,p in enumerate(C.SENSOR_LAYOUT):wide[f'{h}_{p}_{C.VAR_TEMP}']=wide[C.BG_TEMP]+pi*.15+hi*.2+np.sin(t/5+pi)*.02
    return SimpleNamespace(wide=wide)
def cfg(target='field',algorithm='ridge',interpolation='idw',mode='manual',search=None):
    p={'alpha':10} if algorithm=='ridge' else {'n_estimators':16,'max_depth':3,'min_samples_leaf':2} if algorithm!='xgboost' else {'n_estimators':16,'max_depth':3,'learning_rate':.08,'subsample':.8}
    if target=='field':p|={'lx':.5,'lz':.2,**({'power':2} if interpolation=='idw' else {'smoothing':.01})}
    return dict(spatial_protocol='independent_house_section_v2',workbench=dict(target=target,algorithm=algorithm,interpolation=interpolation,mode=mode,params=p,search=search or {}))

@pytest.mark.parametrize('target,algorithm,interp',[('field','xgboost','idw'),('field','random_forest','idw'),('field','extra_trees','rbf'),('field','ridge','rbf'),('mapping','xgboost','idw'),('mapping','random_forest','idw'),('mapping','extra_trees','idw'),('mapping','ridge','idw')])
def test_manual_workflows_fit_requested_models_and_report_real_test_data(target,algorithm,interp):
    requested=cfg(target,algorithm,interp);report,models=train(sample(),requested)
    assert set(models)==({'field'} if target=='field' else {'current'})
    assert report['training_target']==target and report['tuning']['trials']==[]
    assert report['selected_params']==configuration(requested['workbench'])['params']
    assert report['test']['n']==18*24 and np.isfinite(report['test']['mae'])
    assert len(report['plot']['houses'])==3 and len(report['plot']['houses'][0]['points'])==8
    point=report['plot']['houses'][0]['points'][0]
    assert point['residual']==pytest.approx(np.mean(np.array(point['actual'])-point['predicted']))
    assert report['split']['train_end']<report['split']['validation_start']
    restored=pickle.loads(pickle.dumps(next(iter(models.values()))))
    weather,_,_=arrays(sample())
    if target=='mapping':assert restored.predict(weather.tail(1)).shape==(1,8)
    else:assert restored.predict(weather.tail(1),np.full((1,8),26.)).shape==(1,8)

@pytest.mark.parametrize('target',['field','mapping'])
def test_auto_search_and_models_do_not_use_outer_test_labels(target):
    request=cfg(target,mode='auto',search={'alpha':[1,10]})
    first,a=train(sample(),request);changed=sample();_,_,columns=arrays(changed);changed.wide.loc[72:,columns]+=300
    second,b=train(changed,request)
    assert first['tuning']['trials']==second['tuning']['trials'] and len(first['tuning']['trials'])==2
    assert first['selected_params']==second['selected_params']
    weather,_,_=arrays(sample())
    if target=='mapping':np.testing.assert_array_equal(a['current'].predict(weather),b['current'].predict(weather))
    else:np.testing.assert_array_equal(a['field'].trend.predict(field_features(weather,local_positions())),b['field'].trend.predict(field_features(weather,local_positions())))

def test_field_leave_point_excludes_target_from_trend_and_interpolation():
    weather,raw,_=arrays(sample());request=options(cfg());w=request['workbench'];houses={h:raw[:,i*8:(i+1)*8] for i,h in enumerate(C.SHED_ORDER)}
    first=field_predictions(weather[:72],{h:y[:72] for h,y in houses.items()},weather[72:],{h:y[72:] for h,y in houses.items()},w,w['params'],42,[0],lambda _:None)
    for y in houses.values():y[:,0]+=500
    second=field_predictions(weather[:72],{h:y[:72] for h,y in houses.items()},weather[72:],{h:y[72:] for h,y in houses.items()},w,w['params'],42,[0],lambda _:None)
    for h in houses:np.testing.assert_array_equal(first[h][:,0],second[h][:,0])

@pytest.mark.parametrize('raw',[{'target':'field','params':{'unknown':1}},{'target':'field','params':{'max_depth':3.5}},{'target':'mapping','params':{'power':2}},{'target':'field','mode':'auto','search':{}},{'target':'field','mode':'auto','search':{'max_depth':[2,3,4,5,6],'power':[1,2,3,4]}}])
def test_invalid_workbench_parameters_fail_before_training(raw):
    with pytest.raises(ValueError):configuration(raw)

def test_save_names_real_artifacts_is_idempotent_and_survives_restart(api):
    from api import weather_training as jobs
    client,headers,directory=api;id=str(uuid4());url='/internal/v1/weather-training/jobs/'+id
    assert client.get('/internal/v1/weather-training/models').status_code==403
    assert client.post(url,headers=headers,json=cfg('mapping')).status_code==200
    done=wait(client,headers,id);assert done['state']=='done',done
    response=client.post(url+'/save',headers=headers,json={'name':'我的映射模型'})
    assert response.status_code==200,response.text
    assert response.json()['target']=='mapping' and set(response.json()['artifacts'])=={'current'}
    assert client.post(url+'/save',headers=headers,json={'name':'我的映射模型'}).json()==response.json()
    assert client.post(url+'/save',headers=headers,json={'name':'不同名称'}).status_code==409
    jobs.recover()
    assert client.get('/internal/v1/weather-training/models',headers=headers).json()==[response.json()]
