import {getJson,postJson,writeJson} from './client'
import type {DesignSpec,DesignPreview} from './greenhouseDesigns'
export type DeviceKind='drip'|'sprinkler'|'ventilation'|'lighting'
export type ZoneKey='all'|'a'|'b'
export interface ControlParameters {duration_seconds:number;brightness_percent?:number;speed?:'low'|'medium'|'high'}
export interface ControlDevice {
 id:string;design_id:string;name:string;kind:DeviceKind;zone_key:ZoneKey;enabled:boolean;revision:number
 mode:'simulation';connection_status:'simulated';stop_at:string|null;running_seconds:number;today_runtime_seconds:number;total_runtime_seconds:number
 state:{running:boolean;started_at?:string;task_id?:string}&Partial<ControlParameters>
 capabilities:{max_duration_seconds:number;dimming:boolean;speed_control:boolean}
}
export interface ControlOverview {design_id:string;design_revision:number;epoch:number;paused:boolean;mode:'simulation';design_stale:boolean;spec:DesignSpec;layout:DesignPreview;devices:ControlDevice[];timezone:string;zone_note:string}
export type ControlSchedule={kind:'once';at:string}|{kind:'daily';time:string;timezone:'Asia/Shanghai'}
export interface ControlTask {id:string;design_id:string;device_id:string;name:string;source:'manual'|'agriseek';plan_id:string|null;revision:number;enabled:boolean;status:string;spec:{parameters:ControlParameters;schedule:ControlSchedule};next_run_at:string|null;last_run_at:string|null}
export interface ControlEvent {id:string;device_id:string|null;operation:string;source:string;status:string;created_at:string;result:{detail?:string;reason?:string;task_id?:string}}
export interface PlanAction {id:string;device_id:string;parameters:ControlParameters;start_after_minutes:number;reason:string}
export interface PlanResult {summary:string;actions:PlanAction[];notes:string[]}
export interface ControlPlan {
 id:string;design_id:string;revision:number;status:'queued'|'generating'|'draft'|'confirmed'|'failed'|'cancelled';created_at:string;expires_at:string;error_code:string|null
 input:{stage:string;horizon_minutes:number;prototype_frame_id?:string}
 snapshot:{epoch:number;design_revision:number;captured_at:string;devices:ControlDevice[];monitoring:null|{observed_at:string;bg_temp:number;bg_rh:number|null;bg_light:number;summary:{mean?:number;vmin?:number;vmax?:number};source:{observed_at?:string;light_time?:string}}}
 result:PlanResult|null;confirmation:null|{task_ids:string[];confirmed_at:string}
}
const base=(id:string)=>`/api/user/greenhouse-designs/${encodeURIComponent(id)}/control`
export const controlApi={
 overview:(id:string)=>getJson<ControlOverview>(base(id)),
 setup:(id:string,revision:number)=>postJson<ControlOverview>(base(id)+'/setup',{revision}),
 house:(id:string,operation:'stop-all'|'resume'|'rebind',body:unknown)=>postJson(base(id)+'/'+operation,body),
 addDevice:(id:string,body:unknown)=>postJson(base(id)+'/devices',body),
 configure:(id:string,device:string,body:unknown)=>writeJson('PUT',base(id)+'/devices/'+encodeURIComponent(device),body),
 command:(id:string,device:string,body:unknown)=>postJson(base(id)+'/devices/'+encodeURIComponent(device)+'/commands',body),
 tasks:(id:string)=>getJson<{items:ControlTask[]}>(base(id)+'/tasks'),
 createTask:(id:string,body:unknown)=>postJson(base(id)+'/tasks',body),
 editTask:(id:string,task:string,body:unknown)=>writeJson('PUT',base(id)+'/tasks/'+encodeURIComponent(task),body),
 deleteTask:(id:string,task:string,body:unknown)=>postJson(base(id)+'/tasks/'+encodeURIComponent(task)+'/delete',body),
 events:(id:string,alarms=false,offset=0)=>getJson<{items:ControlEvent[]}>(`${base(id)}/events?limit=30&offset=${offset}&alarms=${alarms}`),
 capabilities:(id:string)=>getJson<{model_configured:boolean}>(base(id)+'/capabilities'),
 plans:(id:string)=>getJson<{items:ControlPlan[]}>(base(id)+'/plans'),
 generate:(id:string,body:unknown)=>postJson<ControlPlan>(base(id)+'/plans',body),
 savePlan:(id:string,plan:string,body:unknown)=>writeJson<ControlPlan>('PUT',base(id)+'/plans/'+encodeURIComponent(plan),body),
 confirm:(id:string,plan:string,body:unknown)=>postJson<ControlPlan>(base(id)+'/plans/'+encodeURIComponent(plan)+'/confirm',body),
 cancel:(id:string,plan:string)=>postJson<ControlPlan>(base(id)+'/plans/'+encodeURIComponent(plan)+'/cancel',{}),
}
