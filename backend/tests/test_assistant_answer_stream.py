import json
from uuid import uuid4
import httpx
import pytest
from api.assistant import runtime,store
from api.assistant.model_stream import answer_preview,collect
from test_assistant_stream import run,frames,delta,part
from test_assistant_conversation import provider


def test_partial_json_preview_only_extracts_readable_claims():
    assert answer_preview('{"claims":[{"text":"温度\\n影响生长')=='温度\n影响生长'
    assert answer_preview('{"claims":[{"text":"温度\\u6e')==''
    assert answer_preview('{"evidence_ids":["F:sensor:1"]}')==''
    preview=[]
    with pytest.raises(Exception):
        collect(frames(delta({'reasoning_content':'PRIVATE','tool_calls':[part(0,'{"claims":[{"text":"公开段落','a','finish_answer')]}),done=False),lambda:None,retain_reasoning=True,answer_progress=preview.append)
    assert preview==['公开段落']


def test_replay_cancel_and_stale_attempt_cannot_overwrite(run):
    store.stream_answer(run['id'],2,'当前回答')
    store.stream_answer(run['id'],1,'过期片段')
    saved=store.get_conversation(run['conversation_id'])
    assert saved['runs'][0]['answer_stream']['text']=='当前回答'
    assert saved['timeline'][-1]['type']=='answer/update'
    store.cancel(run['id'])
    store.stream_answer(run['id'],3,'迟到回答')
    assert store.get_run(run['id'])['answer_stream']['text']=='当前回答'


def test_real_http_path_publishes_before_tool_settlement_and_hides_reasoning(run,monkeypatch):
    observed=[]
    class Stream(httpx.SyncByteStream):
        def __init__(self,chunks,check=False):self.chunks,self.check=chunks,check
        def __iter__(self):
            for i,chunk in enumerate(self.chunks):
                yield (chunk+'\n').encode()
                if self.check and i==1:
                    observed.append(store.get_run(run['id']).get('answer_stream',{}).get('text'))
    def upstream(request):
        body=json.loads(request.content)
        message=provider(body)['choices'][0]['message']
        if 'tools' in body:
            call=message['tool_calls'][0]; args=call['function']['arguments']
            cut=args.index('evidence_ids')-2
            # First event exposes readable text while arguments are still incomplete.
            chunks=frames(delta({'reasoning_content':'PRIVATE','tool_calls':[part(0,args[:cut],call['id'],'finish_answer')]}),
                delta({'tool_calls':[part(0,args[cut:])]},'tool_calls'))
            return httpx.Response(200,stream=Stream(chunks,True))
        return httpx.Response(200,stream=Stream(frames(delta({'content':message['content']},'stop'))))
    monkeypatch.setattr(runtime.config,'api_key',lambda:'test')
    client_factory=httpx.Client
    monkeypatch.setattr(runtime.httpx,'Client',lambda **kw:client_factory(transport=httpx.MockTransport(upstream)))
    runner=runtime.Runner(run);runner.client=runtime.httpx.Client()
    assert runner.execute()['status']=='answered'
    assert observed and all(observed)
    assert 'PRIVATE' not in store.packed(store.get_conversation(run['conversation_id']))


@pytest.mark.parametrize('status,retries',[(429,2),(503,2),(401,1)])
def test_only_transient_http_errors_retry(run,monkeypatch,status,retries):
    calls=[]
    def upstream(request):
        calls.append(1)
        if len(calls)==1:return httpx.Response(status)
        return httpx.Response(200,text='\n'.join(frames(delta({'content':'公开回答'},'stop')))+'\n')
    monkeypatch.setattr(runtime.config,'api_key',lambda:'test')
    client_factory=httpx.Client
    monkeypatch.setattr(runtime.httpx,'Client',lambda **kw:client_factory(transport=httpx.MockTransport(upstream)))
    runner=runtime.Runner(run);runner.client=runtime.httpx.Client()
    if status==401:
        with pytest.raises(httpx.HTTPStatusError):runner.model([{'role':'user','content':'test'}])
    else:assert runner.model([{'role':'user','content':'test'}])['content']=='公开回答'
    assert len(calls)==retries
    if runner.client:runner.client.close()
