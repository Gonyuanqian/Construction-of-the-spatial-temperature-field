"""在独立联调环境比较 Java 入口与 Python 计算响应，记录简单耗时样本。"""
import argparse
import base64
import json
from pathlib import Path
import statistics
import time
from urllib.request import Request, urlopen


def clean(value):
    if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k!='elapsed_ms'}
    if isinstance(value,list): return [clean(v) for v in value]
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True);p.add_argument('--python-url',required=True)
    p.add_argument('--token-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    def get(base,path,headers=None,body=None):
        started=time.perf_counter()
        request=Request(base+path,headers=headers or {},data=body)
        if body is not None: request.add_header('Content-Type','application/json')
        with urlopen(request,timeout=600) as response: raw=response.read()
        return json.loads(raw),round((time.perf_counter()-started)*1000,2),len(raw)
    if not get(args.base_url,'/ops/info')[0]['acceptance_mode']: raise ValueError('仅允许独立联调环境。')
    workspace=get(args.base_url,'/api/workspaces/default')[0]
    record=next(r for r in get(args.base_url,'/api/datasets')[0]['items'] if r['dataset_id']==workspace['dataset_id'])
    headers={'X-TField-Internal-Key':args.token_file.read_text().strip(),
             'X-TField-Model-Id':str(workspace['model_id']),'X-TField-Result-Id':'none',
             'X-TField-Dataset-Id':record['dataset_id'],'X-TField-Dataset-Signature':record['signature'],
             'X-TField-Dataset-Hash':record['sha256'],
             'X-TField-Dataset-Name':base64.urlsafe_b64encode(record['file'].encode()).decode().rstrip('=')}
    panel=get(args.base_url,'/api/calibration')[0]['panel']
    diagnostic_body=json.dumps({'params':{item['key']:item['current'] for group in ('trend','idw')
                                         for item in panel[group]}}).encode()
    report=[]
    for path in ('/api/health','/api/features','/api/dataset/timeseries','/api/dataset/layer-timeheight?step=20',
                 '/api/dataset/preview?limit=20','/api/field/sections?t_index=0',
                 '/api/field/volume?t_index=0&y_step=3&preset=interactive&monotonic=true',
                 '/api/field/curve?shed=p1&x=1.05&z=0.7','/api/field/compare?shed=p1&t_index=0',
                 '/api/calibration/diagnostics'):
        body=diagnostic_body if path.endswith('/diagnostics') else None
        direct, cold, size=get(args.python_url,path,headers,body)
        gateway, first, _=get(args.base_url,path,body=body)
        equal=clean(direct)==clean(gateway)
        samples={'python':[],'java':[]}
        for _ in range(3):
            samples['python'].append(get(args.python_url,path,headers,body)[1])
            samples['java'].append(get(args.base_url,path,body=body)[1])
        report.append({'path':path,'equal':equal,'payload_bytes':size,'first_python_ms':cold,
                       'first_java_ms':first,'warm_median_ms':{k:statistics.median(v) for k,v in samples.items()}})
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(('PASS ' if equal else 'FAIL ')+path,flush=True)
        if not equal: raise AssertionError('计算载荷不一致：'+path)


if __name__=='__main__':main()
