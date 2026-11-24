"""Server-configured single-house prototype. Users supply dimensions, never paths/models."""
from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import pickle
import numpy as np
import pandas as pd
from .geometry_transfer import HouseDimensions,build_transferred_volume
from .independent_training import GEOMETRY,PROTOCOL,SectionFieldModel
from .weather_chain import WeatherNodeModel

LIMITS={'length_m':(.5,200.),'width_m':(.5,20.),'height_m':(.3,10.)}

def dimensions(value):
    if not isinstance(value,dict) or set(value)!=set(LIMITS):raise ValueError('棚体尺寸须包含 length_m、width_m、height_m。')
    result={}
    for key,(lo,hi) in LIMITS.items():
        number=value[key]
        if isinstance(number,bool) or not isinstance(number,(float,int)) or not np.isfinite(number) or not lo<=number<=hi:
            raise ValueError(f'{key} 须在 {lo:g}–{hi:g} 米之间。')
        result[key]=float(number)
    return result

def _files():
    configured=os.environ.get('TFIELD_PROTOTYPE_MODEL_DIR','')
    if not configured:raise ValueError('单棚原型基准模型尚未配置。')
    root=Path(configured)
    if not root.is_absolute() or root.is_symlink():raise ValueError('原型模型目录配置无效。')
    root=root.resolve()
    def read(name):
        path=root/name
        if path.is_symlink() or path.resolve().parent!=root or not path.is_file() or path.stat().st_size>32*1024*1024:
            raise ValueError('原型成品文件缺失或无效。')
        return path.read_bytes()
    manifest_raw,report_raw=read('model-manifest.json'),read('report.json')
    manifest,report=json.loads(manifest_raw),json.loads(report_raw)
    if manifest.get('protocol')!=PROTOCOL or report.get('spatial_protocol')!=PROTOCOL:raise ValueError('原型模型协议不一致。')
    if any(manifest['geometry'].get(k)!=GEOMETRY[k] for k in LIMITS):raise ValueError('原型模型参考几何不一致。')
    raw={name:read(name) for name in ('current.pkl','history.pkl','field.pkl')}
    if any(hashlib.sha256(value).hexdigest()!=manifest['files'].get(name) for name,value in raw.items()):raise ValueError('原型模型摘要不一致。')
    reference=hashlib.sha256(manifest_raw+report_raw).hexdigest()
    return root,reference,report,raw

@lru_cache(maxsize=4)
def _decode(reference,current_raw,field_raw):
    current,field=pickle.loads(current_raw),pickle.loads(field_raw)
    if not isinstance(current,WeatherNodeModel) or current.n_nodes!=8 or current.spec.history or not isinstance(field,SectionFieldModel) or field.protocol!=PROTOCOL:
        raise ValueError('原型模型不是单时刻 8 点 G/F 成品。')
    return current,field

def info():
    limits={key:{'min':lo,'max':hi} for key,(lo,hi) in LIMITS.items()}
    try:
        _,reference,report,raw=_files();node,_=_decode(reference,raw['current.pkl'],raw['field.pkl'])
        return dict(ready=True,reference_id=reference,name=report['options']['name'],
            prediction_target=getattr(node,'prediction_target','absolute'),
            reference_dimensions={k:GEOMETRY[k] for k in LIMITS},limits=limits,accuracy_validated=False)
    except (ValueError,OSError,KeyError,TypeError,pickle.UnpicklingError):
        return dict(ready=False,detail='单棚原型基准模型尚未配置或校验失败，请联系管理员。',limits=limits,
            reference_dimensions={k:GEOMETRY[k] for k in LIMITS})

def infer(frames,requested,expected):
    dims=dimensions(requested)
    _,reference,report,raw=_files()
    if reference!=expected:raise ValueError('原型基准模型已变化，请重新构场。')
    node,field=_decode(reference,raw['current.pkl'],raw['field.pkl'])
    if not isinstance(frames,list) or len(frames)!=1:raise ValueError('单棚原型每次接收一个气象时刻。')
    weather=pd.DataFrame(frames)
    ts=pd.to_datetime(weather.timestamp,utc=True,errors='raise')
    if ts.isna().any():raise ValueError('气象时刻无效。')
    weather['timestamp']=ts.dt.tz_convert('Asia/Shanghai').dt.tz_localize(None)
    virtual,rh=node.predict_with_humidity(weather)
    weather['bg_rh']=rh
    volume=build_transferred_volume(field,weather,virtual[0],HouseDimensions(**dims),allow_assumptions=True,source_ref=reference).payload()
    when=ts.iloc[0].isoformat();volume['time']=when
    bounds=report.get('bounds',{})
    summary=dict(time=when,mean=volume['mean'],vmin=volume['vmin'],vmax=volume['vmax'],model_id=None,
        model_name=report['options']['name'],prototype=True,prototype_reference=reference,dimensions=dims,
        external_schema='full' if node.spec.humidity else 'two',stage1_mode='current_only',
        background_humidity_used=float(rh[0]),node_temperatures=virtual[0].tolist(),
        source='prototype_weather_prediction',warnings=[],training_bounds=bounds,
        prediction_target=getattr(node,'prediction_target','absolute'),
        transfer=volume['transfer'],accuracy_validated=False)
    return dict(summary=summary,field=volume,input={'timestamp':when,**{key:float(weather[key].iloc[0]) for key in ('bg_temp','bg_light','bg_rh')}})
