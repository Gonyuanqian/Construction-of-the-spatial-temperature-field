<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {useRoute} from 'vue-router'
import {useGreenhouseControl} from '../composables/useGreenhouseControl'
import {controlApi,type ControlDevice,type ControlParameters,type ControlPlan,type ControlTask,type DeviceKind,type PlanResult} from '../api/greenhouseControl'
import {kinds,zoneLabel,parametersText,statusLabel,localTime} from '../greenhouse/control'
import Icon from '../components/Icon.vue'
import ControlDeviceCard from '../components/ControlDeviceCard.vue'
import ControlEquipmentPreview from '../components/ControlEquipmentPreview.vue'
import ControlPlanPanel from '../components/ControlPlanPanel.vue'
import ControlEditorDialog from '../components/ControlEditorDialog.vue'
import '../greenhouse/control.css'
defineOptions({name:'GreenhouseControlView'})
const route=useRoute()
const linkedDesign=typeof route?.query.greenhouse==='string'?route.query.greenhouse:''
const linkedTab=route?.query.tab==='alarms'?'alarms':'tasks'
const state=useGreenhouseControl(linkedDesign)
const {selected,designs,record,overview,tasks,plans,events,alarms,loading,busy,needsSetup,error,message,modelReady,capabilityError,monitoring,updatedAt,blocked}=state
const tab=ref<'tasks'|'events'|'alarms'>('tasks'),focused=ref<DeviceKind|null>(null),preferred=ref('')
const focusedDevice=ref<string|null>(null)
const editor=ref<{mode:'task'|'device'|'delete';device?:ControlDevice|null;task?:ControlTask|null;kind?:DeviceKind}|null>(null)
watch(selected,(id,previous)=>{editor.value=null;preferred.value='';focused.value=null;focusedDevice.value=null;tab.value=!previous&&id===linkedDesign?linkedTab:'tasks'},{flush:'sync'})
function focusKind(kind:DeviceKind){focused.value=kind;focusedDevice.value=null}
function focusDevice(d:ControlDevice){focused.value=d.kind;focusedDevice.value=d.id}
const device=(id:string)=>overview.value?.devices.find(d=>d.id===id)
const frameId=computed(()=>{
 const m=monitoring.value,s=overview.value?.spec.structure,l=overview.value?.spec.location,c=m?.weather_source?.requested_coordinates
 if(!m?.prototype||m.state!=='ready'||!m.session_id||!s||s.type!=='arch'||!m.dimensions||!c||l?.latitude==null||l.longitude==null)return null
 if(Math.abs(m.dimensions.length_m-s.length_m)>.000001||Math.abs(m.dimensions.width_m-s.width_m)>.000001||Math.abs(m.dimensions.height_m-s.arch_height_m)>.000001)return null
 if(Math.abs(c.latitude-l.latitude)>.001||Math.abs(c.longitude-l.longitude)>.001)return null
 if(!m.time||Date.now()-new Date(m.time).getTime()>3600000)return null
 return m.session_id
})
const displayedEvents=computed(()=>tab.value==='alarms'?alarms.value:events.value)
const operation=(op:string)=>({start:'启动设备',stop:'停止设备',auto_stop:'到时停止',task_run:'执行任务',pause_all:'暂停全部',resume:'恢复控制',rebind:'更新设计版本',stop_all:'停止全部','stop-all':'停止全部',configure_device:'修改设备',add_device:'添加设备',create_task:'创建任务',edit_task:'修改任务',delete_task:'删除任务',setup:'初始化',confirm_plan:'确认 AI 计划'}[op]??op)
async function command(d:ControlDevice,parameters?:ControlParameters){await state.mutation(parameters?'已启动模拟设备':'已停止模拟设备',{device:d.id,revision:d.revision,parameters},(id,key)=>controlApi.command(id,d.id,{request_key:key,revision:d.revision,action:parameters?'start':'stop',...(parameters?{parameters}:{})}))}
async function saveEditor(body:Record<string,unknown>){const e=editor.value;if(!e)return
 const ok=await state.mutation(e.mode==='device'?'设备配置已保存':e.mode==='delete'?'任务已删除':'定时任务已保存',{editor:e,body},(id,key)=>{
  const input={...body,request_key:key}
  if(e.mode==='device')return e.device?controlApi.configure(id,e.device.id,input):controlApi.addDevice(id,input)
  if(e.mode==='delete'&&e.task)return controlApi.deleteTask(id,e.task.id,{request_key:key,revision:e.task.revision})
  return e.task?controlApi.editTask(id,e.task.id,input):controlApi.createTask(id,input)
 });if(ok)editor.value=null
}
async function toggleTask(t:ControlTask){await state.mutation(t.enabled?'任务已暂停':'任务已启用',{task:t.id,revision:t.revision,enabled:!t.enabled},(id,key)=>controlApi.editTask(id,t.id,{request_key:key,revision:t.revision,name:t.name,enabled:!t.enabled,spec:t.spec}))}
async function generate(stage:string,horizon:number,frame:string|null){await state.mutation('控制计划已提交',{stage,horizon,frame},async(id,key)=>{const p=await controlApi.generate(id,{request_key:key,stage,horizon_minutes:horizon,...(frame?{prototype_frame_id:frame}:{})});preferred.value=p.id})}
async function savePlan(p:ControlPlan,result:PlanResult){await state.mutation('计划草案已保存',{id:p.id,revision:p.revision,result},id=>controlApi.savePlan(id,p.id,{revision:p.revision,result}))}
async function confirm(p:ControlPlan,ids:string[]){await state.mutation('所选计划已创建任务',{id:p.id,revision:p.revision,ids},id=>controlApi.confirm(id,p.id,{revision:p.revision,action_ids:ids}));tab.value='tasks'}
async function cancel(p:ControlPlan){await state.mutation('计划已取消',{id:p.id},id=>controlApi.cancel(id,p.id))}
</script>
<template>
 <div class="control-page">
  <header class="control-title"><h1>温室控制 <span class="tag">设备模拟</span></h1><button class="stop-all" :disabled="!overview||busy" @click="state.houseAction('stop-all')"><span class="stop-box"/>停止全部</button></header>
  <div v-if="(error&&!editor)||message" class="control-feedback" :class="{failure:!!error}" :role="error?'alert':'status'">{{error||message}}<button v-if="error" :disabled="busy" @click="state.load()">刷新状态</button></div>
  <section class="control-panel control-toolbar"><label>当前棚室<select v-model="selected" aria-label="当前棚室" :disabled="busy||!designs.length"><option v-if="!designs.length" value="">{{error?'棚室加载失败':loading?'正在读取…':'暂无已保存棚室'}}</option><option v-for="d in designs" :key="d.id" :value="d.id">{{d.spec.name}}</option></select></label><template v-if="record"><span class="location-text">{{record.spec.location.province_name||'地点未设置'}}{{record.spec.location.city_name?' · '+record.spec.location.city_name:''}}</span><span class="tag">{{overview?.spec.structure.length_m??record.spec.structure.length_m}} × {{overview?.spec.structure.width_m??record.spec.structure.width_m}} × {{overview?.spec.structure.arch_height_m??record.spec.structure.arch_height_m}} m</span></template><div class="toolbar-right"><span class="tag">演示设备</span><button :disabled="busy||loading" @click="state.load()"><Icon name="reset"/>刷新状态</button></div></section>
  <div v-if="!designs.length&&!loading&&!error" class="control-panel control-empty"><Icon name="cube"/><h2>先保存一份您的温室设计</h2><p class="muted">棚体尺寸和种植布局将用于生成这里的设备示意。</p><RouterLink to="/greenhouse-design">前往温室设计 →</RouterLink></div>
  <div v-else-if="needsSetup" class="control-panel control-empty"><Icon name="controls"/><h2>为“{{record?.spec.name}}”配置模拟设备</h2><p class="muted">根据保存方案创建控制单元，先体验手动控制、定时任务和 AI 计划。</p><button class="primary" :disabled="busy" @click="state.setup()">初始化模拟设备</button></div>
  <p v-else-if="loading&&!overview" class="muted" role="status">正在读取温室配置…</p>
  <template v-if="overview">
   <div v-if="overview.paused||overview.design_stale" class="notice control-pause"><span>{{overview.design_stale?'温室设计已有新版本，请重新绑定并核对设备。':'控制与任务已暂停。恢复控制后，旧任务仍保持暂停。'}}</span><button v-if="overview.design_stale" :disabled="busy" @click="state.houseAction('rebind')">绑定最新设计</button><button v-else :disabled="busy" @click="state.houseAction('resume')">恢复控制</button></div>
   <div class="control-equipment">
    <ControlEquipmentPreview :key="overview.design_id" :overview="overview" :focused="focused" :selected-id="focusedDevice"
      @focus="focusKind" @select="focusDevice"/>
    <div class="device-grid"><ControlDeviceCard v-for="kind in kinds" :key="kind" :kind="kind"
      :devices="overview.devices.filter(d=>d.kind===kind)" :selected-id="focusedDevice"
      :blocked="blocked" :busy="busy" :focused="focused===kind"
      @select="focusDevice" @start="command" @stop="d=>command(d)" @settings="d=>editor={mode:'device',device:d,kind}"/></div>
   </div>
   <ControlPlanPanel :overview="overview" :plans="plans" :busy="busy" :model-ready="modelReady" :capability-error="capabilityError" :frame-id="frameId" :preferred="preferred" @generate="generate" @save="savePlan" @confirm="confirm" @cancel="cancel"/>
   <section class="control-panel task-panel" aria-label="任务与记录"><header class="panel-heading"><div class="control-tabs" role="tablist" aria-label="任务记录分类"><button v-for="(label,key) in {tasks:'定时任务',events:'操作记录',alarms:'设备告警'}" :key="key" role="tab" :aria-selected="tab===key" @click="tab=key">{{label}}</button></div><button class="primary" :disabled="busy||blocked||!overview.devices.some(d=>d.enabled)" @click="editor={mode:'task'}"><Icon name="plus"/>新建任务</button></header>
    <div class="control-table-wrap"><table v-if="tab==='tasks'"><thead><tr><th>任务名称</th><th>设备 / 分区</th><th>执行时间</th><th>时长 / 参数</th><th>来源</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="t in tasks" :key="t.id"><td>{{t.name}}</td><td>{{device(t.device_id)?.name??'设备'}}<small>{{zoneLabel(device(t.device_id)?.zone_key??'all')}}</small></td><td>{{t.spec.schedule.kind==='daily'?'每天 '+t.spec.schedule.time:localTime(t.spec.schedule.at)}}</td><td>{{parametersText(t.spec.parameters)}}</td><td><span class="tag" :class="{ai:t.source==='agriseek'}">{{t.source==='agriseek'?'AgriSeek':'手动'}}</span></td><td><button v-if="['ready','paused'].includes(t.status)" class="task-switch" role="switch" :aria-checked="t.enabled" :aria-label="`${t.enabled?'暂停':'启用'}${t.name}`" :disabled="busy||(!t.enabled&&blocked)" @click="toggleTask(t)"><span/>{{t.enabled?'开启':'暂停'}}</button><span v-else>{{statusLabel(t.status)}}</span></td><td class="row-actions"><button class="text-button" :disabled="busy" @click="editor={mode:'task',task:t}">编辑</button><button class="text-button" :disabled="busy" @click="editor={mode:'delete',task:t}">删除</button></td></tr><tr v-if="!tasks.length"><td colspan="7" class="empty-row">尚无定时任务，可手动新建或确认 AgriSeek 控制计划。</td></tr></tbody></table>
    <table v-else><thead><tr><th>时间</th><th>设备</th><th>操作</th><th>来源</th><th>结果</th><th>说明</th></tr></thead><tbody><tr v-for="e in displayedEvents" :key="e.id"><td>{{localTime(e.created_at)}}</td><td>{{e.device_id?device(e.device_id)?.name??'设备':'全棚'}}</td><td>{{operation(e.operation)}}</td><td>{{e.source==='manual'?'用户':e.source==='agriseek'?'AgriSeek':e.source==='scheduler'?'定时调度':'系统'}}</td><td>{{statusLabel(e.status)}}</td><td>{{e.result.detail??e.result.reason??'模拟操作'}}</td></tr><tr v-if="!displayedEvents.length"><td colspan="6" class="empty-row">{{tab==='alarms'?'暂无软件调度告警；尚未接入现场硬件告警。':'暂无操作记录。'}}</td></tr></tbody></table></div>
    <footer class="task-note"><span>当前为模拟控制，设备接入后才有实际执行回执。</span><span>状态更新 {{localTime(updatedAt)}}</span></footer>
   </section>
  </template>
  <ControlEditorDialog v-if="editor" v-bind="editor" :devices="overview?.devices??[]" :busy="busy" :error="error" @close="editor=null" @save="saveEditor"/>
 </div>
</template>
<style scoped>
.control-title{display:flex;align-items:center;justify-content:space-between;gap:15px}.control-title h1{display:flex;align-items:center;gap:16px;margin:0;font-size:27px}.control-title .tag{font-weight:400;color:var(--edge)}.stop-all{color:var(--control-amber);border-color:var(--control-amber);background:var(--control-amber-soft)}.stop-box{height:12px;width:12px;border:1px solid currentColor}.control-feedback{position:sticky;top:0;z-index:3;background:var(--card-2);padding:12px 15px;border:1px solid var(--edge);border-radius:5px;font-size:13px;display:flex;align-items:center;justify-content:space-between;gap:12px}.control-feedback.failure{border-color:var(--control-amber);color:var(--control-amber)}.control-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:20px;padding:15px 18px}.control-toolbar>label{display:flex;align-items:center;gap:14px;font-size:14px;font-weight:600}.control-toolbar select{max-width:260px;min-width:170px;font-weight:400}.location-text{border-left:1px solid var(--edge-line);padding-left:20px;color:var(--ink-muted);font-size:13px}.toolbar-right{display:flex;gap:12px;align-items:center;margin-left:auto}.toolbar-right button{font-size:13px}.control-toolbar svg{width:17px;height:17px}.control-empty{display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;min-height:280px;text-align:center}.control-empty>svg{width:44px;height:44px;color:var(--edge)}.control-empty h2{font-size:20px;margin:8px 0}.control-empty p{font-size:14px}.control-equipment{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(500px,1fr);gap:18px;align-items:stretch}.device-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;min-width:0}.control-pause{display:flex;align-items:center;justify-content:space-between;gap:15px}.control-pause button{white-space:nowrap}.control-tabs{display:flex;gap:6px}.control-tabs button{border:0;background:none;color:var(--ink-muted);padding:11px 16px}.control-tabs [aria-selected=true]{background:var(--nav-blue);color:var(--on-face)}.task-panel .panel-heading{margin-bottom:16px}.task-panel table{min-width:850px}.task-panel td small{display:block;color:var(--ink-muted);font-size:11px;margin-top:5px}.task-panel .ai{color:var(--edge)}.row-actions{white-space:nowrap}.row-actions button+button{margin-left:10px}.task-switch{font-size:11px;padding:3px 7px;border-radius:20px;white-space:nowrap;color:var(--ink-muted)}.task-switch>span{width:12px;height:12px;border-radius:50%;background:currentColor;display:inline-block}.task-switch[aria-checked=true]{color:var(--edge);border-color:var(--edge)}.task-note{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--ink-muted);margin-top:16px;line-height:1.7}@media(max-width:1250px){.control-equipment{grid-template-columns:1fr}.device-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:1100px){.device-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.control-toolbar{gap:14px}.location-text{border:0;padding:0}}@media(max-width:640px){.control-title h1{font-size:23px;gap:10px}.control-title .tag{font-size:10px}.control-title .stop-all{font-size:12px}.device-grid{grid-template-columns:1fr}.toolbar-right{margin-left:0;width:100%;justify-content:space-between}.control-toolbar>label{width:100%}.control-toolbar select{max-width:100%;min-width:0;flex:1}.control-tabs{gap:0}.control-tabs button{font-size:12px;padding:9px}.task-panel .panel-heading{flex-wrap:wrap}.task-note{flex-direction:column}.control-pause{flex-direction:column;align-items:flex-start}}
</style>
