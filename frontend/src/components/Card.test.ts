import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import Card from './Card.vue'

describe('卡片外壳', () => {
  it('展开后可用 Escape 收起，保留插槽内容', async () => {
    const w = mount(Card, { slots: { default: '<p>图表内容</p>' } })
    await w.get('button').trigger('click')
    expect(w.get('button').attributes('aria-expanded')).toBe('true')
    expect(w.classes()).toContain('is-expanded')
    await w.trigger('keydown', { key: 'Escape' })
    expect(w.classes()).not.toContain('is-expanded')
    expect(w.text()).toContain('图表内容')
    w.unmount()
  })

  it('把插槽里的东西原样收进来', () => {
    const w = mount(Card, { slots: { default: '<p class="inside">内容</p>' } })
    expect(w.find('.card').exists()).toBe(true)
    expect(w.find('.inside').text()).toBe('内容')
  })

  it('自己不带任何标题标签 —— 页② 按 h3 的条数找东西（spec §十三.1）', () => {
    const w = mount(Card)
    expect(w.find('h2').exists()).toBe(false)
    expect(w.find('h3').exists()).toBe(false)
  })

  it('外壳本身不可聚焦 —— 不进 Tab 序（Review Focus 4）', () => {
    // 卡片是纯展示。给它一个 tabindex，键盘用户每页要多按十几次才走得到控件。
    const w = mount(Card)
    expect(w.find('[tabindex]').exists()).toBe(false)
  })
})
