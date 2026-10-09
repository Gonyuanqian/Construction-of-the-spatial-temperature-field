/**
 * 实时那一屏：状态条、三个控件各打哪个接口、准备中那一句、**分级必须在屏上**。
 *
 * 这一屏的风险比静态图高：静态图可以慢慢看标注，实时是一帧一帧刷过去的，
 * 观众只会记住「它在动」。分级看不见，就等于把「混合出来的」渲染成「测出来的」。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import { createMemoryHistory } from 'vue-router'

import LiveView from './LiveView.vue'
import { createAppRouter } from '../router'
import { FIELD_MODEL } from '../design/copy'
import { makeLiveFramePayload, makeLiveStatus, makeModelsPayload,
         makeVolumePayload } from '../test/fixtures'

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
  root.style.setProperty('--layer-top', '#C44E52')
  root.style.setProperty('--layer-mid', '#4C72B0')
  root.style.setProperty('--layer-low', '#55A868')
  root.style.setProperty('--bar', '#D98C2B')
  root.style.setProperty('--size-chart-axis', '12px')
  root.style.setProperty('--size-chart-title', '14px')
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
function stubFetch(frame = makeLiveFramePayload(),
                   models: unknown = makeModelsPayload(),
                   modelsStatus = 200) {
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
    let status = 200
    if (url.includes('/api/models')) { body = models; status = modelsStatus }
    else if (url.endsWith('/live/prepare')) {
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
      status, headers: { 'content-type': 'application/json' },
    })
  }))
}

/** 空态那一支挂着 `<RouterLink>`，所以每一处挂载都要带路由 ——
   不给的话 Vue 按未知标签渲染并打警告，断言照样绿但每次都刷一遍。 */
function mountLive() {
  return mount(LiveView, {
    global: { plugins: [createAppRouter(createMemoryHistory())] },
  })
}

beforeEach(() => {
  installEnvironment()
  vi.restoreAllMocks()
  calls.length = 0
})

describe('LiveView', () => {
  it('状态条说得出第几帧、共几帧、多久一帧、以及窗口是内存里的', async () => {
    stubFetch()
    const w = mountLive()
    await flushPromises()
    const text = w.text()
    expect(text).toContain('共 144 帧')
    expect(text).toContain('5 分钟一帧')
    expect(text).toContain('重启')
  })

  it('三个控件各打自己那条接口', async () => {
    stubFetch()
    const w = mountLive()
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
    const w = mountLive()
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
    const w = mountLive()
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
    const w = mountLive()
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
      const w = mountLive()
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
    const w = mountLive()
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

  it('一排四张指标卡，且都在报「算」（spec §6.2 页⑤）', async () => {
    stubFetch()
    const w = mountLive()
    await flushPromises()
    const cards = w.findAll('.stat')
    expect(cards.map((c) => c.find('.label').text()))
      .toEqual(['帧', '共', '一帧', '本帧时刻'])
    for (const c of cards) expect(c.find('.prov').text()).toBe('算')
  })

  it('指标卡在状态还没 ready 时也立得住 —— 四格都不空', async () => {
    // 挂载后 status 是 idle（替身默认回的），`frame` 因此还没取。
    // 指标卡挂在 status 上、不挂在 frame 上，就是为了这时候四格仍在。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    for (const c of w.findAll('.stat')) {
      expect(c.find('.value').text(), `${c.find('.label').text()} 那一格是空的`).not.toBe('')
    }
  })

  it('散文折进唯一一处「口径与出处」', async () => {
    stubFetch()
    const w = mountLive()
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why.length).toBe(1)
    expect(why[0].find('summary').text()).toContain('口径与出处')
    // 折进去的东西还在 DOM 里（收起来不等于删掉 —— spec §八 选它不选弹层的理由）
    expect(why[0].text().length).toBeGreaterThan('口径与出处'.length)
  })

  it('「看哪一块」是一条分段控件，不是一排带圆角边框的按钮（spec §九 / 终审 I-1）', async () => {
    // 与页③ 的视图切换同一块 chrome、同一条要求：它得像个开关。
    // 这条与页③ 那条合起来才说明「两页共用一种控件」，只测一页等于没测另一半。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    const seg = w.find('fieldset.rail-box .seg')
    expect(seg.exists(), '视图切换没有分段控件的底').toBe(true)
    expect(seg.findAll('[data-view]').map((b) => b.attributes('data-view')))
      .toEqual(['section', 'volume'])
  })

  it('本帧时刻走 `fmtTime`，不把 ISO 的 T 印给人看（终审 I-3）', async () => {
    // 与页③ 同款：`format.ts` 立的是「同一个数在四页上是同一种写法」，
    // 这一屏原来有两处直接铺载荷（指标卡与「第 n 帧」下面那一行数字）。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    // 帧载荷要等源准备好才取 —— 先点「准备」，第四格才有时刻可谈。
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(w.text(), '屏上还印着带 T 的时间戳').not.toContain('2026-07-27T')

    const card = w.findAll('.stat')[3]
    expect(card.find('.label').text()).toBe('本帧时刻')
    expect(card.find('.value').text()).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })
})

describe('实时模式与模型库', () => {
  beforeEach(() => { installEnvironment(); vi.restoreAllMocks(); calls.length = 0 })

  /** 「一条能用的都没有」：把每一行都标成对不上。 */
  function noneUsable() {
    const p = makeModelsPayload()
    p.rows = p.rows.map((r) => ({ ...r, compatible: false,
                                  why: '数据来源不同：别人家的棚.xlsx' }))
    p.current_id = null
    return p
  }

  it('没有可用模型时不画帧，也不给启动按钮', async () => {
    // 实时源本来就需要一条 fit 好的管线 —— 没有模型时它开不了。
    // ⚠️ 与页③ 同一套空态文案：两页对同一件事说同一句话
    // （`copy.ts` 里 `FIELD_MODEL` 的注释写的理由）。
    stubFetch(makeLiveFramePayload(), noneUsable())
    const w = mountLive()
    await flushPromises()

    expect(w.text()).toContain(FIELD_MODEL.none)
    expect(w.text()).toContain(FIELD_MODEL.toLibrary)
    expect(w.text()).toContain(FIELD_MODEL.toTrain)
    // ⚠️ 断的是 `.chart-stub`，不是 `canvas`：这个文件里 `EChart` 是替身
    // （`<div class="chart-stub" />`），jsdom 里本来就没有 canvas ——
    // `findAll('canvas')` 是一条**永远绿**的断言，删掉整块面板它也绿。
    expect(w.findAll('.chart-stub'), '没有可用模型却画了帧').toHaveLength(0)
    // 入口动作也没了：一个按不动的「准备」比没有更坏
    expect(w.find('button[data-act="prepare"]').exists()).toBe(false)
  })

  it('没有可用模型时一次 /api/live/ 都不打', async () => {
    // ⭐ 这条比上一条更硬：上面拦的是「画了」，这条拦的是「问了」。
    // 实时那一屏的每一条 GET 都会让服务端去碰管线；没模型时问它，
    // 轻则白算一帧，重则抛错并在屏上留一句用户看不懂的话。
    stubFetch(makeLiveFramePayload(), noneUsable())
    // ⚠️ 这一条**不接返回值**：它断的是「问了没有」，不是「画了什么」——
    // 挂一个没人读的 `w` 过不了 `vue-tsc -b`（`noUnusedLocals`），
    // 而报错离「这个变量没人用」很远。挂载本身仍然必要：那一句
    // 「不要问」写在挂载钩子里。
    mountLive()
    await flushPromises()
    expect(calls.filter((c) => c.includes('/api/live/')),
      '没有可用模型却去问了实时接口').toEqual([])
  })

  it('有可用模型时照常渲染帧（空态那两条的反面）', async () => {
    // 少了这条，一个「永远走空态」的实现照样全绿 —— 而那是这条规则
    // 最坏的坏法：页⑤ 从此什么都放不出来，还不报错。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    expect(w.text()).not.toContain(FIELD_MODEL.none)
    expect(w.text()).toContain('共 144 帧')
    expect(w.find('button[data-act="prepare"]').exists()).toBe(true)
    expect(calls.some((c) => c === 'GET /api/live/status')).toBe(true)
  })

  it('模型库取数还没回来时既不画帧也不报空态', async () => {
    // 取数回来的那一瞬间之前，`/api/models` 还没到 —— 这时候报「还没有
    // 可用的模型」是把「还不知道」说成「没有」。与后端那句规矩同一条
    // （连不上必须说连不上，不许说成空库）的界面版本。
    stubFetch()
    const w = mountLive()          // 故意不 flushPromises
    expect(w.text()).not.toContain(FIELD_MODEL.none)
    expect(w.find('button[data-act="prepare"]').exists()).toBe(false)
    await flushPromises()
    expect(w.find('button[data-act="prepare"]').exists()).toBe(true)
  })

  it('模型库连不上时报的是连不上，不说成「还没有可用的模型」', async () => {
    // ⭐ Review Focus 第 1 条。后端在 MySQL 不通时回 500 + 原话
    // （`models.py` 那一支），前端**不许**把它折叠成空库 ——
    // 空库是一个用户能「解决」的状态（去训一个），连不上不是。
    // 说成空库，用户会去训一个模型，然后保存的时候再撞一次同样的 500。
    stubFetch(makeLiveFramePayload(), { detail: '数据库连不上' }, 500)
    const w = mountLive()
    await flushPromises()
    expect(w.text()).not.toContain(FIELD_MODEL.none)
    expect(w.text()).toContain('数据库连不上')
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.find('button[data-act="prepare"]').exists()).toBe(false)
  })
})
