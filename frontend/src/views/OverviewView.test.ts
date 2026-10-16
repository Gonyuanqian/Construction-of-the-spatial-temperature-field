import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OverviewView from './OverviewView.vue'
import { getJson } from '../api/client'
import { readPalette } from '../design/palette'
vi.mock('../api/client', async (original) => ({ ...await original<typeof import('../api/client')>(), getJson: vi.fn() }))
vi.mock('../design/palette', () => ({ readPalette: vi.fn() }))
const dataset = {
  n_times: 12, n_columns: 4, n_missing: 0, n_dup_times: 0,
  time_start: '2026-10-01T00:00:00', time_end: '2026-10-03T00:00:00',
  sheds: { p1: 2 }, positions: [{ id: 'a' }, { id: 'b' }], point_codes: { a: 'B1', b: 'B2' },
  temperature: [{ shed: 'p1', position: 'a', mean: 52 }, { shed: 'p1', position: 'b', mean: null }],
  checks: [{ no: 1, name: '时间轴', status: 'warn' }],
}
const mountView = (demo = false) => mount(OverviewView, { props: { demo }, global: { stubs: {
  RouterLink: { template: '<a><slot /></a>' },
  EChart: { name: 'EChart', props: ['option', 'height'], template: '<div />' },
} } })
beforeEach(() => {
  vi.mocked(readPalette).mockReturnValue({ ink: 'white', inkMuted: 'gray', leaf: 'cyan', bar: 'orange', steel: 'gray', paper: 'black' } as ReturnType<typeof readPalette>)
  vi.mocked(getJson).mockReset()
})
describe('作战总览的数据与空态', () => {
  it('演示模式无需后端即可填充图表，并明确标注模拟数据', async () => {
    const w = mountView(true); await flushPromises()
    expect(getJson).not.toHaveBeenCalled()
    expect(w.get('.demo-banner').text()).toContain('均为模拟数据')
    expect(w.findAll('.stat .value').map(x => x.text())).toEqual(['288', '52', '8', '0'])
    const charts = w.findAllComponents({ name: 'EChart' })
    expect(charts).toHaveLength(4)
    expect(charts[1]!.props('option').series[0].data).toHaveLength(36)
    expect(charts[3]!.props('option').series).toHaveLength(3)
    expect(w.findAll('.calendar .covered')).toHaveLength(6)
    w.unmount()
  })

  it('后端不可用时保留入口，不显示虚构指标或检查状态', async () => {
    vi.mocked(getJson).mockRejectedValue(new Error('HTTP 502'))
    const w = mountView(); await flushPromises()
    expect(w.text()).toContain('总览暂未取得数据')
    expect(w.findAll('.stat .value').every(x => x.text() === '—')).toBe(true)
    expect(w.find('.calendar').exists()).toBe(false)
    expect(getJson).toHaveBeenCalledTimes(1)
  })
  it('热力矩阵保留真实高温，排除缺失值，日历只标记采集覆盖', async () => {
    vi.mocked(getJson).mockImplementation(async (path) => path === '/api/dataset' ? dataset : { time: [], shed_mean: {} })
    const w = mountView(); await flushPromises()
    const heat = w.findAllComponents({ name: 'EChart' })[1]!.props('option')
    expect(heat.series[0].data).toEqual([[0, 0, 52]])
    expect(heat.visualMap.max).toBeGreaterThanOrEqual(52)
    expect(w.findAll('.calendar .covered')).toHaveLength(3)
    expect(w.find('.check-warning').text()).toContain('需关注')
    expect(w.text()).toContain('逐日风险记录暂未提供')
  })
})
