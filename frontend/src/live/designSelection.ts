import { designsApi, type DesignSpec } from '../api/greenhouseDesigns'
import { validStoredLocation } from './monitoringLocation'
import { validDimensions } from './houseDimensions'

export function monitoringConfig(spec: DesignSpec) {
 const {structure,location}=spec
 const dimensions={length_m:structure.length_m,width_m:structure.width_m,height_m:structure.arch_height_m}
 if(structure.type!=='arch'||!validDimensions(dimensions))return {issue:'该棚型或尺寸暂不能用于当前监测模型。'} as const
 if(!validStoredLocation(location))return {issue:'请先在温室设计中补全监测地点和经纬度。'} as const
 return {issue:null,dimensions,location} as const
}

export function requireMonitoringConfig(spec: DesignSpec){
 const result=monitoringConfig(spec)
 if(result.issue!==null)throw new Error(result.issue)
 return result
}

/** Only a previously activated, owned server snapshot may enter monitoring. */
export async function requestedDesign(id:unknown,revision:unknown){
 if(typeof id!=='string'||typeof revision!=='string')throw new Error('温室方案引用无效，请重新选择方案。')
 const {selection}=await designsApi.active()
 if(!selection||selection.id!==id||String(selection.revision)!==revision)throw new Error('应用的温室方案版本已改变，请重新选择方案。')
 return requireMonitoringConfig(selection.spec)
}
