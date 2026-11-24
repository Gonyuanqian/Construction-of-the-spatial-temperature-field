"""New acceptance cases. Scripted mode tests control flow; --live uses real DeepSeek.

Only synthetic field data and the public literature corpus leave the process.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend')); sys.path.insert(0,str(ROOT/'backend/tests'))
from api.assistant import config, knowledge, routing, runtime, store
from assistant_fixtures import snapshot_body


def reply(message):
    return {'choices':[{'message':message,'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
            'usage':{'total_tokens':100}}


def tool(name,args):
    return reply({'role':'assistant','content':None,'tool_calls':[{'id':str(uuid4()),'type':'function',
                  'function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]})


def scripted_provider(body):
    if 'tools' not in body:
        return reply({'role':'assistant','content':json.dumps({'semantic_verdict':'pass',
            'checks':[{'check':k,'verdict':'pass'} for k in runtime.CHECKS]})})
    data=json.loads(body['messages'][1]['content'])
    facts=[f for f in data['facts'] if f.get('origin')=='reconstructed_grid']
    if facts:
        desired='F:region_mean' if '平均' in data['question'] else 'F:maximum' if '热点' in data['question'] else ''
        fact=next((f for f in facts if f['id'].startswith(desired)),facts[0])
        return tool('finish_answer',{'claims':[{'text':fact['text']+' '+format(fact['value'],'.2f')+' °C',
                    'evidence_ids':[fact['id']]}],'missing_conditions':[]})
    for message in reversed(body['messages']):
        if message['role']=='tool':
            observation=json.loads(message['content'])
            if observation.get('evidence'):
                item=observation['evidence'][0]
                return tool('finish_answer',{'claims':[{'text':item['text'],'evidence_ids':[item['id']]}],
                                            'missing_conditions':[]})
    return tool('search_agri_knowledge',{'query':data['question']})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--cases',default='')
    args=parser.parse_args()
    cases=json.loads((ROOT/'backend/tests/assistant-acceptance-v1.json').read_text(encoding='utf-8'))['cases']
    if args.cases: cases=[c for c in cases if c['id'] in args.cases.split(',')]
    os.environ['TFIELD_ASSISTANT_ACTIVE_KNOWLEDGE_FILE']=str(ROOT/'.local/assistant/knowledge-active.json')
    os.environ['DEEPSEEK_API_KEY']=config.api_key()
    root=ROOT/'.local/assistant'; root.mkdir(parents=True,exist_ok=True)
    results=[]
    original=store.paths.PROJECT
    with tempfile.TemporaryDirectory(prefix='acceptance-',dir=root) as temp:
        store.paths.PROJECT=Path(temp)
        try:
            snapshot=store.snapshot(snapshot_body())
            for case in cases:
                request={k:case[k] for k in ('question','position','region','regions') if k in case}
                request['snapshot_id']=None if case.get('without_snapshot') else snapshot['snapshot_id']
                run,_=store.create_run(str(uuid4()),request)
                runner=runtime.Runner(run,None if args.live else scripted_provider)
                started=time.monotonic()
                try: out=runner.execute()
                except Exception as exc: out=runner.failure(type(exc).__name__)
                citations=out.get('result',{}).get('citations',[])
                if case.get('expected_status'):
                    passed=out['status']==case['expected_status']
                elif case.get('expected_knowledge'):
                    passed=out['status']=='answered' and any(e['id']=='K:'+case['expected_knowledge'] for e in citations)
                else:
                    matched=any(isinstance(e.get('value'),(int,float)) and abs(e['value']-case['expected_value'])<1e-8 for e in citations)
                    passed=out['status']=='answered' and matched
                    if case.get('expected_route'): passed=passed and out.get('result',{}).get('route')==case['expected_route']
                item={'id':case['id'],'question':case['question'],'passed':passed,'status':out['status'],
                      'model_calls':runner.calls,'tool_calls':runner.tool_calls,'evaluations':runner.evaluations,
                      'tokens':runner.tokens,'elapsed_seconds':round(time.monotonic()-started,2),'output':out}
                results.append(item)
                print(json.dumps({k:v for k,v in item.items() if k not in ('output','question')},ensure_ascii=True),flush=True)
        finally: store.paths.PROJECT=original
    report={'mode':'real_deepseek' if args.live else 'scripted_model_real_tools_and_retrieval',
            'fixture':'independent linear field; no user observations',
            'passed':all(r['passed'] for r in results),'passed_count':sum(r['passed'] for r in results),
            'total':len(results),'results':results,
            'limitations':'Scripted reviewer is not semantic validation. Live outputs still need manual content assessment.'}
    output=root/('acceptance-live.json' if args.live else 'acceptance-scripted.json')
    if output.exists():
        archived=root/(output.stem+'-'+str(time.time_ns())+'.json')
        archived.write_bytes(output.read_bytes())
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REPORT',str(output),'PASSED',report['passed_count'],'/',report['total'],flush=True)


if __name__=='__main__': main()
