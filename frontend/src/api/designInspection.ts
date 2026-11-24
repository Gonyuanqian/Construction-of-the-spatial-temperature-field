import {getJson,postJson} from './client'
import type {AssistantRun,AssistantCapabilities} from './assistant'
export interface DesignInspection {id:string;design_id:string;revision:number;request_key:string;created_at:string;run:AssistantRun|null}
const base='/api/user/greenhouse-designs'
const path=(id:string)=>`${base}/${encodeURIComponent(id)}/inspections`
export const designInspectionApi={
 capabilities:()=>getJson<AssistantCapabilities>(base+'/inspection-capabilities'),
 submit:(id:string,revision:number,key:string)=>postJson<DesignInspection>(path(id),{revision,request_key:key}),
 latest:(id:string)=>getJson<{inspection:DesignInspection|null}>(path(id)+'/latest'),
 history:(id:string)=>getJson<DesignInspection[]>(path(id)),
 get:(id:string,inspectionId:string)=>getJson<DesignInspection>(path(id)+'/'+encodeURIComponent(inspectionId)),
 cancel:(id:string,inspectionId:string)=>postJson<DesignInspection>(path(id)+'/'+encodeURIComponent(inspectionId)+'/cancel',{}),
}
