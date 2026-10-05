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
  // **替身必须与真后端同形，否则它守不住任何东西。** 两处照真契约来：
  //
  // ① `prepare` 的回执**只有** `{state, seconds}`（规格书 §五）—— 回一份完整的
  //    `LiveStatus` 会让「前端把回执当状态用」这个 bug 在这组测试里凭空消失。
  //    这条替身原来就是这么写的，于是那个 bug 一路绿着走到了终审。
  // ② `status` 得**有状态**：prepare 之前 idle、之后 ready，start / pause 改 running。
  //    回一个写死的状态，页面永远走不到第二条分支，控件那一组也白测。
  let prepared = false
  let running = false
  let cursor = 0
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    let body: unknown
    if (url.endsWith('/live/prepare')) {
      prepared = true
      body = { state: 'ready', seconds: 2.3 }      // 真形状：不是 LiveStatus
    } else if (url.endsWith('/live/start')) {
      running = true
      body = makeLiveStatus({ state: 'ready', running: true })
    } else if (url.endsWith('/live/pause')) {
      running = false
      body = makeLiveStatus({ state: 'ready', running: false })
    } else if (url.endsWith('/live/next')) {
      cursor = 8
      body = makeLiveStatus({ state: 'ready', running, cursor })
    } else if (url.includes('/live/volume')) body = makeVolumePayload()
    else if (url.includes('/live/frame')) body = frame
    else body = makeLiveStatus({ state: prepared ? 'ready' : 'idle', running, cursor })
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

  it('`prepare` 的回执不是状态 —— 点完它状态条要有数', async () => {
    // 规格书 §五：`POST /api/live/prepare` 回的是 `{state, seconds}`，**不是** LiveStatus。
    // 把回执当状态用，状态条会渲染成「第  帧，共  帧，0 秒一帧」，
    // 而 `frame.run()` 会拼出 `/api/live/frame/undefined`（真后端 422，
    // 前端再把它显示成 `[object Object]`）—— 这是实时模式**唯一**的入口动作，
    // 点下去看到的是一屏错误。
    stubFetch()
    const w = mount(LiveView)
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    expect(w.text()).toContain('共 144 帧')
    expect(w.text()).not.toContain('undefined')
    expect(calls.some((c) => c.includes('/live/frame/undefined'))).toBe(false)
    expect(w.find('[role="alert"]').exists()).toBe(false)
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

  it('暂停时不轮询，走起来才轮询（规格书 §6.3 与 §8.2 的验收项）', async () => {
    // ⚠️ **两半都要断。** 只断「暂停时没多问一次」的话，把定时器整个删掉也照样
    // 绿 —— 那是一条靠「什么都没发生」通过的测试。所以第二半把「走起来必须问」
    // 也钉上，两半合起来才等于「轮询开关跟着 running 走」。
    //
    // `toFake` 只给定时器：`flushPromises()` 自己也走 `setTimeout(…, 0)`，
    // 把它一起伪掉的话每个 `await flushPromises()` 都会挂死。
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      stubFetch()
      const w = mount(LiveView)
      await flushPromises()
      await w.get('button[data-act="prepare"]').trigger('click')
      await flushPromises()

      const statusCalls = () => calls.filter((c) => c === 'GET /api/live/status').length

      const paused = statusCalls()
      await vi.advanceTimersByTimeAsync(15000)     // 三个轮询周期
      expect(statusCalls()).toBe(paused)           // 暂停：一次都不许多问

      await w.get('button[data-act="start"]').trigger('click')
      await flushPromises()

      const running = statusCalls()
      await vi.advanceTimersByTimeAsync(5000)      // 一个轮询周期
      expect(statusCalls()).toBeGreaterThan(running)   // 走起来：必须问
    } finally {
      vi.useRealTimers()
    }
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
