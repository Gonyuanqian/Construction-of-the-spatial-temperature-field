export interface HouseDimensions { length_m: number; width_m: number; height_m: number }
export const REFERENCE_DIMENSIONS:HouseDimensions={length_m:6,width_m:2.1,height_m:1.3017}
export const DIMENSION_LIMITS={length_m:{min:.5,max:200},width_m:{min:.5,max:20},height_m:{min:.3,max:10}}
export function validDimensions(value:unknown):value is HouseDimensions{
 if(!value||typeof value!=='object'||Array.isArray(value))return false
 const d=value as Record<string,unknown>
 return Object.keys(d).length===3&&Object.entries(DIMENSION_LIMITS).every(([k,limits])=>typeof d[k]==='number'&&Number.isFinite(d[k])&&(d[k] as number)>=limits.min&&(d[k] as number)<=limits.max)
}
export function sameDimensions(a:unknown,b:HouseDimensions){return validDimensions(a)&&Object.keys(REFERENCE_DIMENSIONS).every(k=>Math.abs(a[k as keyof HouseDimensions]-b[k as keyof HouseDimensions])<1e-8)}
