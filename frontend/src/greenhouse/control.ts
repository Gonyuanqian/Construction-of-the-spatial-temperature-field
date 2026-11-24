import type {ControlParameters,DeviceKind} from '../api/greenhouseControl'
import type {IconName} from '../design/icons'
export const kinds:DeviceKind[]=['drip','sprinkler','ventilation','lighting']
export const kindLabels:Record<DeviceKind,string>={drip:'滴灌设备',sprinkler:'喷灌设备',ventilation:'通风设备',lighting:'补光设备'}
export const kindIcons:Record<DeviceKind,IconName>={drip:'humidity',sprinkler:'sprinkler',ventilation:'fan',lighting:'sunlight'}
export const zoneLabel=(zone:string)=>({all:'全棚',a:'A 区',b:'B 区'}[zone]??zone)
export const clone=<T,>(value:T):T=>JSON.parse(JSON.stringify(value))
export function duration(seconds:number){const n=Math.max(0,Math.floor(seconds));return n>=3600?`${Math.floor(n/3600)} 小时 ${Math.floor(n%3600/60)} 分钟`:`${Math.floor(n/60)} 分 ${n%60} 秒`}
export function parametersText(p:ControlParameters){return [p.speed?({low:'低速',medium:'中速',high:'高速'}[p.speed]):'',p.brightness_percent?`亮度 ${p.brightness_percent}%`:'',duration(p.duration_seconds)].filter(Boolean).join(' · ')}
export const statusLabel=(status:string)=>({ready:'待执行',running:'运行中',completed:'已完成',paused:'已暂停',stopped:'已停止',expired:'已过期',skipped:'已跳过',draft:'待确认',queued:'等待生成',generating:'正在分析',confirmed:'已创建任务',failed:'生成失败',cancelled:'已取消',simulated:'模拟成功'}[status]??status)
export function localTime(value:string|null|undefined){if(!value)return '暂无';const date=new Date(value);return Number.isNaN(date.getTime())?'时间无效':date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'})}
