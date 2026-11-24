import {computed,effectScope,inject,onScopeDispose,provide,reactive,ref,watch,type InjectionKey} from 'vue'
import {gTrainingApi,type GInfo,type GJob,type TrainingTarget,type WorkbenchResult} from '../api/weatherTraining'
import {config,defaultForm} from '../training/workbench'
import {useDataset} from './useDataset'
function createWorkspace(){
 const target=ref<TrainingTarget>('field'),info=ref<GInfo|null>(null),jobs=reactive<{field:GJob|null;mapping:GJob|null}>({field:null,mapping:null})
 const forms=reactive({field:defaultForm('field'),mapping:defaultForm('mapping')})
 const loading=ref(false),submitting=ref(false),saving=ref(false),error=ref(''),savedNotice=ref(''),running=ref<GJob|null>(null)
 const busy=computed(()=>submitting.value||!!running.value||saving.value),form=computed(()=>forms[target.value]),job=computed(()=>jobs[target.value])
 const result=computed(()=>job.value?.result?.protocol_version===3?job.value.result as unknown as WorkbenchResult:null)
 let alive=true,sequence=0,viewSequence=0,timer:ReturnType<typeof setTimeout>|undefined,pending:{body:string;key:string}|null=null
 watch(target,()=>viewSequence++,{flush:'sync'})
 const kind=(job:GJob)=>job.options.workbench?.target
 function accept(value:GJob,restore=false){const key=kind(value);if(!key){running.value=value.state==='running'?value:null;return}
  const finished=value.state==='done'&&jobs[key]?.id===value.id&&jobs[key]?.state==='running'
  jobs[key]=value
  if(value.state==='running')running.value=value
  else if(running.value?.id===value.id)running.value=null
  const report=value.result as unknown as WorkbenchResult|null
  if(restore){const w=value.options.workbench!,f=forms[key];f.prediction_target=w.prediction_target??'absolute';f.algorithm=w.algorithm;f.interpolation=w.interpolation;f.mode=w.mode;Object.assign(f.params,report?.selected_params??w.params);f.search={};for(const [k,v] of Object.entries(w.search))f.search[k]=v.join(', ');f.name=value.saved_model?.name??''}
  else if(finished&&report?.tuning.mode==='auto')Object.assign(forms[key].params,report.selected_params)
 }
 function poll(){if(timer)clearTimeout(timer);if(!alive||!running.value)return
  timer=setTimeout(async()=>{const id=running.value?.id;if(!id)return
   try{const value=await gTrainingApi.get(id);if(alive){accept(value);error.value=''}}catch(e){if(alive)error.value=(e as Error).message}finally{poll()}
  },1500)
 }
 async function load(){const mine=++sequence;loading.value=true;error.value=''
  try{const value=await gTrainingApi.info();if(!alive||mine!==sequence)return;info.value=value
   running.value=value.active_job?.state==='running'?value.active_job:null
   for(const key of ['field','mapping'] as const){const current=jobs[key];const latest=value.jobs.find(j=>kind(j)===key&&j.id===current?.id)??value.jobs.find(j=>kind(j)===key);if(latest&&(!current||current.state==='running'))accept(latest,!current)}
   poll()
  }catch(e){if(alive&&mine===sequence)error.value=(e as Error).message}finally{if(alive&&mine===sequence)loading.value=false}
 }
 async function start(){if(busy.value||loading.value||!info.value?.dataset.ready)return
  const key=target.value;let body
  try{body={name:key==='field'?'温度场构建模型':'气象映射模型',spatial_protocol:'independent_house_section_v2' as const,workbench:config(forms[key],key)}}catch(e){error.value=(e as Error).message;return}
  const encoded=JSON.stringify(body);if(pending?.body!==encoded)pending={body:encoded,key:crypto.randomUUID()}
  submitting.value=true;error.value='';savedNotice.value='';sequence++
  try{const value=await gTrainingApi.start(body as Parameters<typeof gTrainingApi.start>[0],pending.key);if(alive){pending=null;accept(value);forms[key].name='';poll()}}
  catch(e){if(alive)error.value=(e as Error).message}finally{if(alive)submitting.value=false}
 }
 const dirty=computed(()=>{const value=job.value;if(!value?.options.workbench)return false;try{const expected={...value.options.workbench,...(target.value==='mapping'?{prediction_target:value.options.workbench.prediction_target??'absolute'}:{}),params:result.value?.selected_params??value.options.workbench.params};return JSON.stringify(config(form.value,target.value))!==JSON.stringify(expected)}catch{return true}})
 async function save(){if(saving.value||busy.value||dirty.value||job.value?.state!=='done')return
  const key=target.value,id=job.value.id,name=forms[key].name.trim();if(!name){error.value='请填写模型名称。';return}
  saving.value=true;error.value='';savedNotice.value=''
  try{const saved=await gTrainingApi.saveModel(id,name);if(alive&&jobs[key]?.id===id){jobs[key]!.saved_model=saved;savedNotice.value='模型已保存，可在模型库查看。'}}catch(e){if(alive)error.value=(e as Error).message}finally{if(alive)saving.value=false}
 }
 async function cancel(){const value=running.value;if(!value||value.cancel_requested)return;try{const update=await gTrainingApi.cancel(value.id);if(alive){accept(update);poll()}}catch(e){if(alive)error.value=(e as Error).message}}
 async function view(id:string){if(busy.value)return;const mine=++viewSequence;try{const value=await gTrainingApi.get(id);if(alive&&mine===viewSequence&&kind(value)){target.value=kind(value)!;accept(value,true);poll()}}catch(e){if(alive&&mine===viewSequence)error.value=(e as Error).message}}
 onScopeDispose(()=>{alive=false;sequence++;if(timer)clearTimeout(timer)})
 return{target,info,jobs,forms,form,job,result,loading,submitting,saving,error,savedNotice,running,busy,dirty,load,start,save,cancel,view}
}
type Workspace=ReturnType<typeof createWorkspace>
const key:InjectionKey<()=>Workspace>=Symbol('model-training')
export function provideModelTraining(){let scope:ReturnType<typeof effectScope>|null=null,value:Workspace|null=null
 function clear(){scope?.stop();scope=null;value=null}
 provide(key,()=>{if(!value){scope=effectScope(true);value=scope.run(createWorkspace)!}return value})
 watch(useDataset().version,clear,{flush:'sync'});onScopeDispose(clear)
}
export function useModelTraining(){return inject(key,null)?.()??createWorkspace()}
