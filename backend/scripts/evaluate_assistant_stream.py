"""Measure real public-answer delivery using an isolated conversation store."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from api.assistant import config,runtime,store


def main():
    os.environ['DEEPSEEK_API_KEY']=config.api_key()
    folder=ROOT/'.local/assistant';folder.mkdir(parents=True,exist_ok=True)
    original=store.stream_answer
    old_root=os.environ.get('TFIELD_ASSISTANT_STATE_ROOT')
    started=time.monotonic();first=[]
    def observe(identifier,generation,text):
        original(identifier,generation,text)
        if text and not first:first.append(time.monotonic()-started)
    try:
        with tempfile.TemporaryDirectory(prefix='answer-stream-',dir=folder) as temporary:
            os.environ['TFIELD_ASSISTANT_STATE_ROOT']=temporary
            store.stream_answer=observe
            run=store.create_run(str(uuid4()),{'conversation_id':str(uuid4()),
                'question':'简要解释温度如何影响植物生长，不需要检索。','web_search_enabled':False})[0]
            runner=runtime.Runner(run)
            try:out=runner.execute()
            except Exception as exc:
                code=exc.code if isinstance(exc,runtime.ModelProtocolError) else str(exc) if isinstance(exc,runtime.BudgetExceeded) else type(exc).__name__
                out=runner.failure('实测未完成。',code)
            elapsed=time.monotonic()-started
            chat=store.get_conversation(run['conversation_id'])
            report={'status':out['status'],'error_code':out.get('error_code'),'first_text_seconds':round(first[0],3) if first else None,
                'total_seconds':round(elapsed,3),'model_calls':runner.calls,'evaluations':runner.evaluations,
                'answer_events':sum(e['type']=='answer/update' for e in chat['timeline']),
                'passed':out['status']=='answered' and bool(first) and first[0]<elapsed and runner.evaluations>=2,
                'fixture':'public knowledge only; isolated DB; no user observations'}
    finally:
        store.stream_answer=original
        if old_root is None:os.environ.pop('TFIELD_ASSISTANT_STATE_ROOT',None)
        else:os.environ['TFIELD_ASSISTANT_STATE_ROOT']=old_root
    (folder/'answer-stream-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
