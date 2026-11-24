"""Views of a saved weather field, never a sensor replay or another model fit."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from zoneinfo import ZoneInfo

import numpy as np
from tfield import config as C, weather_runtime
from tfield.field.profile import height_temperature_profile
from .assistant import field_tools, store


def saved_volume(frame_id, *, preset='standard', monotonic=True, y_step=.5, y_min=0., y_max=None):
    if preset not in ('standard','experimental_transfer'):
        raise ValueError('气象视图预设无效。')
    limits=(y_step,y_min) if y_max is None else (y_step,y_min,y_max)
    if not all(math.isfinite(v) for v in limits):
        raise ValueError('气象视图参数必须是有限数值。')
    if not .5<=y_step<=6:
        raise ValueError('气象视图步长须为 0.5–6 m。')
    if y_min<0 or y_max is not None and y_max<=y_min:
        raise ValueError('气象视图起止范围无效。')
    result=weather_runtime.read_result(frame_id)
    if result['summary'].get('prototype'):
        return prototype_volume(frame_id,result,preset,y_step,y_min,y_max)
    if y_max is None:y_max=18.
    if preset != 'standard' or not monotonic:
        raise ValueError('气象历史结果使用固定 standard 网格与物理约束，不能在读取时更换计算配置。')
    if not all(math.isfinite(v) for v in (y_step, y_min, y_max)) or not (0 <= y_min < y_max <= 18 and .5 <= y_step <= 6):
        raise ValueError('气象视图范围须在 0–18 m，步长为 0.5–6 m。')
    if any(abs(v/.5-round(v/.5)) > 1e-8 for v in (y_step, y_min, y_max)):
        raise ValueError('气象历史视图只能按已保存的 0.5 m 网格抽取切片。')
    volume=deepcopy(result['field'])
    original={round(p['y'],8):p for p in volume['planes']}
    ys=np.arange(y_min, y_max+1e-8, y_step)
    volume['planes']=[original[round(float(y),8)] for y in ys]
    local_time=datetime.fromisoformat(result['summary']['time'].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).isoformat()
    volume.update(y_step=y_step,y_min=y_min,y_max=y_max,time=local_time,timezone='Asia/Shanghai')
    volume['geometry']=volume.get('geometry') or {'radius':float(C.ARCH_R),'center_x':float(C.ARCH_XC),'offset_z':float(C.ARCH_K)}
    for plane in volume['planes']:
        plane['measured']=False
        plane['virtual_source']=plane.get('shed') is not None
    blocked={(ix,iz) for ix,iz in volume['stripes']}
    values=[v for plane in volume['planes'] for iz,row in enumerate(plane['values']) for ix,v in enumerate(row)
            if v is not None and (ix,iz) not in blocked and math.isfinite(v)]
    volume['mean']=float(np.mean(values)) if values else None
    signature=json.dumps([frame_id,preset,True,float(y_min),float(y_max),float(y_step)],separators=(',',':'))
    volume['field_ref']='weather-'+hashlib.sha256(signature.encode()).hexdigest()
    volume['provenance']=deepcopy(result['summary'])
    volume['frame']={'n':0,'time':local_time,'source':'virtual_weather_prediction'}
    volume['height_profile']=height_temperature_profile(volume['z'],volume['planes'])
    return result,volume

def prototype_volume(frame_id,result,preset,y_step,y_min,y_max):
    volume=deepcopy(result['field']);length=result['summary']['dimensions']['length_m']
    if y_max is None:y_max=length
    if preset not in ('standard','experimental_transfer') or not all(math.isfinite(v) for v in (y_step,y_min,y_max)) or not 0<=y_min<y_max<=length or not .5<=y_step<=6:
        raise ValueError('原型视图须位于当前棚长范围，步长为 0.5–6 m。')
    ys=np.arange(y_min,y_max+1e-9,y_step)
    if abs(ys[-1]-y_max)>1e-8:ys=np.append(ys,y_max)
    plane=volume['planes'][0]
    volume['planes']=[{**deepcopy(plane),'y':float(y),'measured':False,'virtual_source':False,'shed':None} for y in ys]
    local=datetime.fromisoformat(result['summary']['time'].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).isoformat()
    # The served grid uses the standard view profile. Experimental provenance
    # remains in transfer; echoing this profile to /point must be supported.
    volume.update(preset='standard',y_step=y_step,y_min=y_min,y_max=y_max,time=local,timezone='Asia/Shanghai',monotonic=False)
    signature=json.dumps([frame_id,volume['field_ref'],float(y_min),float(y_max),float(y_step)],separators=(',',':'))
    volume['field_ref']='prototype-'+hashlib.sha256(signature.encode()).hexdigest()
    volume['provenance']=deepcopy(result['summary']);volume['geometry']={'kind':'saved_arch_polyline'}
    volume['frame']={'n':0,'time':local,'source':'prototype_weather_prediction'}
    volume['height_profile']=height_temperature_profile(volume['z'],volume['planes'])
    return result,volume


def sections(frame_id, *, preset='standard', monotonic=True):
    result,volume=saved_volume(frame_id,preset=preset,monotonic=monotonic)
    keys=('t_index','time','n_times','preset','monotonic','calibrated','mismatch_note','artifact_note',
          'vmin','vmax','max_measured_z','x_min','x_max','z_max','x','z','arch','sensors','provenance','field_ref')
    payload={key:volume[key] for key in keys}
    if result['summary'].get('prototype'):
        payload['sheds']=[{'shed':'single_prototype','y':volume['y_max']/2,'values':volume['planes'][0]['values'],
            'stripes':deepcopy(volume['stripes']),'measured':False,'virtual_source':False}]
        payload['frame']={**volume['frame'],**result.get('input',{}),'sensor_temps':[None]*8,
            'predicted_sensor_temps':result['summary']['node_temperatures'],'bg_rh':result['summary']['background_humidity_used']}
        payload['transfer']=volume['transfer'];payload['note']=volume['note']
        return payload
    payload['sheds']=[{'shed':shed['id'],'y':shed['y'],'values':next(p['values'] for p in volume['planes'] if abs(p['y']-shed['y'])<1e-8),
                       'stripes':deepcopy(volume['stripes']),'measured':False,'virtual_source':True} for shed in volume['sheds']]
    payload['frame']={**volume['frame'], **result.get('input',{}),
                      'sensor_temps':[None]*24, 'predicted_sensor_temps':result['summary']['node_temperatures'],
                      'bg_rh':result['summary']['background_humidity_used']}
    payload['note']='棚内 24 个点由外部气象预测；sensor_temps 留空，不把模型预测标成传感器实测。'
    return payload


def point(frame_id, x, y, z, *, expected_ref=None, **profile):
    result,volume=saved_volume(frame_id,**profile)
    if expected_ref is not None and expected_ref!=volume['field_ref']:
        from fastapi import HTTPException
        raise HTTPException(409,'气象观测或网格视图已变化，请刷新后查询。')
    value=field_tools.point({'volume':volume},{'x':x,'y':y,'z':z})
    return {**value,'x':x,'y':y,'z':z,'time':volume['time'],'t_index':0,
            'field_ref':volume['field_ref'],'frame':volume['frame'],'method':'trilinear',
            'measured_plane':False,'source':result['summary'].get('source','virtual_weather_prediction'),
            'max_measured_z':volume['max_measured_z'],'note':'对同一份已保存的气象推算网格插值，不读取棚内实测。'}


def snapshot(frame_id, context):
    result,volume=saved_volume(frame_id)
    summary=result['summary']
    nodes=summary['node_temperatures']
    facts=[{'id':'F:context','text':'当前为外部气象驱动的模型推算。棚内点位和温度场都不是现场传感器实测。',
            'origin':'virtual_weather_prediction','source_time':summary['time']},
           {'id':'F:weather-model','text':'固定模型及气象档案配置','origin':'virtual_weather_prediction',
            'model_id':summary['model_id'],'package_id':summary.get('package_id'),'prototype_reference':summary.get('prototype_reference'),
            'dimensions':summary.get('dimensions'),'location':context.get('location')}]
    weather=context.get('weather') or {}
    source=context.get('weather_source') or {}
    if summary.get('prototype'):
        facts.append(dict(id='F:prototype-limits',origin='virtual_weather_prediction',text='单棚原型：基于单一横截面估算，沿棚长均匀展开。不同尺寸下的准确性尚未实测验证，不可据此判断沿棚长的真实冷热差异。'))
    for key,label,unit in [('bg_temp','外部气象温度','°C'),('bg_rh','外部相对湿度','%'),('bg_light','外部照度估算值','lux')]:
        value=weather.get(key)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
            facts.append(dict(id='F:external:'+key,text=label,value=float(value),unit=unit,origin='external_weather',
                source_time=source.get('light_time' if key=='bg_light' else 'observed_at',summary['time']),
                statistic_definition='外部气象输入，不是棚内或土壤实测；光照为辐射预报换算的近似照度。' if key=='bg_light' else '外部气象输入，不是棚内或土壤实测。'))
    facts.append(dict(id='F:weather-source',text='本次气象来源及近似口径',origin='external_weather',
        source_time=summary['time'],weather_source=source,light_conversion=context.get('light_conversion')))
    for name,value in [('虚拟测点均温',float(np.mean(nodes))),('虚拟测点最高温',max(nodes)),('虚拟测点最低温',min(nodes))]:
        facts.append({'id':f'F:predicted:{len(facts)}','text':name,'value':value,'unit':'°C',
                      'origin':'virtual_weather_prediction','count':len(nodes),'statistic_definition':f'{len(nodes)} 个预测点的统计，不是实测或体积均温'})
    return field_tools.public_snapshot(store.snapshot({'session_id':frame_id,'frame_index':0,
        'source_time':volume['time'],'source_timezone':'Asia/Shanghai','source':summary.get('source','virtual_weather_prediction'),'data_mode':'external_weather',
        'model_id':summary['model_id'],'provenance':summary,'archive_snapshot':context.get('archive_snapshot'),
        'location':context.get('location'),'volume':volume,'facts':facts,
        'calculation_profile':{'preset':'standard','monotonic':volume['monotonic'],'y_step':.5,'y_min':volume['y_min'],'y_max':volume['y_max']},
        'field_domain':{'x_min':volume['x'][0],'x_max':volume['x'][-1],'y_min':volume['y_min'],'y_max':volume['y_max'],
                        'z_min':volume['z'][0],'z_max':volume['z'][-1],'max_measured_z':volume['max_measured_z']}}))
