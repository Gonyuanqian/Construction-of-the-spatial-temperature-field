import { describe, expect, it } from 'vitest'

import { deltaStops, tempStops } from './scale'

/**
 * 这两条色标是「场 → 颜色」的**唯一**来源：V5 的切面图、V7 的三维图、
 * 以及页②那张残差热图都从这里取。所以它自己得先站得住。
 */
describe('温度色标', () => {
  it('是正向 cividis：暗蓝在低端、亮黄在高端', () => {
    // 反过来的话 52 °C 会是深蓝、42 °C 是亮黄 —— 每个人都会读反，
    // 而图上不会报任何错（spec §8.1 记着 Streamlit 版就是这么错的）。
    const s = tempStops()
    expect(s).toHaveLength(7)
    expect(s[0]).toBe('#00224E')       // 最暗的一端给低温
    expect(s[6]).toBe('#FFE945')       // 最亮的一端给高温
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
    expect(tempStops()[0]).toBe('#00224E')
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
    // 两条色标混用的话，ΔT 图上的零会被画成 cividis 的某个中间色，
    // 「没变」看起来像「有点热」。
    expect(deltaStops()).not.toEqual(tempStops())
  })
})
