"""Read only a materialized volume. Never consult the active pipeline or playback clock."""
from __future__ import annotations

import hashlib
import math
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tfield.field.sample import axis_weights, sample_grid


class Position(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: float
    y: float
    z: float


class Region(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x_min: float; x_max: float
    y_min: float; y_max: float
    z_min: float; z_max: float

    @model_validator(mode='after')
    def ordered(self):
        if any(getattr(self, a+'_min') > getattr(self, a+'_max') for a in ('x','y','z')):
            raise ValueError('区域下限不能大于上限')
        return self


class RegionPair(BaseModel):
    model_config=ConfigDict(extra='forbid')
    first: Region
    second: Region


def public_snapshot(snapshot):
    return {k:v for k,v in snapshot.items() if k!='volume'}


def volume_of(snapshot):
    if not snapshot.get('volume'):
        raise ValueError('该旧快照没有三维数据，请重新绑定当前帧。')
    return snapshot['volume']


def point(snapshot, position):
    p=Position.model_validate(position)
    volume=volume_of(snapshot)
    xs,ys,zs=volume['x'],[plane['y'] for plane in volume['planes']],volume['z']
    for axis,value in ((xs,p.x),(ys,p.y),(zs,p.z)):
        axis_weights(axis,value)
    geometry=volume['geometry']
    height=float(np.interp(p.x,np.asarray(volume['arch'])[:,0],np.asarray(volume['arch'])[:,1])) if geometry.get('kind')=='saved_arch_polyline' else math.sqrt(max(0,geometry['radius']**2-(p.x-geometry['center_x'])**2))+geometry['offset_z']
    value=None
    if p.z>height+1e-12:
        kind='outside'
    elif p.z>volume['max_measured_z']+1e-9:
        kind='unmeasured'
    else:
        blocked={tuple(cell) for cell in volume['stripes']}
        value=sample_grid(xs,ys,zs,(p.x,p.y,p.z),
            lambda i:np.asarray(volume['planes'][i]['values'],dtype=float),
            lambda ix,iz:(ix,iz) in blocked)
        kind='value' if value is not None else 'unavailable'
    shed=next((s['id'] for s in volume.get('sheds',[]) if abs(s['y']-p.y)<=1e-9
               and s['id'] in volume.get('available_sheds',[])),None)
    virtual=volume.get('provenance',{}).get('source')=='virtual_weather_prediction'
    return dict(p.model_dump(),kind=kind,value=value,method='trilinear',
        measured_plane=shed is not None and not virtual,shed=shed,max_measured_z=volume['max_measured_z'],
        time=volume['time'],t_index=volume['t_index'],field_ref=volume['field_ref'],
        note='固定快照的约束后三维网格插值；重建值，不吸附，不读取最新帧。')


def statistics(snapshot, region=None):
    volume=volume_of(snapshot)
    xs,zs=volume['x'],volume['z']
    ys=[plane['y'] for plane in volume['planes']]
    bounds=Region.model_validate(region) if region else Region(x_min=xs[0],x_max=xs[-1],
        y_min=ys[0],y_max=ys[-1],z_min=zs[0],z_max=zs[-1])
    for axis,values in ((xs,(bounds.x_min,bounds.x_max)),(ys,(bounds.y_min,bounds.y_max)),
                        (zs,(bounds.z_min,bounds.z_max))):
        for v in values: axis_weights(axis,v)
    blocked={tuple(cell) for cell in volume['stripes']}
    samples=[]; considered=0
    for plane in volume['planes']:
        if not bounds.y_min<=plane['y']<=bounds.y_max: continue
        for iz,z in enumerate(zs):
            if not bounds.z_min<=z<=bounds.z_max: continue
            for ix,x in enumerate(xs):
                if not bounds.x_min<=x<=bounds.x_max: continue
                considered+=1
                value=plane['values'][iz][ix]
                if (ix,iz) in blocked or z>volume['max_measured_z']+1e-9 or value is None or not math.isfinite(value):
                    continue
                samples.append((float(value),{'x':x,'y':plane['y'],'z':z}))
    result={'region':bounds.model_dump(),'valid_count':len(samples),'considered_count':considered,
            'statistic_definition':'有效网格样本算术统计；排除拱外、无测量带和缺失值；不是体积加权均温或真实连续场极值。',
            'resolution':{'x_step':xs[1]-xs[0] if len(xs)>1 else None,
                          'y_step':ys[1]-ys[0] if len(ys)>1 else None,
                          'z_step':zs[1]-zs[0] if len(zs)>1 else None}}
    if not samples:
        return dict(result,status='no_data',mean=None,minimum=None,maximum=None)
    minimum=min(v for v,_ in samples); maximum=max(v for v,_ in samples)
    def extreme(value):
        locations=[pos for v,pos in samples if v==value]
        return {'value':value,'position':locations[0],'tied_count':len(locations),'locations':locations[:5]}
    return dict(result,status='ok',mean=sum(v for v,_ in samples)/len(samples),
                minimum=extreme(minimum),maximum=extreme(maximum))


def tool_facts(snapshot, name, args):
    from .store import packed
    suffix=hashlib.sha256(packed(args).encode()).hexdigest()[:10]
    common={'snapshot_id':snapshot['snapshot_id'],'source_time':snapshot['source_time'],
            'origin':'reconstructed_grid','unit':'°C'}
    if name=='compare_regions':
        pair=RegionPair.model_validate(args)
        first=statistics(snapshot,pair.first.model_dump()); second=statistics(snapshot,pair.second.model_dump())
        if first['status']!='ok' or second['status']!='ok':
            return [dict(common,id='F:comparison:'+suffix,text='至少一个区域没有有效网格，不能比较',value=None,
                         region_first=first['region'],region_second=second['region'])]
        return [dict(common,id='F:comparison:'+suffix,text='区域A均温减区域B均温',value=first['mean']-second['mean'],
                     first_mean=first['mean'],second_mean=second['mean'],first_count=first['valid_count'],
                     second_count=second['valid_count'],region_first=first['region'],region_second=second['region'],
                     statistic_definition=first['statistic_definition'])]
    if name=='get_temperature_point':
        data=point(snapshot,args)
        return [dict(common,id='F:point:'+suffix,text='指定位置的重建温度',**data)]
    if name not in ('find_temperature_extrema','get_region_statistics'):
        raise ValueError('不支持的温度场工具')
    if name=='find_temperature_extrema' and args:
        raise ValueError('极值查询不接受额外参数')
    data=statistics(snapshot,args if name=='get_region_statistics' else None)
    if data['status']=='no_data':
        return [dict(common,id='F:region:'+suffix,text='该区域没有可报告温度',**data)]
    facts=[]
    for key,label in (('maximum','有效网格最高温'),('minimum','有效网格最低温')):
        item=data[key]
        facts.append(dict(common,id='F:'+key+':'+suffix,text=label,**item,
            validity='value',statistic_definition=data['statistic_definition'],
            valid_count=data['valid_count'],resolution=data['resolution'],region=data['region']))
    if name=='get_region_statistics':
        facts.append(dict(common,id='F:region_mean:'+suffix,text='区域有效网格算术均温',value=data['mean'],
            validity='value',statistic_definition=data['statistic_definition'],
            valid_count=data['valid_count'],region=data['region']))
    return facts


def actions_for(snapshot,facts):
    actions=[]
    for fact in facts:
        pos=fact.get('position')
        if pos is None and fact.get('kind')=='value':
            pos={axis:fact[axis] for axis in ('x','y','z')}
        if pos:
            actions.append({'type':'view_snapshot_point','snapshot_id':snapshot['snapshot_id'],
                            'position':pos,'label':'在固定温度场中查看','fact_id':fact['id']})
    return actions[:6]
