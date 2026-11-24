import {afterEach,describe,expect,it,vi} from 'vitest'
import type {AssistantRun,Conversation,SessionEvent} from '../api/assistant'
import {ConversationAssembler} from './conversation'
import {ConversationSession} from './session'
import {readEventStream} from '../api/eventStream'

const run=(id:string,status='running',seq=0):AssistantRun=>({id,question:id,status,event_seq:seq,cycle:1,events:[]})
const checkpoint=(seq:number,r:AssistantRun):SessionEvent=>({seq,type:'turn/checkpoint',time:seq,turn_id:r.id,step_id:`${r.id}:step:1`,data:{run:{...r,event_seq:seq}}})
const activity=(seq:number,turn='a',status='running'):SessionEvent=>({seq,type:'activity/update',time:seq,turn_id:turn,step_id:`${turn}:step:1`,
  data:{id:'tool-1',kind:'tool',status:status as 'running',label:'点温查询'}})
const baseline=(runs:AssistantRun[],cursor=0,timeline:SessionEvent[]=[]):Conversation=>({id:'chat',title:'test',head_run_id:runs.at(-1)!.id,updated_at:0,has_older:false,runs,cursor,timeline})
afterEach(()=>{vi.useRealTimers()})

describe('Conversation 事件组装',()=>{
  it('流式正文按轮次替换，断线快照可恢复，终态拒绝迟到正文',()=>{
    const model=new ConversationAssembler()
    model.append(checkpoint(1,run('a')))
    const answer=(seq:number,text:string,generation=1):SessionEvent=>({seq,type:'answer/update',time:seq,turn_id:'a',step_id:null,data:{text,generation}})
    model.append(answer(2,'温度'))
    expect(model.snapshot()[0]!.run.answer_stream?.text).toBe('温度')
    model.append(answer(3,'温度影响植物生长。'))
    model.append(answer(4,'修订后的回答',2))
    model.append(answer(5,'旧尝试迟到',1))
    expect(model.snapshot()[0]!.run.answer_stream?.text).toBe('修订后的回答')
    const restored=new ConversationAssembler()
    restored.replace(baseline([model.snapshot()[0]!.run],5))
    expect(restored.snapshot()[0]!.run.answer_stream?.text).toBe('修订后的回答')
    restored.append(checkpoint(6,{...restored.snapshot()[0]!.run,status:'cancelled'}))
    restored.append(answer(7,'取消后不覆盖',3))
    expect(restored.snapshot()[0]!.run.answer_stream?.text).toBe('修订后的回答')
  })
  it('历史回放与实时追加一致，重复忽略，拒绝缺口，未变化节点保持身份',()=>{
    const events=[checkpoint(1,run('a')),activity(2),activity(3,'a','completed'),checkpoint(4,run('a','answered')),
      checkpoint(5,run('b')),checkpoint(6,run('b','answered'))]
    const live=new ConversationAssembler(), replay=new ConversationAssembler()
    for(const e of events) live.append(e)
    replay.replace(baseline([run('a','answered',4),run('b','answered',6)],6,events))
    expect(live.snapshot()).toEqual(replay.snapshot())
    const a=live.snapshot()[0]
    live.append(checkpoint(7,run('b','answered')))
    expect(live.snapshot()[0]).toBe(a)
    expect(live.append(events[5]!)).toBe(false)
    expect(()=>live.append(checkpoint(9,run('b')))).toThrow('不连续')
    // A late queued HTTP response cannot regress a completed streamed node.
    live.upsert(run('b','queued',5));expect(live.snapshot()[1]!.run.status).toBe('answered')
  })
  it('检查点可独立恢复，补入旧事件不覆盖新状态、不改变活动节点 ID',()=>{
    const model=new ConversationAssembler()
    model.replace(baseline([run('b','cancelled',8)],8,[activity(7,'b')]))
    expect(model.snapshot()[0]!.activities[0]!.status).toBe('cancelled')
    const stable=model.snapshot()[0]
    model.prepend([checkpoint(1,run('a','answered')),activity(2,'a','completed')])
    expect(model.snapshot().map(t=>t.key)).toEqual(['turn:a','turn:b'])
    expect(model.snapshot()[1]).toBe(stable)
    expect(model.cursor).toBe(8)
  })
  it('同一工具 ID 的进度不会凭最近未完成节点串到另一轮',()=>{
    const model=new ConversationAssembler()
    model.append(checkpoint(1,run('a')));model.append(checkpoint(2,run('b')))
    model.append(activity(3,'a'))
    expect(model.snapshot()[0]!.activities).toHaveLength(1)
    expect(model.snapshot()[1]!.activities).toHaveLength(0)
  })
})

describe('会话连接控制器',()=>{
  it('从原游标重连，切换会话后忽略旧连接迟到事件，离开不取消服务器任务',async()=>{
    vi.useFakeTimers()
    const handlers:((event:SessionEvent)=>void)[]=[], endings:(()=>void)[]=[]
    const stream=vi.fn((_id:string,_after:number,_signal:AbortSignal,receive:(event:SessionEvent)=>void)=>{
      handlers.push(receive);return new Promise<void>(resolve=>endings.push(resolve))
    })
    const publish=vi.fn(), io={stream,run:vi.fn(),conversation:vi.fn()}
    const session=new ConversationSession(io,publish)
    session.open('chat',baseline([run('a')],1))
    handlers[0]!(activity(2));endings[0]!();await vi.advanceTimersByTimeAsync(250)
    expect(stream.mock.calls[1]![1]).toBe(2)
    session.open('other',baseline([run('b')],0));handlers[1]!(checkpoint(3,run('a','answered')))
    expect(publish.mock.calls.at(-1)![0][0].run.id).toBe('b')
    session.close();expect(stream.mock.calls.at(-1)![2].aborted).toBe(true)
    endings.forEach(end=>end())
  })
  it('连续流失败时同步任务快照，恢复流之前保留有效回答',async()=>{
    vi.useFakeTimers()
    const stream=vi.fn().mockRejectedValue(new Error('offline'))
    const io={stream,conversation:vi.fn().mockRejectedValue(new Error('offline')),
      run:vi.fn().mockResolvedValue(run('a','answered',3))}
    const publish=vi.fn(),session=new ConversationSession(io,publish)
    session.open('chat',baseline([run('a')],1))
    await vi.advanceTimersByTimeAsync(2000)
    expect(io.run).toHaveBeenCalledWith('a')
    expect(publish.mock.calls.at(-1)![0][0].run.status).toBe('answered')
    session.close()
  })
})

it('SSE 支持跨 UTF-8 字节、CRLF、多行 data、心跳；断帧不发布',async()=>{
  const data=new TextEncoder().encode(': heartbeat\r\nevent: session\r\ndata: {"text":\r\ndata: "温度"}\r\n\r\n')
  const body=new ReadableStream<Uint8Array>({start(c){for(const byte of data)c.enqueue(new Uint8Array([byte]));c.close()}})
  const receive=vi.fn()
  await readEventStream(body,new AbortController().signal,receive)
  expect(receive).toHaveBeenCalledWith('session','{"text":\n"温度"}')
  const broken=new ReadableStream<Uint8Array>({start(c){c.enqueue(new TextEncoder().encode('data: unfinished'));c.close()}})
  await expect(readEventStream(broken,new AbortController().signal,receive)).rejects.toThrow('不完整')
  expect(receive).toHaveBeenCalledTimes(1)
})
