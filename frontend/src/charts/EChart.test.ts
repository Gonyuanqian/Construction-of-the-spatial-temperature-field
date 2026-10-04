import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

/**
 * 这个测试**不渲染真的 ECharts**（jsdom 里没有 canvas）。
 * 它把 `echarts.init` 换成一个假的实例：一个目的是握住 `on('click', …)`
 * 注册进去的那个回调（模拟"用户点了一格"），另一个目的是握住实例本身，
 * 好断言卸载时 `dispose` 真的被调用了。
 *
 * 要验证的性质只有两条：
 * **ECharts 的 click 必须变成组件的 pick 事件**，以及**卸载必须销毁实例**。
 * 中间断了的话，页③ 上点格子什么都不会发生、且不报错；或者来回切页会攒下
 * 一堆活着的实例（每个都挂着 ResizeObserver）。
 */
const handlers: Record<string, (p: unknown) => void> = {}

type FakeChart = {
  setOption: ReturnType<typeof vi.fn>
  resize: ReturnType<typeof vi.fn>
  dispose: ReturnType<typeof vi.fn>
  on: (name: string, fn: (p: unknown) => void) => void
  off: ReturnType<typeof vi.fn>
}

// 握住最近一次 `echarts.init` 造出来的假实例，测试才能对它断言（例如 dispose 被调用）。
let fake: FakeChart | null = null

vi.mock('echarts', () => ({
  init: () => (fake = {
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
    fake = null
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
    expect(fake, '没拿到实例 —— 假 echarts 的 init 没被调用').not.toBeNull()
    expect(() => w.unmount()).not.toThrow()
    expect(fake!.dispose).toHaveBeenCalledTimes(1)
  })
})
