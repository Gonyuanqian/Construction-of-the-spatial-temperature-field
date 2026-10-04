import { describe, expect, it } from 'vitest'

import type { SectionsPayload, SectionShed } from '../../api/types'
import type { Palette } from '../../design/palette'
import { interpretPick, pickText } from '../pick'
import {
  buildSectionFieldOption, cellTooltip, SERIES_PER_SHED, shedOfSeries,
} from './sectionField'

const PALETTE: Palette = {
  paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850', steel: '#DEDCD6',
  leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
}

/** 4×4 的小场，四种格子各占一角（与 pick.test.ts 同一套夹具，便于对照）。 */
function makeShed(shed: string, y: number): SectionShed {
  return {
    shed, y,
    values: [
      [1, 2, 3, 4],
      [1, 2, 3, 4],
      [null, 2, 3, 4],
      [null, null, 3, 4],
    ],
    stripes: [[2, 0], [2, 1], [2, 2], [2, 3], [3, 2], [3, 3]],
  }
}

function makePayload(): SectionsPayload {
  return {
    t_index: 7, time: '2026-07-23T11:00:00', n_times: 1308,
    preset: 'standard', monotonic: true, calibrated: true,
    vmin: 0.9, vmax: 5.1, max_measured_z: 2,
    x_min: 0, x_max: 2.1, z_max: 1.3017,
    x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
    arch: [[0, 0], [2.1, 0]],
    sensors: [{ id: 'x0.7_z0.7', x: 0.7, z: 0.7, layer: 'z0.7' }],
    sheds: [makeShed('p1', 3), makeShed('p2', 9), makeShed('p3', 15)],
    note: '',
  }
}

/** option 的类型在构造器里是 EChartsOption，测试里按结构取用，所以放宽成 any。 */
const opt = (p: SectionsPayload) => buildSectionFieldOption(p, PALETTE) as any

describe('V5 切面场的骨架', () => {
  it('三个棚各占连续 5 条系列，共 15 条', () => {
    const o = opt(makePayload())
    expect(o.series).toHaveLength(3 * SERIES_PER_SHED)
    expect(SERIES_PER_SHED).toBe(5)
  })

  it('shedOfSeries 把任意系列下标映回它的棚', () => {
    const p = makePayload()
    expect(shedOfSeries(p, 0)).toBe('p1')
    expect(shedOfSeries(p, 4)).toBe('p1')
    expect(shedOfSeries(p, 5)).toBe('p2')
    expect(shedOfSeries(p, 9)).toBe('p2')
    expect(shedOfSeries(p, 10)).toBe('p3')
    expect(shedOfSeries(p, 14)).toBe('p3')
    expect(shedOfSeries(p, 15)).toBeNull()
    expect(shedOfSeries(p, -1)).toBeNull()
  })

  it('三格并排，各占一个 grid', () => {
    const o = opt(makePayload())
    expect(o.grid).toHaveLength(3)
    expect(o.xAxis).toHaveLength(3)
    expect(o.yAxis).toHaveLength(3)
    o.series.forEach((s: any, i: number) => {
      expect(s.xAxisIndex, `系列 ${i} 没绑到自己的 grid`).toBe(Math.floor(i / SERIES_PER_SHED))
      expect(s.yAxisIndex).toBe(Math.floor(i / SERIES_PER_SHED))
    })
  })
})

describe('三格共享一个色标（Review Focus 4）', () => {
  it('整个 option 只有**一个** visualMap', () => {
    const o = opt(makePayload())
    expect(Array.isArray(o.visualMap), 'visualMap 成了数组 —— 三格会各算各的').toBe(false)
    expect(o.visualMap).toBeTypeOf('object')
  })

  it('那一个色标的范围就是载荷给的 vmin/vmax', () => {
    const w = makePayload()
    const o = opt(w)
    expect(o.visualMap.min).toBe(w.vmin)
    expect(o.visualMap.max).toBe(w.vmax)
  })

  it('它恰好绑住三条热力场，一条不多一条不少', () => {
    // 绑少了：某一格不跟着色标走（自己一个颜色）。
    // 绑多了：拱线或测点会被温度色标重染 —— 那些记号就不是记号了。
    const o = opt(makePayload())
    expect(o.visualMap.seriesIndex).toEqual([1, 6, 11])
    expect(o.series[1].type).toBe('heatmap')
    expect(o.series[6].type).toBe('heatmap')
    expect(o.series[11].type).toBe('heatmap')
  })

  it('色标条不可拖拽', () => {
    // 拖动 visualMap 的把手会**过滤**数据（超范围的格子不画）。
    // 在这张图上那等于「拖着拖着有些格子消失了」——
    // 色标条在这里是图例，不是控制器。
    expect(opt(makePayload()).visualMap.calculable).toBe(false)
  })

  it('色标的颜色来自唯一来源，且是正向 cividis', () => {
    const o = opt(makePayload())
    const colors: string[] = o.visualMap.inRange.color
    expect(colors).toHaveLength(7)
    expect(colors[0]).toBe('#00224E')    // 低温 = 暗端
    expect(colors[6]).toBe('#FFE945')    // 高温 = 亮端
  })
})

describe('颜色只能来自那一个色标', () => {
  it('没有一个格子自带颜色', () => {
    // 谁自带 itemStyle.color，谁就脱离共享色标 —— 而图上看起来只是「这一格有点怪」。
    const o = opt(makePayload())
    for (const si of [1, 6, 11]) {
      for (const item of o.series[si].data) {
        expect(Array.isArray(item), '热力场的数据项必须是裸的 [ix, iz, v]').toBe(true)
      }
    }
  })

  it('热力场的数据项是 [ix, iz, 值]，且不含 null', () => {
    const o = opt(makePayload())
    const d = o.series[1].data
    // 样本必须 ix ≠ iz，且转置后的项不在数据里 —— 否则 [ix, iz, v] 与
    // [iz, ix, v] 在这两条断言下同样为真，测试就钉不住自己的名字。
    expect(d).toContainEqual([1, 0, 2])
    expect(d).toContainEqual([3, 2, 4])
    expect(d.some((x: any[]) => x[2] === null), '拱外不该进热力场').toBe(false)
  })
})

describe('拱外：留白，但仍然能点', () => {
  it('拱外的格子不在热力场里，却在遮罩系列里', () => {
    const o = opt(makePayload())
    const heat = new Set(o.series[1].data.map((x: any[]) => `${x[0]},${x[1]}`))
    const mask = new Set(o.series[0].data.map((x: any[]) => `${x[0]},${x[1]}`))
    expect(heat.has('0,2')).toBe(false)
    expect(mask.has('0,2')).toBe(true)
    expect(mask.has('0,3')).toBe(true)
    expect(mask.has('1,3')).toBe(true)
    expect(mask.has('0,0'), '拱内的格子不该进遮罩').toBe(false)
    expect([...heat].some((k) => mask.has(k)), '两个集合必须不相交').toBe(false)
  })

  it('遮罩画的是透明矩形', () => {
    // 不透明的遮罩会把拱外变成一块灰 —— 那看起来像是「那里有个值，只是没颜色」，
    // 而拱外是**没有定义**。
    const o = opt(makePayload())
    const out = o.series[0].renderItem({}, {
      value: (i: number) => [0, 2][i],
      coord: () => [0, 0],
      size: () => [10, 10],
    })
    expect(out.shape.width).toBe(10)
    expect(out.shape.height).toBe(10)
    expect(out.style.fill).toBe('transparent')
  })

  it('遮罩可以接点击，装饰性的三条系列不能', () => {
    const o = opt(makePayload())
    for (const i of [0, 1, 6, 11]) {
      expect(o.series[i].silent ?? false, `系列 ${i} 应该能接点击`).toBe(false)
    }
    for (const i of [2, 3, 4, 7, 8, 9, 12, 13, 14]) {
      expect(o.series[i].silent, `系列 ${i} 是装饰，不该接点击`).toBe(true)
    }
  })
})

describe('点选的三种回答在图上都到得了', () => {
  it('cellTooltip 三种回答各给各的话', () => {
    const p = makePayload()
    expect(cellTooltip(p, 'p1', 2, 0)).toContain('不报数')
    expect(cellTooltip(p, 'p1', 0, 2)).toContain('无定义')
    expect(cellTooltip(p, 'p1', 1, 1)).toContain('现场重算')
  })

  it('拱内的实测格子给出的数与格子里那个数一致', () => {
    const p = makePayload()
    p.sheds[0].values[1][1] = 43.216137
    expect(cellTooltip(p, 'p1', 1, 1)).toContain('43.22')
  })

  it('cellTooltip 就是 pickText(interpretPick(…))，不是第二套判定', () => {
    // 判定散开写，「第四种回答」就会从其中一处漏出来（外推值被当成实测值，
    // 不报错，只是让人以为自己看到的是真的）。这条把「只有一处」钉死：
    // 只要 cellTooltip 自己重写哪怕一个字的措辞，这里就红。
    const payload = makePayload()
    const shed = payload.sheds[0]
    const seen = new Set<string>()
    for (let iz = 0; iz < shed.values.length; iz++) {
      for (let ix = 0; ix < shed.values[iz].length; ix++) {
        const r = interpretPick(payload, shed.shed, ix, iz)
        seen.add(r.kind)
        expect(cellTooltip(payload, shed.shed, ix, iz), `(${ix},${iz})`)
          .toBe(pickText(r, payload))
      }
    }
    // 顺带把「这一轮真的问过三种回答」也钉住 —— 否则夹具退化成只剩一种 kind 时，
    // 上面的循环仍在跑、却什么都没覆盖到。
    expect([...seen].sort()).toEqual(['outside', 'unmeasured', 'value'])
  })
})

describe('拱线、测点与斜纹', () => {
  it('拱线用载荷给的折线，不自己算拱', () => {
    const p = makePayload()
    const o = opt(p)
    expect(o.series[3].type).toBe('line')
    // 轴是 **category**（`xAxis.data` 是 `payload.x.map(String)` 出来的类别名），
    // 所以折线的取值必须是**类别名本身**，不能是数字 —— 数字在类别轴上被当
    // **下标**读，而 `2.1` 这个下标是无效的。断言照着实现该产出的形状写。
    expect(o.series[3].data).toEqual(p.arch.map(([x, z]) => [String(x), String(z)]))
  })

  it('测点画的是载荷给的点位', () => {
    const p = makePayload()
    const o = opt(p)
    expect(o.series[2].type).toBe('scatter')
    // 同拱线那条：类别轴上的取值是类别名（字符串），不是数字下标。
    expect(o.series[2].data).toEqual(p.sensors.map((s) => [String(s.x), String(s.z)]))
  })

  it('斜纹画在无测量带的格子上，且用令牌里的颜色', () => {
    const p = makePayload()
    const o = opt(p)
    expect(o.series[4].data).toEqual(p.sheds[0].stripes)
    const item = o.series[4].renderItem({}, {
      value: (i: number) => [2, 0][i],
      coord: () => [100, 100],
      size: () => [10, 10],
    })
    expect(item.children.length).toBeGreaterThan(0)
    // 斜纹的颜色取自令牌 —— 这里断言的是「等于传进来的那份调色板里的值」。
    // ⚠️ **别再补一条 `not.toMatch(/#[0-9A-Fa-f]{6}/)`。** 那条永远不可能过：
    // 运行时 `p.inkMuted` 本来就是一个十六进制字符串（`readPalette` 读的是
    // `getComputedStyle`，因为 canvas 不认 `var(--…)`，见 palette.ts 的模块注释），
    // 所以「等于令牌值」与「不是十六进制」在**运行时**是同一句话，写两条必然自相矛盾。
    // 「源码里不许出现字面十六进制」是**源码层**的性质，由 `design/guards.test.ts`
    // 的十六进制白名单守着（`charts/**` 下只有白名单文件可以出现字面色）。
    expect(item.children[0].style.stroke).toBe(PALETTE.inkMuted)
  })

  it('三个棚的标题写清了各自的 y', () => {
    const p = makePayload()
    const texts = (opt(p).title as any[]).map((t) => t.text)
    expect(texts).toEqual(['p1（y = 3 m）', 'p2（y = 9 m）', 'p3（y = 15 m）'])
  })
})
