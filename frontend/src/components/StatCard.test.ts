import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StatCard from './StatCard.vue'

describe('指标卡', () => {
  it('标签、读数、出处三行都在，出处是一个字加一句 title', () => {
    const w = mount(StatCard, {
      props: { label: '个时刻', value: '1308', prov: 'pack' },
    })
    expect(w.find('.label').text()).toBe('个时刻')
    expect(w.find('.value').text()).toBe('1308')
    const stamp = w.find('.prov')
    expect(stamp.text()).toBe('包')
    expect(stamp.attributes('title')).toContain('随标定包')
  })

  it('没有出处时第三行留空，但仍然占位 —— 一排卡片高度要齐平', () => {
    const w = mount(StatCard, {
      props: { label: '无测量带', value: 'z > 1.10 m 不报数', compact: true, muted: true },
    })
    expect(w.find('.stamp').exists()).toBe(true)
    expect(w.find('.stamp').text()).toBe('')
  })

  it('长标识串用 compact，读数仍然原样印出来', () => {
    const w = mount(StatCard, {
      props: { label: '指纹', value: '6145fa9261e89f1b', prov: 'live', compact: true },
    })
    expect(w.find('.value').classes()).toContain('compact')
    expect(w.find('.value').text()).toBe('6145fa9261e89f1b')
  })

  it('muted 与 compact 是两回事：不报数压暗，长串只是小一号', () => {
    const w = mount(StatCard, {
      props: { label: '无测量带', value: '不报数', compact: true, muted: true },
    })
    expect(w.find('.value').classes()).toContain('compact')
    expect(w.find('.value').classes()).toContain('muted')
  })

  it('不是表格，也不含标题标签 —— 页③/页② 按形状找元素（spec §十三.1）', () => {
    const w = mount(StatCard, { props: { label: '列', value: '52' } })
    expect(w.find('table').exists()).toBe(false)
    expect(w.find('h2').exists()).toBe(false)
    expect(w.find('h3').exists()).toBe(false)
  })

  it('读数不带计算：传进来是什么就印什么', () => {
    const w = mount(StatCard, { props: { label: '起', value: '2026-07-23 11:00' } })
    expect(w.find('.value').text()).toBe('2026-07-23 11:00')
  })
})
