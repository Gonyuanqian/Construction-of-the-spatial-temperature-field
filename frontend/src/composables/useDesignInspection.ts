import {computed,onUnmounted,ref,watch,type Ref} from 'vue'
import {session} from '../api/session'
import type {AssistantCapabilities} from '../api/assistant'
import {designInspectionApi,type DesignInspection} from '../api/designInspection'

export function useDesignInspection(designId:Ref<string|null>,revision:Ref<number|null>,dirty:Ref<boolean>,active:Ref<boolean>){
 const capability=ref<AssistantCapabilities|null>(null),inspection=ref<DesignInspection|null>(null),history=ref<DesignInspection[]>([])
 const error=ref(''),starting=ref(false),loading=ref(false),connecting=ref(false)
 let alive=true,generation=0,timer:ReturnType<typeof setTimeout>|undefined,pending:string|null=null
 const working=computed(()=>starting.value||!!inspection.value?.run&&['queued','running'].includes(inspection.value.run.status))
 const stale=computed(()=>!!inspection.value&&(dirty.value||inspection.value.revision!==revision.value))
 const canStart=computed(()=>!!designId.value&&!!revision.value&&!dirty.value&&!working.value&&!loading.value&&!!capability.value?.model_configured)
 const current=(n:number)=>alive&&generation===n
 function stop(){clearTimeout(timer);timer=undefined}
 function accept(value:DesignInspection,n:number){if(!current(n))return;if(value.design_id!==designId.value)throw new Error('检验记录与当前方案不一致。');inspection.value=value;pending=!value.run&&value.revision===revision.value?value.request_key:null;error.value='';connecting.value=false;poll(n)}
 function poll(n=generation){stop();if(!current(n)||!active.value||!inspection.value?.run||!['queued','running'].includes(inspection.value.run.status))return
  timer=setTimeout(async()=>{const value=inspection.value;if(!value)return;try{accept(await designInspectionApi.get(value.design_id,value.id),n)}catch(e){if(current(n)){error.value=(e as Error).message;connecting.value=true;poll(n)}}},2000)
 }
 async function load(){const n=++generation;stop();starting.value=false;inspection.value=null;history.value=[];pending=null;error.value='';connecting.value=false;loading.value=true;const id=designId.value
  try{const tasks=await Promise.allSettled([designInspectionApi.capabilities(),id?designInspectionApi.latest(id):Promise.resolve({inspection:null}),id?designInspectionApi.history(id):Promise.resolve([])])
   if(!current(n))return
   if(tasks[0].status==='fulfilled')capability.value=tasks[0].value
   if(tasks[2].status==='fulfilled')history.value=tasks[2].value
   if(tasks[1].status==='fulfilled'&&tasks[1].value.inspection)accept(tasks[1].value.inspection,n)
   error.value=tasks.filter(t=>t.status==='rejected').map(t=>(t as PromiseRejectedResult).reason?.message||'检验服务暂时不可用。').join('；')
  }catch(e){if(current(n))error.value=(e as Error).message}finally{if(current(n))loading.value=false}
 }
 async function refreshHistory(n:number,id:string){try{const values=await designInspectionApi.history(id);if(current(n))history.value=values}catch{/* The running inspection is independently polled. */}}
 async function start(){if(!canStart.value||!designId.value||!revision.value)return;const n=generation,id=designId.value,version=revision.value;pending??=crypto.randomUUID();starting.value=true;error.value=''
  try{const value=await designInspectionApi.submit(id,version,pending);if(current(n)){if(value.revision!==version)throw new Error('检验任务与当前保存版本不一致。');accept(value,n);void refreshHistory(n,id)}}
  catch(e){if(current(n))error.value=(e as Error).message}finally{if(current(n))starting.value=false}
 }
 async function select(id:string){if(!designId.value||starting.value)return;const n=++generation;stop();loading.value=true;error.value='';try{accept(await designInspectionApi.get(designId.value,id),n)}catch(e){if(current(n))error.value=(e as Error).message}finally{if(current(n))loading.value=false}}
 async function cancel(){if(!inspection.value)return;const n=generation,value=inspection.value;try{accept(await designInspectionApi.cancel(value.design_id,value.id),n)}catch(e){if(current(n))error.value=(e as Error).message}}
 watch([designId,revision,()=>session.user.value?.id],()=>{capability.value=null;void load()},{immediate:true,flush:'sync'})
 watch(active,value=>{if(value)poll();else stop()})
 onUnmounted(()=>{alive=false;generation++;stop()})
 return{capability,inspection,history,error,starting,loading,connecting,working,stale,canStart,start,load,select,cancel}
}
