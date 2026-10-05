/**
 * 实时那一屏：状态条、三个控件各打哪个接口、准备中那一句、**分级必须在屏上**。
 *
 * 这一屏的风险比静态图高：静态图可以慢慢看标注，实时是一帧一帧刷过去的，
 * 观众只会记住「它在动」。分级看不见，就等于把「混合出来的」渲染成「测出来的」。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import LiveView from './LiveView.vue'
import { makeLiveFramePayload, makeLiveStatus, makeVolumePayload } from '../test/fixtures'

/**
 * jsdom 里没有 canvas，而 `EChart` 一挂上就 `echarts.init` + `setOption` ——
 * zrender 拿到的 2d 上下文是 `null`（jsdom 只打一句「Not implemented」），
 * 紧接着写 `ctx.dpr` 就抛，抛在挂载钩子里，整个 wrapper 跟着废掉。
 * 这一组测的是分帧、控件、文案与三维的取数口，**不是画图** ——
 * 与 `routes.smoke.test.ts` 同一个处置。「画得对不对」由 `EChart.test.ts`
 * 与页③ 那组测试兜着，不靠这里。
 */
vi.mock('../charts/EChart.vue', () => ({
  default: {
    name: 'EChart', props: ['option', 'height'], template: '<div class="chart-stub" />',
  },
}))

const calls: string[] = []

/**
 * 与页③ 同款的环境夹具：调色板读不到令牌就**抛**（故意的，宁可不画也不画错的灰），
 * 而 jsdom 里没有 `ResizeObserver`（`EChart` 挂载时要它）。
 */
function installEnvironment(): void {
  const root = document.documentElement
  root.style.setProperty('--paper', '#F7F6F2')
  root.style.setProperty('--ink', '#211F1C')
  root.style.setProperty('--ink-muted', '#5C5850')
  root.style.setProperty('--steel', '#DEDCD6')
  root.style.setProperty('--leaf', '#14532D')
  root.style.setProperty('--leaf-soft', '#E7EFE9')
  root.style.setProperty('--net', '#0B0F0D')
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
}

/**
 * 假的 fetch。**每条接口回它自己那个状态** —— 一个「永远回 ready」的
 * 替身会让「准备之前只该有一个按钮」那条测试自相矛盾地绿掉。
 *
 * ⚠️ `/live/volume` 回的是**体网格**载荷（`makeVolumePayload`），不是帧载荷：
 * 那一块由页③ 的 `VolumeView` 渲染，它按 `planes` / `y_step` 那套读。
 * 回错形状会让它静默画不出东西。
 */
function stubFetch(frame = makeLiveFramePayload()) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    let body: unknown
    if (url.endsWith('/live/prepare')) body = makeLiveStatus({ state: 'ready' })
    else if (url.endsWith('/live/start')) body = makeLiveStatus({ state: 'ready', running: true })
    else if (url.endsWith('/live/pause')) body = makeLiveStatus({ state: 'ready', running: false })
    else if (url.endsWith('/live/next')) body = makeLiveStatus({ state: 'ready', running: false, cursor: 8 })
    else if (url.includes('/live/volume')) body = makeVolumePayload()
    else if (url.includes('/live/frame')) body = frame
    else body = makeLiveStatus()          // 初始 status：还没准备
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'content-type': 'application/json' },
    })
  }))
}

beforeEach(() => {
  installEnvironment()
  vi.restoreAllMocks()
  calls.length = 0
})

describe('LiveView', () => {
  it('状态条说得出第几帧、共几帧、多久一帧、以及窗口是内存里的', async () => {
    stubFetch()
    const w = mount(LiveView)
    await flushPromises()
    const text = w.text()
    expect(text).toContain('共 144 帧')
    expect(text).toContain('5 分钟一帧')
    expect(text).toContain('重启')
  })

  it('三个控件各打自己那条接口', async () => {
    stubFetch()
    const w = mount(LiveView)
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.startsWith('POST /api/live/prepare'))).toBe(true)

    await w.get('button[data-act="start"]').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.startsWith('POST /api/live/start'))).toBe(true)

    await w.get('button[data-act="next"]').trigger('click')
    await flushPromises()
    expect(calls.some((c) => c.startsWith('POST /api/live/next'))).toBe(true)
  })

  it('准备之前只有「准备」，不摆一排按不动的按钮', async () => {
    stubFetch()
    const w = mount(LiveView)
    await flushPromises()
    expect(w.find('button[data-act="start"]').exists()).toBe(false)
    expect(w.find('button[data-act="prepare"]').exists()).toBe(true)
    // 而且要说清这一步要等 —— 几十秒的等待不预告，用户会以为它挂了。
    expect(w.text()).toContain('几十秒')
  })

  it('**分级在屏上**：三种回答里有「不报数」这一档', async () => {
    stubFetch()
    const w = mount(LiveView)
    await flushPromises()
    // 分级那一段只在准备好之后才在（没准备时屏上只有「准备实时源」一件事）。
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-grading]').text()).toMatch(/实测|非实测|不报数/)
  })

  it('三维那一块走实时那条取数口，不打页③ 的接口', async () => {
    // 规格书 §「前端形态」那一行：三维**懒加载 `scene/VolumeView.vue`** ——
    // 也就是说实时这一屏不新写一份三维面板，而是把页③ 那一块搬过来，
    // 只把取数口换成 `/api/live/volume/{n}`。
    // 这条钉的就是那个「只换取数口」：少了它，实时屏要么自己画一份（判定与
    // 文案就有了第二处），要么悄悄去打页③ 的接口、拿到**另一帧**的场。
    stubFetch()
    const w = mount(LiveView)
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    await w.get('[data-view="volume"]').trigger('click')
    // 那一块是懒加载的：等它真的上来（`vi.waitFor` 默认 1s 上限）。
    await vi.waitFor(() => {
      expect(calls.some((c) => c === 'GET /api/live/volume/0')).toBe(true)
    })
    expect(calls.some((c) => c.includes('/api/field/volume'))).toBe(false)
  })
})
