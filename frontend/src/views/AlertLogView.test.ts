import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { warningsApi, type WarningEvent } from '../api/warnings'
import AlertLogView from './AlertLogView.vue'

vi.mock('../api/warnings', () => ({ warningsApi: { list: vi.fn(), acknowledge: vi.fn() } }))
vi.mock('../scene/VolumeView.vue', () => ({
  default: { name:'WarningVolumeStub', template: '<span>已打开历史构场</span>', props: ['sessionId', 'source', 'tIndex'] },
}))
enableAutoUnmount(afterEach)

const temperature: WarningEvent = {
  id: 'temperature-test', category: 'temperature', design_id: 'house-test', greenhouse_name: '人参棚 01',
  device_name: null, alert_type: 'high', source: 'real_time', operation: null, result: null,
  trigger_frame_id: 'test-frame', event_time: '2026-11-23T01:08:00Z', last_seen_at: '2026-11-23T01:10:00Z',
  threshold_value: 30, trigger_value: 32.8, extreme_value: 34.5, ended_at: null, end_reason: null,
  acknowledged_at: null, acknowledged_by: null,
}
const device: WarningEvent = {
  ...temperature, id: 'device-test', category: 'device', alert_type: 'skipped', source: 'scheduler',
  operation: 'task_run', device_name: '通风设备', result: { detail: '设备已停用' }, trigger_frame_id: null,
  threshold_value: null, trigger_value: null, extreme_value: null, last_seen_at: null,
}

it('选择记录、打开原始构场、确认已阅及切换设备分类', async () => {
  const greenhouses = [{ id: 'house-test', name: '人参棚 01', archived: false }]
  let current = temperature
  vi.mocked(warningsApi.list).mockImplementation(async filters => {
    const items = filters.category === 'device' ? [device] : [current, device]
    return { items, total: items.length, greenhouses }
  })
  vi.mocked(warningsApi.acknowledge).mockImplementation(async () => {
    current = { ...temperature, acknowledged_at: '2026-11-23T01:30:00Z', acknowledged_by: '值班用户' }
    return current
  })
  const w = mount(AlertLogView, { global: { stubs: { Teleport: true, RouterLink: RouterLinkStub } } })
  await flushPromises()
  expect(w.get('.detail-card').text()).toContain('34.5 °C')
  const button = (label: string) => w.findAll('button').find(item => item.text() === label)!
  await button('查看构场').trigger('click')
  await flushPromises()
  expect(w.get('[aria-label="预警触发时的温度场"]').text()).toContain('已打开历史构场')
  expect(w.getComponent({name:'WarningVolumeStub'}).props('sessionId')).toBe('test-frame')
  await button('关闭').trigger('click')
  await button('确认已阅').trigger('click')
  await flushPromises()
  expect(w.get('.detail-card').text()).toContain('值班用户')
  expect(w.get('.detail-card').text()).toContain('异常中')
  await button('设备告警').trigger('click')
  await flushPromises()
  expect(warningsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'device', offset: '0' }))
  expect(w.get('.detail-card').text()).toContain('设备已停用')
  expect(w.get('.detail-card').text()).toContain('模拟设备')
})
