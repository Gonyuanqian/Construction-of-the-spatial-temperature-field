"""Three-turn acceptance on an independent linear fixture. --live calls DeepSeek."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from api.assistant import config, runtime, store
from assistant_fixtures import snapshot_body
from test_assistant_conversation import provider


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if args.live: os.environ['DEEPSEEK_API_KEY']=config.api_key()
    root=ROOT/'.local/assistant'; root.mkdir(parents=True,exist_ok=True)
    project=store.paths.PROJECT
    results=[]
    with tempfile.TemporaryDirectory(prefix='conversations-',dir=root) as folder:
        store.paths.PROJECT=Path(folder)
        try:
            snap=store.snapshot(snapshot_body()); chat=str(uuid4()); parent=None
            for index,(question,expected) in enumerate([
                ('当前 x=0.5 y=1 z=0.25 的温度是多少？',15),('那 x=1.5 呢？',17),('你回答错了',None)]):
                run,_=store.create_run(str(uuid4()),{'conversation_id':chat,'parent_run_id':parent,
                    'question':question,'snapshot_id':snap['snapshot_id'] if index==0 else None})
                runner=runtime.Runner(run,None if args.live else provider)
                try: out=runner.execute()
                except Exception as exc:
                    code=exc.code if isinstance(exc,runtime.ModelProtocolError) else str(exc) if isinstance(exc,runtime.BudgetExceeded) else type(exc).__name__
                    out=runner.failure('验收执行未完成。',code)
                record=store.get_run(run['id']); parent=run['id']
                citations=(out.get('result') or {}).get('citations',[])
                value=next((e['value'] for e in citations if e.get('id','').startswith('F:point:')),None)
                evaluation=record.get('last_evaluation',{})
                item={'turn':index+1,'status':out['status'],'error_code':out.get('error_code'),
                    'last_check':{'pass':evaluation.get('pass'),'issues':evaluation.get('issues'),
                        'checks':[{k:c.get(k) for k in ('check','verdict')} for c in evaluation.get('evaluation',{}).get('checks',[])]},
                    'history_turns_in_model':record.get('history_turns_in_model',0),'value':value,'expected_value':expected,
                    'previous_run_id':record.get('resolved_context',{}).get('previous_run_id'),
                    'evaluations':runner.evaluations,'model_calls':runner.calls,
                    'thinking':record.get('thinking'),
                    'passed':out['status']=='needs_clarification' if expected is None else out['status']=='answered' and value==expected,
                    'output':out}
                results.append(item)
                print(json.dumps({k:v for k,v in item.items() if k!='output'},ensure_ascii=True),flush=True)
            isolated,_=store.create_run(str(uuid4()),{'conversation_id':str(uuid4()),'parent_run_id':None,'question':'继续'})
            isolated_result=runtime.Runner(isolated,lambda _:(_ for _ in ()).throw(AssertionError('must not call model'))).execute()
        finally: store.paths.PROJECT=project
    report={'mode':'real_deepseek' if args.live else 'scripted_provider',
            'fixture':'independent analytic field, no user observations',
            'passed':all(r['passed'] for r in results), 'new_chat_isolated':isolated_result['status']=='needs_clarification',
            'results':results,'limitations':'Passing fixture cases does not certify agronomic quality or provider reliability.'}
    target=root/('conversation-live.json' if args.live else 'conversation-scripted.json')
    if target.exists(): target.with_name(target.stem+'-'+str(__import__('time').time_ns())+'.json').write_bytes(target.read_bytes())
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPORT',target,'PASSED',sum(r['passed'] for r in results),'/',len(results),flush=True)


if __name__=='__main__':main()
