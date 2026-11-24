/** Display-only bearings; physical thermal effects are not inferred. */
export function bearingName(angle:number):string {
 if(!Number.isFinite(angle))return '待填写'
 return ['北','东北','东','东南','南','西南','西','西北'][Math.round(((angle%360+360)%360)/45)%8]!
}
