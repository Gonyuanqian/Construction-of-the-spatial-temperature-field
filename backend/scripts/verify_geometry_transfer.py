"""Validate experimental dimension transfer using existing frozen G/F artifacts."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import pickle
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from tfield.geometry_transfer import HouseDimensions,build_transferred_volume,POLICY
from tfield.data.loader import load_dataset
from tfield.independent_training import GEOMETRY,local_positions
from tfield.weather_training import arrays,causal_features

CASES=[('reference',6,2.1,1.3017),('half_all',3,1.05,.65085),('double_length',12,2.1,1.3017),
    ('wider_taller',8,3,1.8),('double_section',6,4.2,2.6034),('height_only',6,2.1,2.2),
    ('long_house',30,3,2),('large_house',60,6,3)]


def draw_gallery(output):
    """One physical enclosure per panel; copied sections are illustrations, not new observations."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    cases=json.loads((output/'cases.json').read_text('utf-8'))
    payload=json.loads((output/'payloads/reference.json').read_text('utf-8'))
    with np.load(output/'reference.npz') as reference:
        x,z,section=reference['x'],reference['z'],reference['sections'][-1]
    norm=plt.Normalize(payload['vmin'],payload['vmax']);cmap=plt.get_cmap('turbo')
    colors=cmap(norm(section));colors[~np.isfinite(section),3]=0
    for ix,iz in payload['stripes']:colors[iz,ix,3]=0
    fig=plt.figure(figsize=(18,8));fig.subplots_adjust(left=.01,right=.89,top=.88,bottom=.1,wspace=.02,hspace=0)
    for number,case in enumerate(cases):
        L,W,H=case['dimensions'];dim=HouseDimensions(L,W,H);ax=fig.add_subplot(2,4,number+1,projection='3d')
        X,Z=np.meshgrid(x/2.1*W,z/1.3017*H)
        for y in (0,L/2,L):
            ax.plot_surface(np.full(X.shape,y),X,Z,facecolors=colors,shade=False,rstride=1,cstride=1,alpha=.85)
        roofx=np.linspace(0,W,100)
        for y in np.linspace(0,L,7):ax.plot(np.full(100,y),roofx,dim.roof(roofx),color='gray',linewidth=.7,alpha=.55)
        for cross in (0,W*.25,W*.5,W*.75,W):
            ax.plot([0,L],[cross,cross],[float(dim.roof(cross))]*2,color='gray',linewidth=.7,alpha=.55)
        ax.plot([0,L,L,0,0],[0,0,W,W,0],[0]*5,color='gray',linewidth=.8)
        ax.set(xlim=(0,L),ylim=(0,W),zlim=(0,H));ax.set_box_aspect((L,W,H))
        ax.view_init(elev=22,azim=-62);ax.set_axis_off();ax.set_title(f'{L:g} × {W:g} × {H:g} m',fontsize=12,pad=-10)
    fig.suptitle('不同尺寸构场原型：参考横截面映射＋纵向均匀假设',fontsize=17)
    fig.text(.45,.04,'尺寸为长 × 宽 × 高；彩色截面为同一模型截面的复制，并非多个实测断面。跨尺寸温度精度尚未验证。',ha='center',fontsize=12)
    cax=fig.add_axes([.93,.2,.012,.55]);fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cax,label='模型温度 / ℃')
    fig.savefig(output/'dimension-gallery.png',dpi=160,bbox_inches='tight');plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    reference=args.reference.resolve(strict=True);output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False);(output/'payloads').mkdir()
    manifest=json.loads((reference/'input-manifest.json').read_text('utf-8'))
    models=json.loads((reference/'model-manifest.json').read_text('utf-8'))
    training=json.loads((reference/'report.json').read_text('utf-8'))
    source=Path(manifest['dataset'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['sha256']
    loaded={}
    for key in ('current','field'):
        raw=(reference/'models'/f'{key}.pkl').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==models['files'][f'{key}.pkl']
        loaded[key]=pickle.loads(raw)
    weather,_,_=arrays(load_dataset(source))
    holdout=weather.iloc[training['split']['train_frames']:]
    indices=list(dict.fromkeys([int(holdout.bg_temp.idxmin()),int(holdout.bg_temp.sort_values().index[len(holdout)//2]),int(holdout.bg_light.idxmax())]))
    predictions=loaded['current'].estimator.predict(causal_features(weather,loaded['current'].spec))[:,:8]
    provenance=dict(created_at=datetime.now(timezone.utc).isoformat(),policy=POLICY,
        dataset_sha256=manifest['sha256'],model_files=models['files'],reference=str(reference),
        geometry=GEOMETRY,selected_indices=indices,weather=weather.loc[indices].assign(timestamp=lambda df:df.timestamp.astype(str)).to_dict('records'))
    save=lambda name,value:(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    save('input-manifest.json',provenance)
    rows=[];case_payloads=[]
    frames={i:weather.iloc[[i]].reset_index(drop=True) for i in indices}
    baselines={i:build_transferred_volume(loaded['field'],frames[i],predictions[i],HouseDimensions(6,2.1,1.3017),allow_assumptions=True) for i in indices}
    for name,L,W,H in CASES:
        dim=HouseDimensions(L,W,H);checks=[];sections=[]
        begin=time.perf_counter()
        for i in indices:
            field=build_transferred_volume(loaded['field'],frames[i],predictions[i],dim,allow_assumptions=True,source_ref=models['files']['field.pkl'])
            baseline=baselines[i];sections.append(field.section)
            np.testing.assert_array_equal(field.mask,baseline.mask)
            np.testing.assert_allclose(field.section,baseline.section,equal_nan=True,atol=1e-10)
            assert np.isfinite(field.section[field.mask]).all() and np.isnan(field.section[~field.mask]).all()
            assert field.x[-1]==W and field.y[-1]==L and field.z[-1]==H
            query=field.query(.5*W,.37*L,.5*H)
            reference_query=baseline.query(.5*2.1,.37*6,.5*1.3017)
            assert query['kind']=='value' and abs(query['value']-reference_query['value'])<1e-9
            longitudinal_difference=abs(field.query(.5*W,.93*L,.5*H)['value']-query['value'])
            assert longitudinal_difference<1e-9
            assert field.query(-.01,0,0)['kind']=='outside'
            assert field.query(W/2,L+.01,H/2)['kind']=='outside'
            assert field.query(0,L/2,H)['kind']=='outside'
            assert field.query(W/2,L/2,.95*H)['kind']=='unmeasured'
            # Virtual anchors scale in physical coordinates but carry identical model predictions.
            physical_nodes=local_positions()*np.array([W,H])
            relative=physical_nodes/np.array([W,H])
            np.testing.assert_allclose(loaded['field'].predict(frames[i],predictions[i][None,:],target_positions=relative)[0],predictions[i],atol=1e-6)
            payload=field.payload();assert all(not p['measured'] for p in payload['planes'])
            assert abs(max(p[1] for p in payload['arch'])-H)<1e-10
            checks.append(dict(frame=i,time=field.timestamp,finite_inside=True,outside_is_missing=True,
                query_value=query['value'],normalized_grid_max_difference=float(np.nanmax(np.abs(field.section-baseline.section))),
                query_difference=abs(query['value']-reference_query['value']),longitudinal_difference=longitudinal_difference,grid_values=len(field.x)*len(field.y)*len(field.z)))
            if i==indices[-1]:
                save(f'payloads/{name}.json',payload)
                case_payloads.append(dict(id=name,dimensions=[L,W,H],payload=f'payloads/{name}.json',query=query))
        np.savez_compressed(output/f'{name}.npz',x=field.x,y=field.y,z=field.z,sections=np.stack(sections),weather_indices=indices)
        rows.append(dict(case=name,length_m=L,width_m=W,height_m=H,checks=checks,
            passed=True,elapsed_s=time.perf_counter()-begin,temperature_accuracy_mae=None,accuracy_validated=False))
        print(f'{name}: {L} × {W} × {H} m, geometry/query PASS; thermal accuracy NOT VALIDATED',flush=True)
    # Evidence that loading/building did not rewrite or retune the frozen models.
    for key in ('current','field'):
        assert hashlib.sha256((reference/'models'/f'{key}.pkl').read_bytes()).hexdigest()==models['files'][f'{key}.pkl']
    result=dict(policy=POLICY,engineering_passed=True,case_count=len(rows),weather_count=len(indices),results=rows,
        thermal_accuracy_validated=False,source_artifacts_unchanged=True,production_enabled=False,
        conclusion='可生成同类归一化拱形的不同尺寸估算场；温度为参考横截面映射并沿长度均匀展开，不能据此证明跨尺寸预测精度。')
    save('verification.json',result);save('cases.json',case_payloads)
    pd.DataFrame([{k:v for k,v in row.items() if k!='checks'} for row in rows]).to_csv(output/'case-summary.csv',index=False,encoding='utf-8-sig')
    lines=['# 不同棚体尺寸的构场验证','',result['conclusion'],'',
        f"固定已训练 G/F 成品，使用 {len(indices)} 个尾部留出时刻，验证 {len(rows)} 个尺寸组合。输入摘要、过程、网格与可渲染载荷均在本目录。",'',
        '| 棚体长×宽×高 / m | 几何/掩膜 | 查询/同源点 | 三维数据生成 | 温度精度 |','|---|---|---|---|---|']
    for row in rows:lines.append(f"| {row['length_m']:g} × {row['width_m']:g} × {row['height_m']:g} | 通过 | 通过 | 通过 | 无对应尺寸实测，未验证 |")
    lines+=['','## 验证含义','',
        '计算使用 x/W、z/H 对应的参考相对坐标，长度方向采用均匀假设。相同相对位置、相同气象下，不同尺寸的温度场数值一致；本轮已逐网格验证这一点。因此它是可运行的空间映射，而不是模型学会了尺寸改变后的通风或热交换。',
        '', '宽高独立变化时保留基准拱形的归一化轮廓，缩放后的屋面可能不再是圆弧；不代表任意棚型。',
        '', '八个虚拟点不带真实纵向位置，展示中壳体放在长度中点仅用于几何摆放；所有生成片都标记为非实测。超过原测点相对高度覆盖的查询返回 unmeasured，拱外没有温度，边界缺失角点不补值。',
        '', '实验均未修改在线发布能力、模型适用尺寸或业务数据库。正式页面仍受当前运行协议限制。',
        '', '## 尚缺的精度验证','',
        '现有数据为三座同尺寸棚，每棚一个横截面。缺少其他尺寸棚及棚内纵向截面的独立真值，本轮不会给跨尺寸 MAE/RMSE 或宣称可用尺寸范围。',
        '', '下一轮应采集目标尺寸棚的实测温度，在整棚/整尺寸留出条件下比较参考映射基线和加入结构条件的新模型；长度方向至少需要多个真实截面。不能把映射后的虚拟温度当真值评价映射本身。']
    (output/'report.md').write_text('\n'.join(lines)+'\n','utf-8')
    draw_gallery(output)
    print(output,flush=True)


if __name__=='__main__':main()
