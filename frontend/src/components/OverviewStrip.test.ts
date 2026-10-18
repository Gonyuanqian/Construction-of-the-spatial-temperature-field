/**
 * 概览那一条与圆环仪表。两件都是**通用展示件**：不认识页⑤，不认识温度。
 * 这一组钉的就是那条边界 —— 它们只收已经格式化好的字符串与一个 0–1 的比例。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import GaugeDial from './GaugeDial.vue'
import OverviewStrip from './OverviewStrip.vue'

const CELLS = [
  { key: 'mean', label: '棚内平均温度', value: '26.5 °C', tone: 'plain' as const },
  { key: 'scene', label: '棚体三维温度场', value: '已生成', tone: 'ok' as const },
]

describe('OverviewStrip', () => {
  it('一格两行：标签、值。按 key 渲染，值是原样的字符串', () => {
    const w = mount(OverviewStrip, { props: { cells: CELLS } })
    expect(w.findAll('.cell')).toHaveLength(2)
    expect(w.text()).toContain('棚内平均温度')
    expect(w.text()).toContain('26.5 °C')
    // ⚠️ 2026-10-16 用户裁定：每格那**第三行副文案**（原先就是 `.sub` 那一行，
    // 「拱形以内、z 不高于 1.10 m」那几句）整块撤了 —— 页⑤ 的中央那一屏要
    // 三块同屏不滚动，每格一行就是几十像素。反面在这儿钉一条：那个类一旦
    // 回来，这一屏的账就得重算，而它在屏上只表现为「底栏又看不见了」。
    expect(w.find('.sub').exists(), '`.sub` 那一行又回来了').toBe(false)
    expect(w.findAll('.cell')[0]!.element.children, '一格不止两行了').toHaveLength(2)
  })

  it('语气走类名，不做任何判断', () => {
    // 值是「已生成」还是「取数失败」由**页面**说了算（`sceneText` 那一处）。
    // 这一层再判一次，就是同一件事的第二处判定。
    const w = mount(OverviewStrip, { props: { cells: CELLS } })
    expect(w.findAll('.value')[1]!.classes()).toContain('ok')
    expect(w.findAll('.value')[0]!.classes()).toContain('plain')
  })

  it('每格有一个具名插槽留位给图标 —— 本轮一律空着', () => {
    // 用户裁定「请先复现整体结构，再精修图标」。插槽在，图标不在。
    const w = mount(OverviewStrip, {
      props: { cells: CELLS },
      slots: { 'icon-mean': '<i class="ico-test" />' },
    })
    expect(w.find('.ico-test').exists(), '具名插槽没接上').toBe(true)
    expect(w.findAll('.ico .ico-test')).toHaveLength(1)
  })
})

describe('GaugeDial', () => {
  it('弧长按比例走，比例是调用者给的', () => {
    const w = mount(GaugeDial, { props: { frac: 0.5, valueText: '26.5 °C', label: '棚内平均温度' } })
    const arc = w.find('.arc')
    expect(arc.exists()).toBe(true)
    const dash = arc.attributes('stroke-dasharray') ?? ''
    const [on, total] = dash.split(' ').map(Number)
    expect(on! / total!, '弧长不是比例的一半').toBeCloseTo(0.5, 2)
  })

  it('读数与标签都原样印，不认识温度', () => {
    const w = mount(GaugeDial, { props: { frac: 0, valueText: '不报数', label: '棚内平均温度' } })
    expect(w.text()).toContain('不报数')
    expect(w.text()).toContain('棚内平均温度')
  })

  it('颜色由调用者给；不给时兜一个主色，不写死十六进制', () => {
    // ⚠️ 十六进制在这个仓里只许出现在 `tokens.css` 与 `charts/scale.ts`。
    // 所以兜底那一档必须走 `var(--leaf)`，而它只能写在**样式**里
    // （SVG 的表现属性不认 `var()`）。
    const w = mount(GaugeDial, { props: { frac: 0.2, valueText: '26.5 °C', label: '均温' } })
    expect(w.html()).not.toMatch(/#[0-9A-Fa-f]{3,8}\b/)
    expect(w.find('.arc').attributes('style') ?? '').toContain('var(--leaf)')
  })
})
