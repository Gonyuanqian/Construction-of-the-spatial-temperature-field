import { describe, expect, it } from 'vitest'

import { deltaStops, hexToRgb, tempStops, valueToColor } from './scale'

/**
 * 这两条色标是「场 → 颜色」的**唯一**来源：V5 的切面图、V7 的三维图、
 * 以及页②那张残差热图都从这里取。所以它自己得先站得住。
 */
describe('温度色标', () => {
  it('是正向 turbo：暗紫蓝在低端、暗红在高端', () => {
    // 反过来的话 52 °C 会是深蓝、42 °C 是亮黄 —— 每个人都会读反，
    // 而图上不会报任何错（spec §8.1 记着这个坑：整张图读反了，屏上一切正常）。
    // ⚠️ 2026-10-12 用户裁定从 cividis 换成 turbo（「换 turbo，全站统一」）——
    // 参考图那条彩虹色带就是 turbo 的长相，而 turbo 是彩虹系里专门设计来
    // 修正 jet 那些假亮带的。
    const s = tempStops()
    expect(s).toHaveLength(9)
    expect(s[0]).toBe('#30123B')       // 最暗的一端给低温
    expect(s[8]).toBe('#7A0403')       // 最暗的红那一端给高温
  })

  it('不等于它自己的倒序', () => {
    // 这条听起来废话，但它正是「抄错方向」这个 bug 的形状：
    // 上面那两条断言在倒过来之后**仍然会**通过（如果只断言了长度与首尾属于集合）。
    // 显式比一次倒序，把方向钉死。
    expect(tempStops()).not.toEqual([...tempStops()].reverse())
  })

  it('每次调用返回新数组，改一个不影响另一个', () => {
    // 同一个数组引用被交给 ECharts、又交给别处，是最容易被下游改坏的一类共享状态。
    const a = tempStops()
    a[0] = '#000000'
    expect(tempStops()[0]).toBe('#30123B')
  })
})

describe('差异色标', () => {
  it('是发散色标：两端是蓝与红，中点接近无彩色', () => {
    const s = deltaStops()
    expect(s).toHaveLength(11)
    expect(s[0]).toBe('#053061')       // 负端：深蓝
    expect(s[10]).toBe('#67001F')      // 正端：深红
    expect(s[5]).toBe('#F7F7F7')       // 中点：近白 —— 发散色标的中点必须是中性色
  })

  it('温度色标与差异色标不是同一条', () => {
    // 两条色标混用的话，ΔT 图上的零会被画成温度色标的某个中间色，
    // 「没变」看起来像「有点热」。
    expect(deltaStops()).not.toEqual(tempStops())
  })
})

describe('值 → 颜色', () => {
  const stops = tempStops()
  const VMIN = 42.1
  const VMAX = 52.8
  /** 第 i 个采样点所在的温度。 */
  const atStop = (i: number): number => VMIN + ((VMAX - VMIN) * i) / (stops.length - 1)

  it('九个采样点的位置上逐个等于采样点自己的色值', () => {
    // 规格书 §5.4 的验收。二维那边的插值是 ECharts 的 `visualMap` 在**内部**做的，
    // 我们碰不到 —— 所以「V5 与 V7 共用同一个光栅化函数」按字面做不到。
    // 落成能执行的一条：共用同一组 stops、同一条插值规则，然后**在采样点上逐点对拍**。
    for (let i = 0; i < stops.length; i++) {
      expect(valueToColor(atStop(i), VMIN, VMAX, stops), `第 ${i} 个采样点`)
        .toEqual(hexToRgb(stops[i]))
    }
  })

  it('采样点之间按 RGB 线性插值', () => {
    // 第一段的中点（九档时 t = 1/16）。三个通道从 stop0 到 stop1 都是**单调增**的，
    // 所以「严格落在两者之间」不需要猜具体的舍入值 —— 而写成确切数字的话，
    // 这条测试就只是在重抄实现。
    const a = hexToRgb(stops[0])
    const b = hexToRgb(stops[1])
    const m = valueToColor(VMIN + (VMAX - VMIN) / 16, VMIN, VMAX, stops)
    for (let i = 0; i < 3; i++) {
      expect(m[i], `第 ${i} 个通道`).toBeGreaterThan(a[i])
      expect(m[i], `第 ${i} 个通道`).toBeLessThan(b[i])
    }
  })

  it('两端之外夹到端点色，不给范围外的颜色', () => {
    expect(valueToColor(VMIN - 100, VMIN, VMAX, stops)).toEqual(hexToRgb(stops[0]))
    expect(valueToColor(VMAX + 100, VMIN, VMAX, stops)).toEqual(hexToRgb(stops[8]))
  })

  it('值域塌成零宽时取最低端，不返回 NaN', () => {
    // vmax === vmin 时 (v - vmin) / 0 是 NaN。一个 NaN 颜色会让**整片场**沉掉 ——
    // 而 `Uint8ClampedArray` 会把 NaN 悄悄写成 0（黑），看起来像「很冷」。
    const c = valueToColor(50, 50, 50, stops)
    expect(c).toEqual(hexToRgb(stops[0]))
    expect(c.every((n) => Number.isFinite(n))).toBe(true)
  })

  it('值是 NaN 时也不返回 NaN 颜色', () => {
    const c = valueToColor(Number.NaN, VMIN, VMAX, stops)
    expect(c).toEqual(hexToRgb(stops[0]))
    expect(c.every((n) => Number.isFinite(n))).toBe(true)
  })
})

describe('hexToRgb', () => {
  it('六位与三位都认得，且不区分大小写', () => {
    expect(hexToRgb('#30123B')).toEqual([48, 18, 59])
    expect(hexToRgb('#30123b')).toEqual([48, 18, 59])
    expect(hexToRgb('#fff')).toEqual([255, 255, 255])
  })

  it('九个温度采样点解出来都在 0 至 255 之间', () => {
    for (const s of tempStops()) {
      for (const c of hexToRgb(s)) {
        expect(c).toBeGreaterThanOrEqual(0)
        expect(c).toBeLessThanOrEqual(255)
      }
    }
  })
})
