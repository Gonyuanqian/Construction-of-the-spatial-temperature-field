import { afterEach, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import TimedMonitoringControl from './TimedMonitoringControl.vue'

enableAutoUnmount(afterEach)
const props = { enabled: false, intervalMinutes: 15, nextAt: null, available: true }
it('提供间隔选择、开启和暂停，保留下一次更新时间', async () => {
  const w = mount(TimedMonitoringControl, { props, attachTo: document.body })
  await w.get('[aria-label="定时监测"]').trigger('click')
  expect(w.get('[role="dialog"]').attributes('aria-label')).toBe('定时监测设置')
  expect(w.findAll('option').map(n => n.attributes('value'))).toEqual(['5', '15', '30', '60'])
  expect(document.activeElement).toBe(w.get('select').element)
  await w.get('select').setValue('30'); expect(w.emitted('interval')).toEqual([[30]])
  await w.get('.timed-action').trigger('click'); expect(w.emitted('start')).toHaveLength(1)
  await w.setProps({ enabled: true, nextAt: Date.parse('2026-11-11T02:15:00Z') })
  expect(w.text()).toContain('监测中'); expect(w.text()).toContain('下次更新 10:15:00')
  await w.get('.timed-action').trigger('click'); expect(w.emitted('stop')).toHaveLength(1)
  await w.get('select').trigger('keydown', { key: 'Escape' }); expect(w.find('[role="dialog"]').exists()).toBe(false)
  expect(document.activeElement).toBe(w.get('[aria-label="定时监测"]').element)
})
it('未选择地点时解释禁用；错误和暂缓状态明确，点外部关闭', async () => {
  const w = mount(TimedMonitoringControl, { props: { ...props, available: false } })
  await w.get('[aria-label="定时监测"]').trigger('click')
  expect(w.get('.timed-action').attributes('disabled')).toBeDefined(); expect(w.text()).toContain('请先选择监测地点')
  await w.setProps({ enabled: true, available: true, paused: true, error: '气象暂不可用' })
  expect(w.get('[role="status"]').text()).toContain('已暂缓更新'); expect(w.get('[role="alert"]').text()).toContain('下次定时重试')
  document.body.dispatchEvent(new Event('pointerdown', { bubbles: true })); await w.vm.$nextTick()
  expect(w.find('[role="dialog"]').exists()).toBe(false)
})
