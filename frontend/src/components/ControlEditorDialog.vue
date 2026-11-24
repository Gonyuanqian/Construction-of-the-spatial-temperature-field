<script setup lang="ts">
import {computed,reactive} from 'vue'
import ModalDialog from './ModalDialog.vue'
import type {ControlDevice,ControlTask,DeviceKind,ZoneKey} from '../api/greenhouseControl'
import {kindLabels,kinds,zoneLabel} from '../greenhouse/control'
const props=defineProps<{mode:'device'|'task'|'delete';device?:ControlDevice|null;task?:ControlTask|null;kind?:DeviceKind;devices:ControlDevice[];busy:boolean;error:string}>()
const emit=defineEmits<{close:[];save:[body:Record<string,unknown>]}>()
const isoLocal=(value:string)=>new Date(value).toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'}).slice(0,16).replace(' ','T')
const initial=props.task?.spec.parameters
const form=reactive({name:props.mode==='device'?(props.device?.name??kindLabels[props.kind??'drip']):(props.task?.name??''),kind:props.device?.kind??props.kind??'drip',zone:(props.device?.zone_key??'all') as ZoneKey,enabled:props.device?.enabled??props.task?.enabled??true,device:props.task?.device_id??props.devices.find(d=>d.enabled)?.id??'',minutes:(initial?.duration_seconds??600)/60,brightness:initial?.brightness_percent??60,speed:initial?.speed??'medium',schedule:props.task?.spec.schedule.kind??'daily',time:props.task?.spec.schedule.kind==='daily'?props.task.spec.schedule.time:'07:00',at:props.task?.spec.schedule.kind==='once'?isoLocal(props.task.spec.schedule.at):isoLocal(new Date(Date.now()+3600000).toISOString())})
const selected=computed(()=>props.devices.find(d=>d.id===form.device))
const title=computed(()=>props.mode==='delete'?'删除定时任务':props.mode==='device'?(props.device?'设备设置':'添加模拟设备'):(props.task?'编辑定时任务':'新建定时任务'))
function submit(){
 if(props.mode==='delete'){emit('save',{});return}
 if(props.mode==='device'){emit('save',{name:form.name,zone_key:form.zone,...(props.device?{revision:props.device.revision,enabled:form.enabled}:{kind:form.kind})});return}
 const parameters={duration_seconds:Math.round(form.minutes*60),...(selected.value?.kind==='lighting'?{brightness_percent:form.brightness}:{}),...(selected.value?.kind==='ventilation'?{speed:form.speed}:{})}
 const schedule=form.schedule==='daily'?{kind:'daily',time:form.time,timezone:'Asia/Shanghai'}:{kind:'once',at:new Date(form.at+':00+08:00').toISOString()}
 emit('save',{name:form.name,spec:{parameters,schedule},...(props.task?{revision:props.task.revision,enabled:form.enabled}:{device_id:form.device})})
}
</script>
<template><ModalDialog :label="title" :busy="busy" @close="emit('close')"><div class="control-dialog"><header><h2>{{title}}</h2><button :disabled="busy" aria-label="关闭编辑窗口" @click="emit('close')">关闭</button></header><form @submit.prevent="submit">
 <p v-if="error" role="alert" class="notice">{{error}}</p>
 <template v-if="mode==='delete'"><p>删除“{{task?.name}}”？任务记录会保留；正在由该任务运行的设备将停止。</p></template>
 <template v-else-if="mode==='device'"><label>设备名称<input v-model="form.name" required maxlength="80"></label><div class="editor-grid"><label>设备类型<select v-model="form.kind" :disabled="!!device"><option v-for="k in kinds" :key="k" :value="k">{{kindLabels[k]}}</option></select></label><label>控制分区<select v-model="form.zone"><option v-for="z in ['all','a','b']" :key="z" :value="z">{{zoneLabel(z)}}</option></select></label></div><label v-if="device" class="check-label"><input v-model="form.enabled" type="checkbox">启用此控制单元</label><p class="muted">{{device?'保存配置将停止本单元，并暂停关联任务。':'新增的是模拟控制单元；分组不代表已接通现场设备。'}}</p></template>
 <template v-else><label>任务名称<input v-model="form.name" required maxlength="100" placeholder="例如：早间滴灌"></label><label>控制设备<select v-model="form.device" required :disabled="!!task"><option v-for="d in devices" :key="d.id" :value="d.id">{{d.name}} · {{zoneLabel(d.zone_key)}}{{!d.enabled?'（已停用）':''}}</option></select></label><div class="editor-grid"><label>运行时长 / 分钟<input v-model.number="form.minutes" required type="number" min=".1" :max="(selected?.capabilities.max_duration_seconds??1800)/60" step=".1"></label><label>执行方式<select v-model="form.schedule"><option value="daily">每天执行</option><option value="once">单次执行</option></select></label><label v-if="selected?.kind==='lighting'">补光亮度 / %<input v-model.number="form.brightness" required type="number" min="1" max="100" step="1"></label><label v-if="selected?.kind==='ventilation'">风速<select v-model="form.speed"><option value="low">低</option><option value="medium">中</option><option value="high">高</option></select></label><label v-if="form.schedule==='daily'">执行时间 / 北京时间<input v-model="form.time" required type="time"></label><label v-else class="wide">执行时刻 / 北京时间<input v-model="form.at" required type="datetime-local"></label></div><label v-if="task" class="check-label"><input v-model="form.enabled" type="checkbox">启用任务</label><p class="muted">任务保存在服务端。修改运行中的任务会先停止由该任务启动的设备。</p></template>
 <footer><button type="button" :disabled="busy" @click="emit('close')">取消</button><button type="submit" class="primary" :disabled="busy">{{busy?'保存中…':mode==='delete'?'确认删除':'保存'}}</button></footer>
 </form></div></ModalDialog></template>
<style scoped>
.control-dialog header{display:flex;align-items:center;justify-content:space-between;gap:12px}.control-dialog h2{margin:0;font-size:20px}.control-dialog form{display:flex;flex-direction:column;gap:18px;margin-top:22px}.control-dialog label{display:flex;flex-direction:column;gap:9px;font-size:14px}.editor-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.editor-grid .wide{grid-column:1/-1}.control-dialog input,.control-dialog select{width:100%;min-width:0}.control-dialog .check-label{flex-direction:row;align-items:center}.check-label input{width:auto}.control-dialog footer{display:flex;justify-content:flex-end;gap:10px;padding-top:8px}.control-dialog p{margin:0;font-size:13px;line-height:1.8}
</style>
