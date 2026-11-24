import {computed,onUnmounted,ref,watch,type Ref} from 'vue'
import {assistantApi,type AssistantRun} from '../api/assistant'
import {session} from '../api/session'
import {agronomyQuestion,ginsengStages} from '../assistant/agronomy'

/** One explicit request binds one immutable field and one user-selected growth stage. */
export function useAgronomyAdvice(sessionId:Ref<string|null>,active:Ref<boolean>){
 const stage=ref(''),run=ref<AssistantRun|null>(null),error=ref(''),starting=ref(false),connecting=ref(false)
 let alive=true,generation=0,timer:ReturnType<typeof setTimeout>|undefined
 let pending:Parameters<typeof assistantApi.submit>[0]|null=null
 const working=computed(()=>starting.value||!!run.value&&['queued','running'].includes(run.value.status))
 const account=()=>session.user.value?.id??null
 const key=()=>account()?`tfield.ginseng-stage.v1.${session.user.value!.role}.${account()}`:null
 function stopPoll(){if(timer)clearTimeout(timer);timer=undefined}
 function current(mine:number){return alive&&mine===generation}
 function accept(value:AssistantRun,mine:number){if(!current(mine))return;run.value=value;error.value='';connecting.value=false;schedule(mine)}
 function schedule(mine=generation){stopPoll();if(!current(mine)||!active.value||!run.value||!['queued','running'].includes(run.value.status))return
  timer=setTimeout(async()=>{const id=run.value?.id;if(!id)return
   try{const value=await assistantApi.run(id);if(current(mine)&&run.value?.id===id)accept(value,mine)}catch(e){if(current(mine)){error.value=(e as Error).message;connecting.value=true;schedule(mine)}}
  },2000)
 }
 function invalidate(){generation++;stopPoll();run.value=null;pending=null;error.value='';starting.value=false;connecting.value=false}
 watch(()=>`${session.user.value?.role}:${session.user.value?.id}`,()=>{invalidate();stage.value='';try{const value=localStorage.getItem(key()??'');if(ginsengStages.some(s=>s===value))stage.value=value!}catch{/* Optional preference. */}},{immediate:true,flush:'sync'})
 watch(stage,value=>{invalidate();try{const id=key();if(id)localStorage.setItem(id,value)}catch{/* Optional preference. */}},{flush:'sync'})
 watch(sessionId,invalidate,{flush:'sync'})
 watch(active,value=>{if(value)schedule();else stopPoll()})
 async function update(){
  if(!alive||!active.value||!sessionId.value||!stage.value||starting.value)return
  if(run.value&&['queued','running'].includes(run.value.status)){schedule();return}
  const id=sessionId.value,selectedStage=stage.value,user=account(),mine=++generation
  stopPoll();starting.value=true;error.value='';connecting.value=false
  try{
   if(!pending){
    const capability=await assistantApi.capabilities();if(!current(mine)||!active.value)return
    if(!capability.model_configured)throw new Error('AgriSeek 尚未配置，请联系管理员。')
    const snapshot=await assistantApi.snapshot(id);if(!current(mine)||!active.value)return
    if(snapshot.session_id!==id||snapshot.frame_index!==0)throw new Error('温度场快照与当前画布不一致，请刷新后重试。')
    pending={snapshot_id:snapshot.snapshot_id,request_key:crypto.randomUUID(),conversation_id:crypto.randomUUID(),question:agronomyQuestion(selectedStage),crop:'人参',stage:selectedStage,web_search_enabled:true}
   }
   const value=await assistantApi.submit(pending)
   if(current(mine)){pending=null;accept(value,mine)}
   // Context switches hide late replies; server history remains available to its owner.
   else if(alive&&account()===user&&['queued','running'].includes(value.status))void assistantApi.cancel(value.id).catch(()=>{})
  }catch(e){if(current(mine))error.value=(e as Error).message}
  finally{if(current(mine))starting.value=false}
 }
 const link=computed(()=>run.value?.conversation_id?{path:'/assistant',query:{conversation:run.value.conversation_id}}:{path:'/assistant',query:{crop:'人参',...(stage.value?{stage:stage.value}:{})}})
 const terminalMessage=computed(()=>run.value&&!['queued','running'].includes(run.value.status)&&!run.value.result?.claims.length?
  run.value.error_code==='review_stalled'?'本次建议未通过依据核验，暂未发布。可在 AgriSeek 中查看详情并补充现场条件。':run.value.detail||'本次未形成可发布建议，请继续提问或重试。':'')
 onUnmounted(()=>{alive=false;generation++;stopPoll()})
 return{stage,run,error,starting,working,connecting,update,link,terminalMessage}
}
