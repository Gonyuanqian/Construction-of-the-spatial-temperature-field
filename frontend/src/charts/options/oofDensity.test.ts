/// <reference types="node" />
// 这一条要读源码文本（见最后一个用例）。jsdom 环境下 `import.meta.url` 不是
// file: 协议，`fileURLToPath` 会抛「The URL must be of scheme file」——
// 与 `design/prose.test.ts`、`design/guards.test.ts` 两处源码守卫同一个头。
// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { buildOofDensityOption, densityColor } from './oofDensity'
import type { Palette } from '../../design/palette'
import type { DiagnosticsPayload } from '../../api/types'

const P = {
  paper: '#fff', ink: '#111', inkMuted: '#666', steel: '#888', leaf: '#0a0',
  leafSoft: '#efe', net: '#c00', layerTop: '#1', layerMid: '#2', layerLow: '#3',
  chartAxis: 12, chartTitle: 14,
} as unknown as Palette

function payload(counts: number[][], extra: Partial<DiagnosticsPayload['density']> = {}) {
  return {
    density: { bins: counts.length, lo: 0, hi: 10, n: 100, counts, ...extra },
  } as unknown as DiagnosticsPayload
}

describe('密度图', () => {
  it('每一格一个矩形，零格不画', () => {
    const opt = buildOofDensityOption(payload([[1, 0], [0, 2]]), P)
    const series = opt.series as { type: string; data: unknown[] }[]
    expect(series[0].type).toBe('custom')
    expect(series[0].data).toHaveLength(2)      // 两个非零格
  })

  it('两个轴共用同一个范围 —— 它是 45 度对角线图', () => {
    const opt = buildOofDensityOption(payload([[1]]), P)
    const ax = opt.xAxis as { min: number; max: number }
    const ay = opt.yAxis as { min: number; max: number }
    expect(ax.min).toBe(0)
    expect(ax.max).toBe(10)
    expect(ay.min).toBe(ax.min)
    expect(ay.max).toBe(ax.max)
  })

  it('有一条 y = x 的参考线', () => {
    const opt = buildOofDensityOption(payload([[1]]), P)
    const series = opt.series as { type: string; data: number[][] }[]
    const ref = series.find((s) => s.type === 'line')!
    expect(ref).toBeDefined()
    expect(ref.data).toEqual([[0, 0], [10, 10]])
  })

  it('一对有限点都没有时给一张空图而不是崩', () => {
    // 后端在「一个有限点都没有」时给 lo/hi = null，counts = []。
    const opt = buildOofDensityOption(payload([], { lo: null, hi: null, counts: [] }), P)
    expect((opt.series as unknown[]).length).toBe(0)
    expect((opt.title as { text: string }).text).toContain('没算出来')
  })

  it('计数映射到颜色时，零与最大值对得上色标的两端', () => {
    const stops = ['#a', '#b', '#c']
    expect(densityColor(1, 100, stops)).toBe(stops[0])
    expect(densityColor(100, 100, stops)).toBe(stops[stops.length - 1])
  })

  it('计数全一样时也给得出颜色（不许除以零）', () => {
    expect(densityColor(3, 1, ['#a', '#b'])).toBe('#b')
  })

  it('色标只从 scale.ts 来 —— 实现文件里没有十六进制字面量', () => {
    // `design/guards.test.ts` 扫的是源码，它管不着测试文件；这条是给实现文件
    // 补的镜像守卫。比那条全仓守卫更严一点：它只认**六位**十六进制，
    // 这里连 `#fff` 这种三位写法一起拦。
    const src = readFileSync(
      fileURLToPath(new URL('./oofDensity.ts', import.meta.url)), 'utf8')
    expect(src.match(/#[0-9A-Fa-f]{3,8}\b/g) ?? []).toEqual([])
  })
})
