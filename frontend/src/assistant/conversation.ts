import type { Activity, AssistantRun, Conversation, SessionEvent } from '../api/assistant'

export interface ConversationTurn {key:string; run:AssistantRun; activities:readonly Activity[]}
interface Definition {match:(event:SessionEvent)=>boolean; apply:(model:ConversationAssembler,event:SessionEvent)=>void}
const definitions:readonly Definition[]=[
  {match:e=>['turn/start','turn/checkpoint','turn/end'].includes(e.type),
    apply:(m,e)=>{if(e.data.run && e.data.run.id===e.turn_id) m.upsert(e.data.run)}},
  {match:e=>e.type==='activity/update', apply:(m,e)=>m.activity(e)},
  {match:e=>e.type==='answer/update',apply:(m,e)=>m.answer(e)},
]
const active=(run?:AssistantRun)=>!!run && ['queued','running'].includes(run.status)
const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b)

/** Framework-independent, per-session assembly. Payloads carry their own identities. */
export class ConversationAssembler {
  cursor=0
  private runs=new Map<string,AssistantRun>()
  private activities=new Map<string,{turn:string;seq:number;order:number;value:Activity}>()
  private order:string[]=[]
  private previous=new Map<string,ConversationTurn>()
  upsert(run:AssistantRun) {
    const old=this.runs.get(run.id)
    if(old && (old.event_seq||0)>(run.event_seq||0)) return
    if(!this.order.includes(run.id)) this.order.push(run.id)
    this.runs.set(run.id,same(old,run) ? old! : run)
  }
  activity(event:SessionEvent) {
    const {id,kind,status,label}=event.data
    if(!id || !['model','tool'].includes(kind||'') || !status || !label) return
    const key=`${kind}:${id}`, old=this.activities.get(key)
    if(old && old.seq>=event.seq) {old.order=Math.min(old.order,event.seq);return}
    // Each checkpoint is self-contained, even when the start is outside the window.
    const value:Activity={id,kind:kind!,status,label,
      received_chars:event.data.received_chars,tool_count:event.data.tool_count,evidence_count:event.data.evidence_count}
    this.activities.set(key,{turn:event.turn_id,seq:event.seq,order:Math.min(old?.order??event.seq,event.seq),value:same(old?.value,value) ? old!.value : value})
  }
  answer(event:SessionEvent) {
    const run=this.runs.get(event.turn_id), {generation,text}=event.data
    if(!run || !active(run) || event.seq<=(run.event_seq||0) || !Number.isSafeInteger(generation) || typeof text!=='string' || text.length>20000)return
    if(generation!<(run.answer_stream?.generation||0))return
    this.upsert({...run,event_seq:event.seq,answer_stream:{generation:generation!,text}})
  }
  private fold(event:SessionEvent) {for(const def of definitions) if(def.match(event)) def.apply(this,event)}
  replace(snapshot:Conversation) {
    const keep=new Set(snapshot.runs.map(r=>r.id))
    for(const id of this.runs.keys()) if(!keep.has(id)) this.runs.delete(id)
    this.order=snapshot.runs.map(r=>r.id)
    for(const run of snapshot.runs) this.upsert(run)
    this.activities.clear()
    for(const event of snapshot.timeline||[]) this.fold(event)
    this.cursor=snapshot.cursor||0
  }
  append(event:SessionEvent) {
    if(event.seq<=this.cursor) return false
    if(event.seq!==this.cursor+1) throw new Error('会话事件不连续，需要重新同步')
    this.fold(event); this.cursor=event.seq; return true
  }
  prepend(events:SessionEvent[]) {
    const existing=new Set(this.order)
    for(const e of [...events].sort((a,b)=>a.seq-b.seq)) {
      if(e.seq>this.cursor) throw new Error('历史事件超出当前窗口')
      this.fold(e)
    }
    this.order=[...this.order.filter(id=>!existing.has(id)),...this.order.filter(id=>existing.has(id))]
  }
  snapshot():readonly ConversationTurn[] {
    return this.order.map(id=>{
      const run=this.runs.get(id)!
      const activities=[...this.activities.values()].filter(a=>a.turn===id).sort((a,b)=>a.order-b.order)
        .map(a=>a.value.status==='running' && !active(run) ? {...a.value,status:run.status==='cancelled' ? 'cancelled' as const : 'interrupted' as const} : a.value)
      const old=this.previous.get(id)
      if(old?.run===run && same(old.activities,activities)) return old
      const turn={key:`turn:${id}`,run,activities}; this.previous.set(id,turn); return turn
    })
  }
}

export { active as isActiveRun }
