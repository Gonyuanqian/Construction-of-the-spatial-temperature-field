import type { VolumePointPayload } from '../api/types'

export function pointText(p: VolumePointPayload): string {
  if (p.kind === 'outside') return '拱外，无定义：该坐标不在棚体拱形截面内'
  if (p.kind === 'unmeasured') return `无测量带（z 高于 ${p.max_measured_z.toFixed(2)} m），不报数`
  if (p.kind === 'unavailable') return '该位置附近的有效格点不足，无法插值；请向棚内调整坐标'
  if (p.kind !== 'value' || p.value === null || !Number.isFinite(p.value)) throw new Error('查询返回了无效的温度结果')
  return `空间重建（网格插值）：${p.value.toFixed(2)} °C`
}
