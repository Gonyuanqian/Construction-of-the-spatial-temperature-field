"""Reproduce corrected G/F training; archive models, metrics and data provenance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pandas as pd
from tfield.data.loader import load_dataset
from tfield.independent_training import PROTOCOL
from tfield.weather_training import arrays, causal_features, train


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--algorithm',choices=['ridge','extra_trees'],default='extra_trees')
    parser.add_argument('--trees',type=int,default=80)
    args=parser.parse_args()
    source=args.dataset.resolve(strict=True)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    def checkpoint(message):
        with (output/'process.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),message=message),ensure_ascii=False)+'\n')
        print(message,flush=True)
    cfg=dict(name='单棚 G/F 纠正训练',spatial_protocol=PROTOCOL,algorithm=args.algorithm,n_estimators=args.trees)
    save('input-manifest.json',dict(dataset=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        options=cfg,house_length_m=6,house_count=3,points_per_house=8,sampling='one_cross_section_per_house'))
    try:
        ds=load_dataset(source)
        report,models=train(ds,cfg,checkpoint)
        save('report.json',report)
        folder=output/'models';folder.mkdir()
        hashes={}
        for key,model in models.items():
            raw=pickle.dumps(model,protocol=pickle.HIGHEST_PROTOCOL)
            (folder/f'{key}.pkl').write_bytes(raw)
            hashes[f'{key}.pkl']=hashlib.sha256(raw).hexdigest()
        save('model-manifest.json',dict(protocol=PROTOCOL,geometry=report['geometry'],files=hashes))
        pd.DataFrame(report['field_validation']['trials']).to_csv(output/'f-search.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(report['field_validation']['per_point']).to_csv(output/'f-b-position-validation.csv',index=False,encoding='utf-8-sig')
        folds=[];points=[];predictions=[]
        weather,_,_=arrays(ds)
        for variant in report['variants']:
            folds.extend(dict(variant=variant['key'],**row) for row in variant['cross_house'])
            points.extend(dict(variant=variant['key'],**row) for row in variant['per_node'])
            node=models[variant['key']]
            pred=node.estimator.predict(causal_features(weather,node.spec))[:,:8]
            for t,values in enumerate(pred):
                predictions.append(dict(variant=variant['key'],timestamp=weather.timestamp.iloc[t].isoformat(),
                    split='training' if t<report['split']['train_frames'] else 'validation',
                    **{f'node_{i+1}':float(v) for i,v in enumerate(values)}))
        pd.DataFrame(folds).to_csv(output/'g-leave-house-out.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(points).to_csv(output/'g-time-validation.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(predictions).to_csv(output/'g-node-predictions.csv',index=False,encoding='utf-8-sig')
        lines=['# 三座独立棚的纠正训练', '', '每座棚长 6 m、宽 2.1 m、高 1.3017 m，每棚只有一个横截面的 8 个测点。',
            '', '训练与评估过程、输入摘要、逐点成绩和三个冻结成品都保存在本目录。', '',
            '| G 版本 | 时间留出 MAE / ℃ | 时间留出 RMSE / ℃ |', '|---|---:|---:|']
        for variant in report['variants']:
            lines.append(f"| {variant['label']} | {variant['validation']['mae']:.4f} | {variant['validation']['rmse']:.4f} |")
        lines+=['', '| G 版本 | 留出棚 | 训练棚 | MAE / ℃ | RMSE / ℃ |','|---|---|---|---:|---:|']
        for row in folds:
            lines.append(f"| {row['variant']} | {row['house_id']} | {', '.join(row['training_houses'])} | {row['mae']:.4f} | {row['rmse']:.4f} |")
        f=report['field_validation']
        lines+=['', f"F 的 B 位置＋未来时段：MAE {f['mae']:.4f} ℃，RMSE {f['rmse']:.4f} ℃。",
                'F 空间验证使用同棚另外 7 个真实测点，不能与仅外部气象的上线成绩混淆。', '', report['note'], '',
                '旧协议成品和业务库均未改写。新成品需要单棚运行协议，不能发布到旧版三棚 24 点链路。']
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        checkpoint('纠正训练完成，模型与评估归档已保存')
        print(output,flush=True)
    except Exception as error:
        save('failure.json',dict(type=type(error).__name__,message=str(error)))
        raise


if __name__=='__main__':main()
