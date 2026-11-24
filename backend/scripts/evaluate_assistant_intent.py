"""Real-provider capability-routing acceptance, using independent fixture observations."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from api.assistant import config,runtime,store
from assistant_fixtures import snapshot_body


def main():
    os.environ['DEEPSEEK_API_KEY']=config.api_key()
    folder=ROOT/'.local/assistant'
    original=store.paths.PROJECT
    cases=[]
    with tempfile.TemporaryDirectory(prefix='capability-acceptance-',dir=folder) as temporary:
        store.paths.PROJECT=Path(temporary)
        try:
            snap=store.snapshot(snapshot_body())
            for question,bound in [('你只能切面的测点吗，非切面的测点不知道吗',True),
                ('你只能处理切面吗？',False)]:
                run=store.create_run(str(uuid4()),{'question':question,'conversation_id':str(uuid4()),
                    'snapshot_id':snap['snapshot_id'] if bound else None,'web_search_enabled':False})[0]
                runner=runtime.Runner(run)
                started=time.monotonic()
                try:out=runner.execute()
                except Exception as exc:
                    code=exc.code if isinstance(exc,runtime.ModelProtocolError) else str(exc) if isinstance(exc,runtime.BudgetExceeded) else type(exc).__name__
                    out=runner.failure('验收未完成。',code)
                record=store.get_run(run['id'])
                result=out.get('result') or {}
                ids=[e['id'] for e in result.get('citations',[])]
                case={'question':question,'snapshot_bound':bound,'status':out['status'],
                    'route':record.get('route'),'error_code':out.get('error_code'),
                    'elapsed_seconds':round(time.monotonic()-started,2),'evaluations':runner.evaluations,
                    'model_calls':runner.calls,'thinking':record.get('thinking'),
                    'passed':out['status']=='answered' and record.get('route')=='capability' and
                        not runner.field_facts and not any(e.startswith('F:sensor:') for e in ids),
                    'output':out}
                cases.append(case)
                print(json.dumps({k:v for k,v in case.items() if k!='output'},ensure_ascii=True),flush=True)
        finally:store.paths.PROJECT=original
    target=folder/'intent-capability-live.json'
    if target.exists():target.with_name(target.stem+'-'+str(time.time_ns())+'.json').write_bytes(target.read_bytes())
    target.write_text(json.dumps({'passed':all(c['passed'] for c in cases),'cases':cases,
        'fixture':'independent analytic field; no user greenhouse observations'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPORT',target,flush=True)


if __name__=='__main__':main()
