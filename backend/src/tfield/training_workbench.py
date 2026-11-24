"""Separate F/G training workflows. All selection excludes the final time holdout."""
from itertools import product
import math
import numpy as np
import pandas as pd
from . import config as C
from .independent_training import GEOMETRY,PROTOCOL,SectionFieldModel,field_features,local_positions
from .models.idw import AnisoMetric
from .weather_chain import WeatherFeatureSpec,WeatherNodeModel,weather_features

PARAMETERS={
    'n_estimators':(120,16,300,True), 'max_depth':(5,2,24,True),
    'learning_rate':(.08,.005,.5,False),'subsample':(.8,.2,1,False),
    'min_samples_leaf':(2,1,20,True),'alpha':(10.,.001,10000.,False),
    'power':(2.,.25,6,False),'lx':(.5,.05,3,False),'lz':(.2,.05,3,False),
    'smoothing':(.01,0,10,False),'seed':(42,0,2147483647,True),
}
ALGORITHMS={'xgboost':['n_estimators','max_depth','learning_rate','subsample'],
    'random_forest':['n_estimators','max_depth','min_samples_leaf'],
    'extra_trees':['n_estimators','max_depth','min_samples_leaf'],'ridge':['alpha']}
INTERPOLATORS={'idw':['power','lx','lz'],'rbf':['smoothing','lx','lz']}

def configuration(raw):
    if not isinstance(raw,dict) or set(raw)-{'target','mode','algorithm','interpolation','params','search','prediction_target'}:raise ValueError('训练工作台配置无效。')
    target=raw.get('target');mode=raw.get('mode','manual');algorithm=raw.get('algorithm','xgboost' if target=='field' else 'extra_trees')
    interpolation=raw.get('interpolation','idw')
    if target not in ('field','mapping') or mode not in ('manual','auto') or algorithm not in ALGORITHMS:raise ValueError('训练类型、方式或模型无效。')
    prediction_target=raw.get('prediction_target','absolute')
    if prediction_target not in ('absolute','delta') or target=='field' and prediction_target!='absolute':raise ValueError('预测温差仅适用于气象映射模型。')
    if interpolation not in INTERPOLATORS:raise ValueError('插值模型无效。')
    allowed=ALGORITHMS[algorithm]+(INTERPOLATORS[interpolation] if target=='field' else ['seed'] if algorithm!='ridge' else [])
    provided=raw.get('params',{})
    if not isinstance(provided,dict) or set(provided)-set(allowed):raise ValueError('参数与所选模型不匹配。')
    def number(key,value):
        _,lo,hi,integer=PARAMETERS[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi or integer and int(value)!=value:
            raise ValueError(f'{key} 须在 {lo:g}–{hi:g} 范围内'+('且为整数。' if integer else '。'))
        return int(value) if integer else float(value)
    params={key:number(key,provided.get(key,PARAMETERS[key][0])) for key in allowed}
    search=raw.get('search',{})
    if not isinstance(search,dict) or set(search)-set(allowed):raise ValueError('优选范围与模型不匹配。')
    normalized={}
    for key,values in search.items():
        if not isinstance(values,list) or not 1<=len(values)<=6:raise ValueError('每项优选参数须包含 1–6 个候选值。')
        normalized[key]=sorted(set(number(key,v) for v in values))
    if mode=='auto' and not normalized:raise ValueError('自动优选至少需要一项候选参数。')
    if math.prod(len(v) for v in normalized.values())>16:raise ValueError('候选组合最多为 16 组，请缩小优选范围。')
    result=dict(target=target,mode=mode,algorithm=algorithm,interpolation=interpolation,params=params,search=normalized if mode=='auto' else {})
    if target=='mapping' and 'prediction_target' in raw:result['prediction_target']=prediction_target
    return result

def estimator(algorithm,p,seed):
    seed=p.get('seed',seed)
    if algorithm=='xgboost':
        from xgboost import XGBRegressor
        return XGBRegressor(n_estimators=p['n_estimators'],max_depth=p['max_depth'],learning_rate=p['learning_rate'],subsample=p['subsample'],objective='reg:squarederror',random_state=seed,n_jobs=2)
    if algorithm in ('random_forest','extra_trees'):
        from sklearn.ensemble import RandomForestRegressor,ExtraTreesRegressor
        cls=RandomForestRegressor if algorithm=='random_forest' else ExtraTreesRegressor
        return cls(n_estimators=p['n_estimators'],max_depth=p['max_depth'],min_samples_leaf=p['min_samples_leaf'],random_state=seed,n_jobs=2)
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge
    return make_pipeline(StandardScaler(),Ridge(alpha=p['alpha']))

def field_fit(weather,houses,sources,w,p,seed):
    X=field_features(weather,local_positions()[sources])
    trend=estimator(w['algorithm'],p,seed)
    trend.fit(pd.concat([X]*len(houses),ignore_index=True),np.concatenate([y[:,sources].ravel() for y in houses.values()]))
    return SectionFieldModel(trend,AnisoMetric(lx=p['lx'],lz=p['lz'],power=p.get('power',2)),GEOMETRY.copy(),
        interpolation=w['interpolation'],rbf_smoothing=p.get('smoothing',.01))

def mapping_fit(weather,houses,w,p,seed):
    spec=WeatherFeatureSpec(True,False);X=weather_features(weather,spec)
    model=estimator(w['algorithm'],p,seed)
    prediction_target=w.get('prediction_target','absolute')
    labels=np.concatenate(list(houses.values()))
    if prediction_target=='delta':labels=labels-np.tile(weather.bg_temp.to_numpy(float),len(houses))[:,None]
    model.fit(pd.concat([X]*len(houses),ignore_index=True),labels)
    return WeatherNodeModel(spec,model,tuple(X.columns),8,prediction_target)

def mapping_comparison(prefix,train_houses,test,test_houses,w,p,seed,selected,checkpoint):
    from .temperature_difference import TemperatureDifferenceFormula
    from .weather_training import scores
    pooled=pd.concat([prefix]*len(train_houses),ignore_index=True)
    formula=TemperatureDifferenceFormula().fit(pooled,np.concatenate(list(train_houses.values())))
    actual=np.concatenate(list(test_houses.values()))
    rows=[dict(key='outside',label='直接使用外温',**scores(actual,np.tile(test.bg_temp.to_numpy(float)[:,None],(len(test_houses),8)))),
          dict(key='formula',label='外温＋光照温差公式',**scores(actual,np.tile(formula.predict(test),(len(test_houses),1))))]
    for kind,label in [('absolute','直接预测温度 G'),('delta','预测温差 G')]:
        checkpoint('正在评估同口径对照：'+label)
        candidate=selected if kind==w.get('prediction_target','absolute') else mapping_fit(prefix,train_houses,w|{'prediction_target':kind},p,seed)
        rows.append(dict(key=kind,label=label,**scores(actual,np.tile(candidate.predict(test),(len(test_houses),1)))))
    return dict(rows=rows,formula=formula.report(),selected=w.get('prediction_target','absolute'),
        definition='同一训练前段拟合、同一测试后段、三棚全部测点逐值评分；对照沿用当前已选参数，不根据测试成绩自动选型。',
        winter_validated=False)

def field_predictions(training,houses,test,test_houses,w,p,seed,positions,checkpoint):
    predictions={house:np.full_like(y,np.nan) for house,y in test_houses.items()}
    for index,held in enumerate(positions):
        checkpoint(f'留一测点验证 {index+1}/{len(positions)}：隐藏位置 B{held+1}')
        sources=[i for i in range(8) if i!=held]
        model=field_fit(training,houses,sources,w,p,seed)
        for house,values in test_houses.items():
            visible=values.copy();visible[:,held]=np.nan
            predictions[house][:,held]=model.predict(test,visible,source_indices=sources,target_positions=local_positions()[[held]])[:,0]
    return predictions

def train(ds,cfg,checkpoint=lambda _:None):
    from .weather_training import arrays,describe,scores
    w=cfg['workbench'];description=describe(ds)
    if not description['ready']:raise ValueError(description['reason'])
    weather,raw,_=arrays(ds)
    if weather.timestamp.isna().any() or weather.timestamp.duplicated().any() or not weather.timestamp.is_monotonic_increasing:raise ValueError('需要严格递增且不重复的时间轴。')
    houses={house:raw[:,i*8:(i+1)*8] for i,house in enumerate(C.SHED_ORDER)}
    split=int(len(weather)*(1-cfg['validation_fraction']))
    prefix=weather.iloc[:split].reset_index(drop=True);test=weather.iloc[split:].reset_index(drop=True)
    train_houses={h:y[:split] for h,y in houses.items()};test_houses={h:y[split:] for h,y in houses.items()}
    keys=sorted(w['search']);candidates=[w['params']|dict(zip(keys,values)) for values in product(*(w['search'][k] for k in keys))] if keys else [w['params']]
    trials=[];best=w['params'].copy()
    if w['mode']=='auto':
        for index,p in enumerate(candidates):
            checkpoint(f'参数优选 {index+1}/{len(candidates)}，仅使用训练时段')
            if w['target']=='field':
                positions=[i for i,key in enumerate(C.SENSOR_LAYOUT) if key in C.TUNING_POSITIONS]
                predicted=field_predictions(prefix,train_houses,prefix,train_houses,w,p,cfg['seed'],positions,checkpoint)
                actual=np.concatenate([y[:,positions] for y in train_houses.values()]);values=np.concatenate([y[:,positions] for y in predicted.values()])
            else:
                inner=int(len(prefix)*.8);a=prefix.iloc[:inner].reset_index(drop=True);b=prefix.iloc[inner:].reset_index(drop=True)
                model=mapping_fit(a,{h:y[:inner] for h,y in train_houses.items()},w,p,cfg['seed'])
                actual=np.concatenate([y[inner:] for y in train_houses.values()]);values=np.tile(model.predict(b),(len(houses),1))
            trials.append(dict(params=p,**scores(actual,values)))
        best=min(trials,key=lambda trial:trial['mae'])['params'].copy()
    checkpoint('正在使用最终参数训练模型')
    if w['target']=='field':
        predictions=field_predictions(prefix,train_houses,test,test_houses,w,best,cfg['seed'],list(range(8)),checkpoint)
        model=field_fit(prefix,train_houses,list(range(8)),w,best,cfg['seed']);models={'field':model}
        definition='未来测试时段的留一位置重建；目标位置同时从趋势拟合与同棚插值来源排除，其余 7 点为同期真实测点。'
    else:
        model=mapping_fit(prefix,train_houses,w,best,cfg['seed']);pred=model.predict(test)
        predictions={h:pred.copy() for h in houses};models={'current':model}
        definition='未来测试时段，仅使用外部温湿光预测单棚 8 点；与三座独立棚的真实标签分别比较。'
    actual=np.concatenate(list(test_houses.values()));predicted=np.concatenate(list(predictions.values()))
    points=local_positions()*[GEOMETRY['width_m'],GEOMETRY['height_m']]
    indices=np.unique(np.linspace(0,len(test)-1,min(180,len(test)),dtype=int))
    plots=[]
    for house,y in test_houses.items():
        entries=[]
        for i,(key,(x,z)) in enumerate(zip(C.SENSOR_LAYOUT,points)):
            entries.append(dict(key=key,label=f'B{i+1}',x=float(x),z=float(z),residual=float(np.mean(y[:,i]-predictions[house][:,i])),
                actual=y[indices,i].tolist(),predicted=predictions[house][indices,i].tolist(),**scores(y[:,i:i+1],predictions[house][:,i:i+1])))
        plots.append(dict(house_id=house,points=entries))
    arch_x=np.linspace(0,GEOMETRY['width_m'],129)
    arch_z=np.sqrt(np.maximum(C.ARCH_R**2-(arch_x-C.ARCH_XC)**2,0))+C.ARCH_K
    result=dict(protocol_version=3,spatial_protocol=PROTOCOL,training_target=w['target'],options=cfg,dataset=description,geometry=GEOMETRY.copy(),
        house_ids=list(houses),nodes_per_house=8,output_nodes=8,
        split=dict(method='chronological',train_frames=split,validation_frames=len(test),train_start=prefix.timestamp.iloc[0].isoformat(),train_end=prefix.timestamp.iloc[-1].isoformat(),validation_start=test.timestamp.iloc[0].isoformat(),validation_end=test.timestamp.iloc[-1].isoformat()),
        test=scores(actual,predicted)|dict(definition=definition),selected_params=best,
        tuning=dict(mode=w['mode'],trials=trials,selection='训练时段内留点验证' if w['target']=='field' else '训练时段内时间留出'),
        plot=dict(times=[pd.Timestamp(test.timestamp.iloc[i]).isoformat() for i in indices],houses=plots,arch=np.column_stack([arch_x,arch_z]).tolist()),
        bounds={key:[float(prefix[key].min()),float(prefix[key].max())] for key in ('bg_temp','bg_rh','bg_light')},
        note=definition+' 测试集不参与选参或最终成品拟合；当前评估不证明未测空间或跨尺寸精度。')
    if w['target']=='mapping':
        result['mapping_comparison']=mapping_comparison(prefix,train_houses,test,test_houses,w,best,cfg['seed'],model,checkpoint)
        result['prediction_target']=w.get('prediction_target','absolute')
    checkpoint('训练完成，正在归档成品及测试报告')
    return result,models
