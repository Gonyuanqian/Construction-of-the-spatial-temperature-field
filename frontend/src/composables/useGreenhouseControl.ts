import {computed,onUnmounted,ref,watch} from 'vue'
import {ApiError,getJson} from '../api/client'
import {session} from '../api/session'
import {designsApi,type DesignRecord} from '../api/greenhouseDesigns'
import {controlApi,type ControlOverview,type ControlTask,type ControlPlan,type ControlEvent} from '../api/greenhouseControl'
import type {LiveStatus} from '../api/types'

/** The server owns running devices/jobs. Page polling only reads existing state. */
export function useGreenhouseControl(linkedDesign=''){
 const designs=ref<DesignRecord[]>([]),selected=ref(''),overview=ref<ControlOverview|null>(null),tasks=ref<ControlTask[]>([]),plans=ref<ControlPlan[]>([]),events=ref<ControlEvent[]>([]),alarms=ref<ControlEvent[]>([])
 const loading=ref(false),busy=ref(false),needsSetup=ref(false),error=ref(''),message=ref(''),modelReady=ref(false),capabilityError=ref(''),monitoring=ref<LiveStatus|null>(null),updatedAt=ref('')
 let alive=true,generation=0,reads=0,timer:ReturnType<typeof setTimeout>|undefined
 const pending=new Map<string,string>()
 const record=computed(()=>designs.value.find(d=>d.id===selected.value)??null)
 const blocked=computed(()=>!overview.value||overview.value.paused||overview.value.design_stale)
 const storageKey=()=>`tfield.control.selected.${session.user.value?.id??'anonymous'}`
 const current=(n:number)=>alive&&n===generation
 function stop(){clearTimeout(timer);timer=undefined}
 function poll(){stop();if(!alive||!selected.value||!overview.value||document.hidden)return;timer=setTimeout(async()=>{if(!busy.value)await refresh();else poll()},4000)}
 async function refresh(){
  stop();const id=selected.value,n=generation,r=++reads;if(!id)return;loading.value=true
  try{
   const value=await controlApi.overview(id);if(!current(n)||r!==reads)return;if(value.design_id!==id)throw new Error('设备状态与所选温室不一致，请重新刷新。');overview.value=value;needsSetup.value=false
   const all=await Promise.allSettled([controlApi.tasks(id),controlApi.plans(id),controlApi.events(id),controlApi.events(id,true)])
   if(!current(n)||r!==reads)return
   if(all[0].status==='fulfilled')tasks.value=all[0].value.items
   if(all[1].status==='fulfilled')plans.value=all[1].value.items
   if(all[2].status==='fulfilled')events.value=all[2].value.items
   if(all[3].status==='fulfilled')alarms.value=all[3].value.items
   const failed=all.find(v=>v.status==='rejected');error.value=failed?.status==='rejected'?(failed.reason as Error).message:'';updatedAt.value=new Date().toISOString()
  }catch(e){if(current(n)&&r===reads){if(e instanceof ApiError&&e.status===404){overview.value=null;needsSetup.value=true}else error.value=(e as Error).message}}
  finally{if(current(n)&&r===reads){loading.value=false;poll()}}
 }
 async function context(){const id=selected.value,n=generation;if(!id)return
  const values=await Promise.allSettled([controlApi.capabilities(id),getJson<LiveStatus>('/api/live/status')]);if(!current(n))return
  modelReady.value=values[0].status==='fulfilled'&&values[0].value.model_configured
  capabilityError.value=values[0].status==='rejected'?(values[0].reason as Error).message:''
  monitoring.value=values[1].status==='fulfilled'?values[1].value:null
 }
 async function load(){
  const n=generation;error.value='';loading.value=true
  try{const result=await designsApi.list();if(!current(n))return;designs.value=result.items
   let previous='';try{previous=sessionStorage.getItem(storageKey())??''}catch{/* Session storage is optional. */}
   const available=new Set(result.items.map(d=>d.id))
   const next=[selected.value,linkedDesign,previous].find(id=>available.has(id))??result.items[0]?.id??''
   if(next===selected.value){await refresh();await context()}else selected.value=next
  }catch(e){if(current(n))error.value=(e as Error).message}finally{if(current(n))loading.value=false}
 }
 async function mutation(label:string,identity:unknown,work:(id:string,key:string)=>Promise<unknown>){
  if(busy.value||!selected.value)return false
  const n=generation,id=selected.value,signature=JSON.stringify([id,label,identity]);let key=pending.get(signature);if(!key){key=crypto.randomUUID();pending.set(signature,key)}
  busy.value=true;error.value='';message.value='';stop()
  try{await work(id,key);pending.delete(signature);if(current(n)){message.value=label+'。';await refresh();void context()}return current(n)}
  catch(e){if(current(n)){error.value=(e as Error).message;await refresh();error.value=(e as Error).message}return false}
  finally{if(current(n)){busy.value=false;poll()}}
 }
 async function setup(){const r=record.value;if(!r)return;await mutation('模拟设备已初始化',{revision:r.revision},id=>controlApi.setup(id,r.revision))}
 async function houseAction(action:'stop-all'|'resume'|'rebind'){
  let revision:number|undefined
  if(action==='rebind'){try{const r=await designsApi.get(selected.value);revision=r.revision;designs.value=designs.value.map(v=>v.id===r.id?r:v)}catch(e){error.value=(e as Error).message;return}}
  await mutation(action==='stop-all'?'已停止全部设备并暂停任务':action==='resume'?'控制已恢复，旧任务仍保持暂停':'已绑定新版本，请核对设备后恢复控制',{action,revision},(id,key)=>controlApi.house(id,action,{request_key:key,...(revision?{revision}:{})}))
 }
 function reset(){stop();generation++;reads++;pending.clear();selected.value='';designs.value=[];overview.value=null;tasks.value=[];plans.value=[];events.value=[];alarms.value=[];monitoring.value=null;modelReady.value=false;error.value='';message.value='';busy.value=false;needsSetup.value=false;updatedAt.value='';void load()}
 watch(selected,id=>{stop();generation++;overview.value=null;tasks.value=[];plans.value=[];events.value=[];alarms.value=[];needsSetup.value=false;modelReady.value=false;capabilityError.value='';monitoring.value=null;busy.value=false;error.value='';message.value='';if(id){try{sessionStorage.setItem(storageKey(),id)}catch{/* Optional. */}void refresh().then(()=>context())}},{flush:'sync'})
 watch(()=>session.revision.value,reset,{immediate:true,flush:'sync'})
 const visible=()=>{if(!document.hidden)void refresh()}
 document.addEventListener('visibilitychange',visible)
 onUnmounted(()=>{alive=false;generation++;stop();document.removeEventListener('visibilitychange',visible)})
 return{designs,selected,record,overview,tasks,plans,events,alarms,loading,busy,needsSetup,error,message,modelReady,capabilityError,monitoring,updatedAt,blocked,load,refresh,context,mutation,setup,houseAction}
}
