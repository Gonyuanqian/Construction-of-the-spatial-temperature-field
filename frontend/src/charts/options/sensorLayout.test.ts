import { describe, expect, it } from 'vitest'

import { buildSensorLayoutOption } from './sensorLayout'
import type { ArchPayload, DatasetPayload } from '../../api/types'
import { paletteColors } from '../../design/palette'

const PALETTE = {
  paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850',
  steel: '#DEDCD6', leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
  // 三个层的点色。值是用户那张切面图上的（seaborn deep），在 tokens.css 里定一次。
  layerTop: '#C44E52', layerMid: '#4C72B0', layerLow: '#55A868',
  // 页② 残差图的柱子色。这一张图也不用它，同上。
  bar: '#D98C2B',
  // 图表字号。**是数不是色** —— canvas 的 fontSize 不吃 `'12px'`。
  chartAxis: 12, chartTitle: 14,
}

const ARCH: ArchPayload = {
  x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 1.1,
  // 真载荷是 121 个点的圆弧，这里只要够画出轮廓即可 —— 这条测试不校验拱线本身。
  arch: [[0, 0.4535], [1.05, 1.3017], [2.1, 0.4686]],
  sheds: [{ id: 'p1', y: 3 }, { id: 'p2', y: 9 }, { id: 'p3', y: 15 }],
}

// 八个测点与它们的编号，都照后端真实载荷抄（含三个带括号的 ztop 点）。
const POSITIONS = [
  { id: 'x0.15_z0.4', x: 0.15, z: 0.4, layer: 'z0.4' },
  { id: 'x0.4_z0.7', x: 0.4, z: 0.7, layer: 'z0.7' },
  { id: 'x0.8_zH(0.80)-0.20', x: 0.8, z: 1.1, layer: 'ztop' },
  { id: 'x1.05_z0.4', x: 1.05, z: 0.4, layer: 'z0.4' },
  { id: 'x1.05_z0.7', x: 1.05, z: 0.7, layer: 'z0.7' },
  { id: 'x1.3_zH(1.30)-0.20', x: 1.3, z: 1.1, layer: 'ztop' },
  { id: 'x1.7_z0.7', x: 1.7, z: 0.7, layer: 'z0.7' },
  { id: 'x1.95_z0.4', x: 1.95, z: 0.4, layer: 'z0.4' },
]

const CODES: Record<string, string> = {
  'x0.8_zH(0.80)-0.20': 'B1', 'x1.3_zH(1.30)-0.20': 'B2',
  'x0.4_z0.7': 'B3', 'x1.05_z0.7': 'B4', 'x1.7_z0.7': 'B5',
  'x0.15_z0.4': 'B6', 'x1.05_z0.4': 'B7', 'x1.95_z0.4': 'B8',
}

/** 三个棚的均值故意取三个不一样的数，好让「tooltip 报的是哪一座棚」可辨。 */
const MEANS: Record<string, [number, number, number]> = {
  'x1.05_z0.7': [30.4, 31.2, 29.8],       // B4
  'x0.8_zH(0.80)-0.20': [31.9, 32.5, 30.1], // B1
}

function ds(): DatasetPayload {
  return {
    signature: 'x', file: 'f.xlsx', n_times: 1308, n_columns: 52,
    n_missing: 0, n_dup_times: 4,
    time_start: '', time_end: '',
    sheds: { p1: 3, p2: 9, p3: 15 },
    positions: POSITIONS,
    point_codes: CODES,
    temperature: POSITIONS.flatMap((pos) => {
      const m = MEANS[pos.id]
      return (['p1', 'p2', 'p3'] as const).map((shed, i) => ({
        shed, position: pos.id,
        mean: m ? m[i] : 40, min: 30, max: 50,
      }))
    }),
    fix: {
      n_rows: 1308, fixed_indices: [], monotonic_before: false,
      monotonic_after: true, spacing_seconds: 300, n_gaps: 0,
    },
    checks: [], checks_note: '',
  }
}

type Series = Record<string, any>
const series = (o: Record<string, any>): Series[] => o.series as Series[]
const scatters = (o: Record<string, any>): Series[] =>
  series(o).filter((s) => s.type === 'scatter')

/** 一个测点：`[x, z, 编号, 棚1 均值, 棚2 均值, 棚3 均值]`。 */
type Datum = [number, number, string, ...(number | null)[]]

/** 按编号从三条散点系列里把那一个点捞出来（编号是它的身份，坐标不是）。 */
function datumOf(o: Record<string, any>, code: string): Datum {
  const all = scatters(o).flatMap((s) => s.data as Datum[])
  const d = all.find((x) => x[2] === code)
  if (!d) throw new Error(`没有编号为 ${code} 的测点`)
  return d
}

describe('页① 切面图', () => {
  it('只画一个切面：一格 grid，不是三棚并排的三格', () => {
    // 用户 2026-10-06 裁定：切面图只留一座。三座棚的点位本来就是同一套，
    // 并排放三张只是把同一个形状画三遍。
    const g = buildSensorLayoutOption(ds(), ARCH, PALETTE).grid
    expect(Array.isArray(g), 'grid 还是个数组，说明还在并排画三格').toBe(false)
    expect(g).toMatchObject({
      left: expect.any(String), width: expect.any(String),
      top: expect.any(String), bottom: expect.any(String),
    })
  })

  it('图幅横向几乎占满卡片：两边不留大片白', () => {
    // 2026-10-06 用户裁定。原先是 `left: '30%', width: '40%'`（「四边各留三成」）——
    // 那是这张图**还占满整页宽**时按构图定的。页① 改成左右分栏之后卡片只剩一半，
    // 同一组百分比把图幅压到约 190px，留白却原样留着，用户的原话是
    // 「图表部分距离卡片的边缘还有很长一段距离」。
    // 这条钉的不是哪两个数，是**那片白**：左右留白合计超过一成，就是又犯了一遍。
    const g = buildSensorLayoutOption(ds(), ARCH, PALETTE).grid as Record<string, string>
    const pct = (s: string) => Number.parseFloat(s) / 100
    const left = pct(g.left)
    const width = pct(g.width)
    expect(left + width, '左右留白合计超过一成：图又缩回卡片中间了')
      .toBeGreaterThanOrEqual(0.9)
    expect(left + width, '图幅加左距超出了卡片').toBeLessThanOrEqual(1)
    expect(left, '左边放不下纵轴刻度').toBeGreaterThanOrEqual(0.08)
  })

  it('轴只有一根，不再有 gridIndex', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    expect(o.xAxis).not.toBeInstanceOf(Array)
    expect(o.yAxis).not.toBeInstanceOf(Array)
    expect(o.xAxis.gridIndex).toBeUndefined()
    expect(o.yAxis.gridIndex).toBeUndefined()
  })

  it('「无测量带」那条虚线撤下 —— 它原来正好从 B1、B2 两个点上穿过去', () => {
    // 用户 2026-10-06 裁定去掉。原先画在 z = 1.10 m，而顶层两个测点的 z 也是
    // 1.10 —— 线是压在点上的，所以它既没标出「带」在哪，又让人以为那两个点
    // 落在带里。这条约束改由下方的口径说明用文字交代。
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    expect(series(o).some((s) => s.name === '无测量带')).toBe(false)
  })

  it('纵轴不从 0 起：图幅框住拱与测点，不空出一大截地面', () => {
    // 拱脚在 z ≈ 0.45 m，最低测点在 0.40 —— 从 0 起画，下面四成是空的。
    // 用户那张参考图同样把下界抬到了 z ≈ 0.25。
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    expect(o.yAxis.min).toBe(0.2)
    expect(o.yAxis.max).toBe(ARCH.z_max)
  })

  it('双向网格线打开：横线每 0.2 m、竖线每 0.5 m，与参考图同一步长', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    expect(o.xAxis.interval).toBe(0.5)
    expect(o.yAxis.interval).toBe(0.2)
    expect(o.xAxis.splitLine.show).toBe(true)
    expect(o.yAxis.splitLine.show).toBe(true)
    expect(o.xAxis.splitLine.lineStyle.color).toBe(PALETTE.steel)
    expect(o.yAxis.splitLine.lineStyle.color).toBe(PALETTE.steel)
  })

  it('刻度数字打开，轴名交代量纲', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    expect(o.xAxis.axisLabel.show).toBe(true)
    expect(o.yAxis.axisLabel.show).toBe(true)
    expect(o.xAxis.name).toBe('棚长 x / m')
    expect(o.yAxis.name).toBe('高度 z / m')
  })

  it('没有矩形外框：轴线本身仍然关着', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    expect(o.xAxis.axisLine.show).toBe(false)
    expect(o.yAxis.axisLine.show).toBe(false)
  })

  it('拱线用的是后端给的那一条，一个点不加一个点不减', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    const arches = series(o).filter((s) => s.name === '拱形轮廓')
    expect(arches).toHaveLength(1)
    expect(arches[0].data).toEqual(ARCH.arch)
    expect(arches[0].lineStyle.color).toBe(PALETTE.ink)
  })

  it('测点按高度分三层，一层一条系列，颜色按层从高到低取', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    const sc = scatters(o)
    expect(sc).toHaveLength(3)
    expect(sc.map((s) => s.itemStyle.color))
      .toEqual([PALETTE.layerTop, PALETTE.layerMid, PALETTE.layerLow])
    // 每层的点数：顶层 2、中层 3、底层 3
    expect(sc.map((s) => s.data.length)).toEqual([2, 3, 3])
  })

  it('每个测点带编号，且编号就是后端给的那一个', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    const labels = scatters(o).flatMap((s) =>
      s.data.map((d: number[]) => s.label.formatter({ data: d })))
    expect(labels.sort()).toEqual(['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8'])
  })

  it('点旁的编号来自后端：拿不到就空着，不就地编一个', () => {
    // 编号是后端按「层从高到低、同层 x 从左到右」排的（`point_codes`）。
    // 缺了就是缺了 —— 就地补一个序号，图上会多出一个**错的**编号，
    // 而错的编号和对的看起来一模一样。
    const bad = ds()
    bad.point_codes = {}
    const o = buildSensorLayoutOption(bad, ARCH, PALETTE) as Record<string, any>
    const labels = scatters(o).flatMap((s) =>
      s.data.map((d: number[]) => s.label.formatter({ data: d })))
    expect(labels.every((t: string) => t === '')).toBe(true)
  })

  it('测点的横纵坐标就是后端给的那两个数', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    const all = scatters(o).flatMap((s) => s.data as number[][])
    const xs = all.map((d) => d[0]).sort((a, b) => a - b)
    const zs = all.map((d) => d[1]).sort((a, b) => a - b)
    expect(xs).toEqual([0.15, 0.4, 0.8, 1.05, 1.05, 1.3, 1.7, 1.95])
    expect(zs).toEqual([0.4, 0.4, 0.4, 0.7, 0.7, 0.7, 1.1, 1.1])
  })

  it('tooltip 报三座棚的 5 天均值 —— 只画一个切面之后，均值只剩这一处出口', () => {
    const o = buildSensorLayoutOption(ds(), ARCH, PALETTE) as Record<string, any>
    const html = o.tooltip.formatter({ data: datumOf(o, 'B4') })
    expect(html).toContain('B4')
    expect(html).toContain('30.4')      // p1
    expect(html).toContain('31.2')      // p2
    expect(html).toContain('29.8')      // p3
  })

  it('tooltip 里的均值缺失时写「无值」，不编一个数', () => {
    const bad = ds()
    bad.temperature = bad.temperature.filter((t) => t.shed !== 'p2')
    const o = buildSensorLayoutOption(bad, ARCH, PALETTE) as Record<string, any>
    const html = o.tooltip.formatter({ data: datumOf(o, 'B4') })
    expect(html).toContain('无值')
    expect(html).not.toContain('NaN')
  })

  it('全图的颜色只来自调色板，且没有第八个颜色', () => {
    const flat = JSON.stringify(buildSensorLayoutOption(ds(), ARCH, PALETTE))
    // 先证明「它真的画了颜色」—— 否则下面那条 foreign 会在「一个色都没有」时空转通过。
    const used = [PALETTE.paper, PALETTE.ink, PALETTE.steel,
      PALETTE.layerTop, PALETTE.layerMid, PALETTE.layerLow]
    for (const c of used) expect(flat.toUpperCase()).toContain(c.toUpperCase())
    const allowed = new Set(paletteColors(PALETTE).map((c) => c.toUpperCase()))
    const hexes = [...flat.matchAll(/#[0-9A-Fa-f]{6}/g)].map((m) => m[0].toUpperCase())
    const foreign = [...new Set(hexes.filter((h) => !allowed.has(h)))]
    expect(foreign, `这些色不在调色板里：${foreign.join('、')}`).toEqual([])
  })
})
