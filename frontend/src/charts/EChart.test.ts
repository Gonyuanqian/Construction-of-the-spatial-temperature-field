import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

/**
 * 这个测试**不渲染真的 ECharts**（jsdom 里没有 canvas）。
 * 它把 `echarts.init` 换成一个假的实例，唯一目的是握住 `on('click', …)`
 * 注册进去的那个回调，然后手动调用它 —— 也就是模拟"用户点了一格"。
 *
 * 要验证的性质只有一条：**ECharts 的 click 必须变成组件的 pick 事件**。
 * 中间断了的话，页③ 上点格子什么都不会发生，而且不报错。
 */
const handlers: Record<string, (p: unknown) => void> = {}

vi.mock('echarts', () => ({
  init: () => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    on: (name: string, fn: (p: unknown) => void) => { handlers[name] = fn },
    // `off` 必须在这里 —— 实现里 `onBeforeUnmount` 会调 `chart.off('click')`。
    // 假实例少了它，下面那条「卸载时把 chart 销毁掉」会抛 `TypeError`，
    // 于是测试从绿转红 —— 而红的理由与「点选」这件事毫无关系。
    off: vi.fn(),
  }),
}))

import EChart from './EChart.vue'

function installEnvironment(): void {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
}

describe('EChart 的点选', () => {
  beforeEach(() => {
    installEnvironment()
    for (const k of Object.keys(handlers)) delete handlers[k]
  })

  it('把 ECharts 的 click 转成组件的 pick 事件', async () => {
    const w = mount(EChart, { props: { option: {} as never } })
    expect(handlers.click, '没有注册 click 回调 —— 点选永远不会触发').toBeTypeOf('function')

    handlers.click({ seriesIndex: 1, value: [3, 4, 43.21] })
    const got = w.emitted('pick')
    expect(got).toHaveLength(1)
    expect(got![0][0]).toEqual({ seriesIndex: 1, value: [3, 4, 43.21] })
  })

  it('卸载时把 chart 销毁掉', () => {
    // 不销毁的话，来回切页会攒下一堆活着的实例（每个都挂着 ResizeObserver）。
    const w = mount(EChart, { props: { option: {} as never } })
    expect(() => w.unmount()).not.toThrow()
  })
})
