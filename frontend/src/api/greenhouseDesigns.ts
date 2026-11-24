import { deleteJson, getJson, postJson, writeJson } from './client'
import type { MonitoringLocation } from '../live/monitoringLocation'
export interface LightingDesign { enabled:boolean; spacing_m:number; mounting_height_m:number }
export interface DesignSpec {
 name:string
 location:Omit<Partial<MonitoringLocation>,'longitude'|'latitude'>&{longitude:number|null;latitude:number|null;altitude_m:number|null;opening_azimuth:number;coordinate_system:'GCJ-02'}
 structure:{type:'arch'|'multi_span';length_m:number;width_m:number;arch_height_m:number;covering:'film'|'shade_net'|'film_shade'|'polycarbonate'|'glass';span_width_m:number;span_count:number;eave_height_m:number}
 planting:{cultivar:string;band_width_m:number;plant_spacing_m:number;row_spacing_m:number;aisle_width_m:number;front_passage_m:number;rear_passage_m:number;side_margin_m:number}
 irrigation:{drip_enabled:boolean;sprinkler_enabled:boolean;emitter_spacing_m:number;sprinkler_spacing_m:number;installation_height_m:number;coverage_radius_m:number;placement:'auto'|'manual';sprinklers:{x:number;y:number}[]}
 lighting?:LightingDesign
}
export interface DesignRecord {id:string;revision:number;spec:DesignSpec;created_at?:string;updated_at?:string}
export interface DesignPreview {
 beds:{x:number;y:number;width:number;length:number}[]
 rows:{x:number;y_start:number;y_end:number;plant_count:number}[]
 sprinklers:{x:number;y:number}[]
 lights?:{x:number;y:number;z:number}[]
 area_m2:number;usable_length_m:number;plant_count:number;notices:string[]
 ai:{available:false;status:'planned'}
 model:{geometry_only:true;monitoring_supported:boolean;detail:string}
}
const base='/api/user/greenhouse-designs'
export const designsApi={
 list:()=>getJson<{items:DesignRecord[];total:number}>(base+'?limit=100'),
 get:(id:string)=>getJson<DesignRecord>(base+'/'+encodeURIComponent(id)),
 create:(spec:DesignSpec)=>postJson<DesignRecord>(base,spec),
 update:(id:string,revision:number,spec:DesignSpec)=>writeJson<DesignRecord>('PUT',base+'/'+encodeURIComponent(id),{revision,spec}),
 remove:(id:string,revision:number)=>deleteJson<{deleted:true}>(`${base}/${encodeURIComponent(id)}?revision=${revision}`),
 preview:(spec:DesignSpec)=>postJson<DesignPreview>(base+'/preview',spec),
 active:()=>getJson<{selection:DesignRecord|null}>(base+'/active'),
 activate:(id:string,revision:number)=>postJson<DesignRecord>(base+'/'+encodeURIComponent(id)+'/activate',{revision}),
}
export function newDesign():DesignSpec & {lighting:LightingDesign}{return{
 name:'我的人参棚',location:{longitude:null,latitude:null,altitude_m:null,opening_azimuth:180,coordinate_system:'GCJ-02'},
 structure:{type:'arch',length_m:18,width_m:6,arch_height_m:2.4,covering:'film_shade',span_width_m:6,span_count:2,eave_height_m:2},
 planting:{cultivar:'',band_width_m:1.2,plant_spacing_m:.2,row_spacing_m:.3,aisle_width_m:.5,front_passage_m:.8,rear_passage_m:.6,side_margin_m:.7},
 irrigation:{drip_enabled:true,sprinkler_enabled:true,emitter_spacing_m:.2,sprinkler_spacing_m:2,installation_height_m:1.6,coverage_radius_m:1.5,placement:'auto',sprinklers:[]},
 lighting:{enabled:false,spacing_m:3,mounting_height_m:1.6},
}}
