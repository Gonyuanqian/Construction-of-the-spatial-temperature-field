/**
 * 实时那一屏：三个控件各打哪个接口、指标行说的是什么、分级句**收在哪儿**。
 *
 * ⚠️ 2026-10-09 第二轮用户裁定（在原先「只留温度场」之后）：按一张深蓝科技风的
 * 仪表盘参考图重做，**风格与内容都借过来**。于是同一天早些时候撤掉的那排指标卡
 * **回来了** —— 但回来的是三张，说的全是温度场的事（棚内均温 / 三维温度场 /
 * 本帧时刻），那张「第几帧、共几帧」仍然一张都没有：「不报帧数」这条裁定没变。
 * 「本帧时刻」也随之从三维影像的角上**挪回指标卡**（用户原话：「本帧时刻挪到指标卡」）。
 *
 * 这一屏的风险比静态图高：静态图可以慢慢看标注，实时是一帧一帧刷过去的，
 * 观众只会记住「它在动」。**分级看不见，就等于把「混合出来的」渲染成
 * 「测出来的」** —— 规格书为这句话点过五次名。用户裁定的处置是把它
 * 从「常驻屏上」改成「折进『口径与出处』」：话一个字不丢，但要自己点开。
 * 再往下删（比如连折叠里那份也删）之前先回到规格书那五处看一眼。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import { createMemoryHistory } from 'vue-router'

import LiveView from './LiveView.vue'
import { createAppRouter } from '../router'
import { BORROWED, FIELD_MODEL } from '../design/copy'
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
                   modelsStatus = 200,
                   // 本卷均温。`null` 是后端的**真状态**（拱内一格都没测到），
                   // 不是错误 —— 2026-10-09 终审 Important 2 的另一半要走到那一支。
                   mean: number | null = 26.5) {
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
    // ⚠️ 体网格的时刻**跟着帧走**：真后端的 `/api/live/volume/{n}` 给的就是
    // 第 n 帧那一刻的场（`makeVolumePayload` 的默认时刻是页③ 那卷的
    // 2026-07-23，直接用它会让替身与真后端不同形 —— 而画面上那枚时刻
    // 读的正是载荷自己的 `time`，替身不同形它就指着另一个时刻）。
    } else if (url.includes('/live/volume')) body = makeVolumePayload({ time: frame.frame.time, mean })
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
  it('屏上**不再报帧数** —— 第几帧、共几帧是后端的事（2026-10-09 用户裁定）', async () => {
    // 用户的原话：「实时模式主要就是为了展示构建的温度场……不需要向下滚动
    // 就能看到全貌，所以把一些不重要东西都删掉……第几帧，一共多少帧这几个
    // 就没必要展示出来，后端系统知道就行」。
    // 那条状态句整句说的都是帧数，跟着指标卡一起走。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    const text = w.text()
    expect(text, '还在报一共多少帧').not.toContain('共 144 帧')
    expect(text, '还在报第几帧').not.toContain('第 0 帧')
    expect(text, '还在报多久一帧').not.toContain('5 分钟一帧')
  })

  it('但那句真话没有丢 —— 「重启就回到第 0 帧」挪进了「口径与出处」', async () => {
    // 删的是**摆法**，不是这句话本身：帧历史在内存里、重启服务就没了，
    // 是用户该知道的口径。收进 `details.why` 里，占不到温度场的地方。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why, '「口径与出处」只有一个').toHaveLength(1)
    expect(why[0].text(), '帧历史那句被删掉了，不是挪走了').toContain('内存')
    expect(why[0].text()).toContain('重启')
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

  it('`prepare` 的回执不是状态 —— 点完它要真的去取那一帧', async () => {
    // 规格书 §五：`POST /api/live/prepare` 回的是 `{state, seconds}`，**不是** LiveStatus。
    // 把回执当状态用，`frame.run()` 会拼出 `/api/live/frame/undefined`
    // （真后端 422，前端再把它显示成 `[object Object]`）—— 这是实时模式
    // **唯一**的入口动作，点下去看到的是一屏错误。
    //
    // ⚠️ 这条原先拿「状态条上有数」当证据（`共 144 帧`）。那条状态句按用户
    // 裁定删了，证据换成**控件换了一屏**：三个播放控件只在 `ready` 时在，
    // 它们出来了就说明 `status` 真的被刷新过，而不是 receipt 冒充的。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    expect(w.find('button[data-act="start"]').exists(), '点完准备，控件没换').toBe(true)
    expect(calls.some((c) => c === 'GET /api/live/frame/0'), '没有去取第 0 帧').toBe(true)
    expect(w.text()).not.toContain('undefined')
    expect(calls.some((c) => c.includes('/live/frame/undefined'))).toBe(false)
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('分级句收进「口径与出处」—— 屏上不留常驻的那一行（2026-10-09 用户裁定）', async () => {
    // 用户把这一行圈出来说「这两句也不要」。
    // ⚠️ 规格书里这一句是**被点过五次名**的：§6.2、§十二.7、页⑤ 规格书
    // §306 / §308 / §415，原话是「实时是一帧一帧刷过去的，观众只会记住
    // 『它在动』；分级看不见，就等于把『混合出来的』渲染成『测出来的』」。
    // 用户是规格书的作者，所以这一条是**有意推翻**——推翻的方式是把它从
    // 「常驻」降成「折起来」：话一个字不丢，但要自己点开。与那句
    // 「帧历史只在内存里」同一个去处（本文件「口径与出处」那一组）。
    //
    // ⚠️ 断的是**结构**（在不在 `details.why` 里），不是 `w.text()` ——
    // `text()` 把折起来的内容一起算进去，`not.toContain('三种回答')` 在这里
    // 是一条**永远绿**的断言，删掉整句也照样过。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    // 分级只在源准备好之后才在（没准备时屏上只有「准备实时源」一件事）。
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    const why = w.find('details.why')
    expect(why.exists(), '「口径与出处」不在').toBe(true)
    const grading = why.find('[data-grading]')
    expect(grading.exists(), '分级句不在「口径与出处」里').toBe(true)
    expect(grading.text()).toMatch(/实测|不报数/)
    // 全屏只有这一处 —— 只在屏上钉「在折叠里」的话，「折起来的留着、
    // 屏上那份也没删」两边都算过。
    expect(w.findAll('[data-grading]'), '屏上还留着一份').toHaveLength(1)
  })

  it('借来的模型：这一帧照画，但口径里逐字印着后端那句「借来的」', async () => {
    // ⭐ 2026-10-10 用户裁定「模型不绑数据集」在页⑤ 上的落点。
    // 用户报的正是这一页：「实时模式用的就是已经训练好的模型来根据新的数据
    // 来构建温度场」—— 实时那一帧**天生**是没见过的数据，拿一份为别的数据
    // 标好的模型来构是它的正常用法，不是错误。改档之前这一屏直接走空态。
    //
    // ⚠️ 印的仍是载荷里那句 `mismatch_note` 本身（后端 `deps._BORROWED_NOTE`
    // 那唯一一句）—— 与页③ 同一句、同一个来源。
    const NOTE = '这一份模型的参数不是用当前这份数据标出来的'
    stubFetch(makeLiveFramePayload({ mismatch_note: NOTE }))
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    // ⚠️ 那一枚图章在**断面**那一档上（三维那一档它无处可挂：三维块是
    // `VolumeView`，它自己那一卷的图章在页④）。默认落的是三维，所以先切过去。
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain(`已标定（${BORROWED}）`)

    const why = w.find('details.why')
    expect(why.exists(), '「口径与出处」不在').toBe(true)
    expect(why.text()).toContain(NOTE)
  })

  it('「看哪一块」那个标签整个撤了 —— 两个按钮自己说得清', async () => {
    // 同日用户裁定。页③ 那条写的是「视图」（两个字），实时这一屏写的却是
    // 一句话，而底下两个按钮本来就写着「断面」「三维」。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(w.text(), '「看哪一块」还挂着').not.toContain('看哪一块')
    // 撤的是那行标签，不是开关本身 —— 反面：把整个 `fieldset` 一起删了也绿。
    const seg = w.find('fieldset.rail-box .seg')
    expect(seg.exists(), '分段控件跟着标签一起没了').toBe(true)
    expect(seg.findAll('button').map((b) => b.text())).toEqual(['断面', '三维'])
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
    // 页⑤ 自己那一份**摘要**取数走同一个端点、粗一档的步长（见 `SUMMARY_Y_STEP`）。
    // 两条都打实时那条口，一条都不许打到页③ 的 `/api/field/volume`。
    expect(
      calls.some((c) => c.startsWith('GET /api/live/volume/0?y_step=3')),
      '摘要那一份没走实时端点',
    ).toBe(true)
    expect(calls.some((c) => c.includes('/api/field/volume'))).toBe(false)
  })

  it('指标行回来了三张，说的全是温度场的事，仍然不报帧数（2026-10-09 用户裁定）', async () => {
    // 用户按参考图把指标卡要了回来，原话是「本帧时刻挪到指标卡」。
    // ⚠️ 但同一天早些时候那条「第几帧、一共多少帧没必要展示」**没被推翻** ——
    // 所以这里断的不只是「有三张」，还有「三张里没有一张说帧数」。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    // 3 张主行 + 3 张「棚顶气象」（气温 / 湿度 / 光照）。
    expect(w.findAll('.stat'), '指标卡不在').toHaveLength(6)
    const text = w.text()
    expect(text).toContain('棚内均温')
    expect(text).toContain('三维温度场')
    expect(text).toContain('本帧时刻')
    // 本帧时刻走 `fmtTime`：同一个数在四页上是同一种写法，不把 ISO 的 T 印给人看。
    expect(text).toContain('2026-07-27 12:00')
    expect(text, '屏上还印着带 T 的时间戳').not.toContain('2026-07-27T')
    // 反面：帧数一张都没有。
    expect(text).not.toContain('共 144 帧')
    expect(text).not.toContain('5 分钟一帧')
    expect(text, '第几帧又回来了').not.toMatch(/第 \d+ 帧/)

    // ⚠️ 只断「这三个标签在」不够：把 `meanText` 改接底栏那个 `bg_temp`（替身里是
    // 28.4），上面每一行照样全绿 —— 标签在，值也「看着像个温度」
    // （2026-10-09 终审 Important 2）。所以这里**读值**：替身里拱内均温 26.5 与
    // 棚顶气温 28.4 是两个不同的数，读 26.5 那句话就再也糊不过去。
    const meanCard = w.findAll('.stat').find((s) => s.text().includes('棚内均温'))
    expect(meanCard, '「棚内均温」那一张不在').toBeTruthy()
    expect(meanCard!.find('.value').text(), '「棚内均温」印的不是本卷均温').toBe('26.5 °C')
  })

  it('这一卷一个可用格子都没测到时，均温那一张说「不报数」，不说 0（终审 Important 2）', async () => {
    // `mean === null` 是后端会真的回的状态（拱内一格都没测到），不是错误。
    // 翻成 `0.0 °C` 会印出一个**看起来完全正常**的读数，而它其实是「没测到」——
    // 这一屏上再没有第二个地方能把它揭穿。
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, null)
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    const card = w.findAll('.stat').find((s) => s.text().includes('棚内均温'))
    expect(card, '「棚内均温」那一张不在').toBeTruthy()
    expect(card!.find('.value').text(), 'null 被翻成了一个数').toBe('不报数')
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

  it('视图切换是一条分段控件，不是一排带圆角边框的按钮（spec §九 / 终审 I-1）', async () => {
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

  it('断面与三维共用一个位子 —— 切过去是**换掉**，不是接在下面', async () => {
    // 2026-10-09 用户裁定。原先这一屏的视图切换只加不换：断面那张卡没有
    // `v-if` 拦着，切到三维就成了「断面卡 + 三维块」上下两条 —— 用户得往下翻
    // 才看得全，而这一屏的版面因此没法按「一屏」来设计。
    // 页③ 那一份一直是对的（`v-if` / `v-else`），只有实时这一屏漏了。
    //
    // 两条断言缺一不可：只钉「切到三维有三维」的话，叠加着也照样绿 ——
    // 而叠加正是要改掉的那件事。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    // ① 默认落在三维：进这一屏先看棚体，不必先点一下。
    expect(
      w.find('button[data-view="volume"]').classes(), '默认没落在三维',
    ).toContain('on')
    // 三维那一块是懒加载的，等它真的上来（`vi.waitFor` 默认 1s 上限）。
    await vi.waitFor(() => expect(w.text()).toContain('棚体三维温度场'))
    // ⚠️ 原先这里断的是「断面图不存在」。现在底栏那条沿棚均温曲线**两档都在**，
    // 所以断的是**数量**：三维这一支只有那一张（1），断面那一支是两张（2）。
    // 断「存在」的话，「两张都挂着」这条错法会绿。
    expect(
      w.findAll('.chart-stub'), '三维这一支里多出来的那张图是谁',
    ).toHaveLength(1)

    // ② 切到断面：三维那一块要**走开**，不是留在下面。
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()
    expect(w.find('button[data-view="section"]').classes()).toContain('on')
    expect(w.findAll('.chart-stub'), '切到断面却没有断面图').toHaveLength(2)
    expect(w.text(), '切到断面了，三维那一块还留在下面').not.toContain('棚体三维温度场')
  })

  it('本帧时刻挪进指标卡，走 `fmtTime`，不在三维的角上了', async () => {
    // 2026-10-09 第二轮用户裁定：「本帧时刻挪到指标卡」。第一轮的处置是
    // 把它印到三维影像的角上（`show-clock`），这一轮挪回来。
    // 「手上这一屏画的是哪一刻」是温度场唯一的元信息，值得一直看得见 ——
    // 而它落在指标行里，断面与三维两档都看得见；角上那份只有三维那一档有。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    expect(w.text(), '屏上还印着带 T 的时间戳').not.toContain('2026-07-27T')
    const stat = w.findAll('.stat').find((s) => s.text().includes('本帧时刻'))
    expect(stat, '「本帧时刻」那一张不在').toBeTruthy()
    expect(stat!.text()).toContain('2026-07-27 12:00')

    // 三维那一块懒加载上来之后，角上那份**不该**再有 —— 同一件事印两处，
    // 迟早有一处是旧的。
    await vi.waitFor(() => expect(w.text()).toContain('棚体三维温度场'))
    expect(w.find('.stage-clock').exists(), '角上那份还留着').toBe(false)
  })

  it('底栏两块是棚顶气象与沿棚均温，两档视图下都在', async () => {
    // 参考图下方的两块。2026-10-09 第二轮之前「棚顶气象」只挂在断面那张卡里，
    // 切到三维就没了 —— 而它是**帧**的属性，与看哪一块无关。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()

    expect(w.text()).toContain('棚顶气象')
    expect(w.text()).toContain('气温')
    expect(w.text()).toContain('沿棚均温')
    // 均温的口径句要在（它是这一屏最容易看错的那个数）。
    // ⚠️ 计划这一行写的是 `toContain('拱内')` —— 那个词只在注释里出现过
    // （`liveMeanCurve.ts`、`types.ts`），模板上一个字都没有，永远绿不了。
    // 改断「都不进平均」：它**只**出现在均温那一句口径里，底栏那条曲线的
    // 口径句没有它 —— 断「拱形以内」的话两句都有，等于没断细。
    expect(w.text()).toContain('都不进平均')

    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()
    expect(w.text(), '切到断面，棚顶气象就没了').toContain('棚顶气象')
    expect(w.text()).toContain('沿棚均温')
  })

  it('画面上方那两行说明不占这一屏的地方（2026-10-09 用户裁定）', async () => {
    // 用户把那两行圈出来说「这一段话也没必要展示了」。和撤指标卡同一条
    // 道理：这一屏只留温度场，画面要顶到上面去。
    // 那两行是 `VolumeView` 给的，而那一块是页③⑤ 共用的 —— 页⑤ 传
    // `:show-notes="false"` 关掉，页③ 原样不动。
    //
    // ⚠️ 反面必须一起钉：只断「那两行不在」的话，把左右两栏整块删掉也绿 ——
    // 而规格书 §5.3 要求的「棚体示意」正是由左栏那个滑块接管的。
    stubFetch()
    const w = mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(w.text()).toContain('棚体三维温度场'))

    expect(w.text(), '壳长那句说明还占着画面的地方')
      .not.toContain('拱壳按拱形截面示意')
    expect(w.text()).not.toContain('测了这么长')
    // 接管它的那一句还在。
    expect(w.text(), '「棚体示意」的警示跟着那两行一起没了')
      .toContain('棚体示意长度')
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

  it('库里**只有一份借来的模型**也照画 —— 用户报的就是这一种', async () => {
    // ⭐⭐ 2026-10-10 用户的原话：「实时模式的空间温度场的构建为什么需要数据集
    // 的指纹，实时模式下的数据原本就是从来没见过的数据，用的就是已经训练好的
    // 模型来根据新的数据来构建温度场」。
    //
    // 他截的那张图就是这一种：库里只有一份**为别的数据标好的**模型。
    // ⚠️ 与上面那条（一条能用的都没有）是一对，不可合并 —— 上面那条只需要
    // 「`compatible` 判得对」，这一条还要求闸门口径对：闸门守的是「有没有一个
    // 模型在算」，不是「数据集对不对得上」。把 `usableModels` 改回两轴都要求，
    // 只有这一条会红。
    const p = makeModelsPayload()
    p.rows = [p.rows[1]]        // 第二行：借来的那一份
    p.current_id = 2
    stubFetch(makeLiveFramePayload(), p)
    const w = mountLive()
    await flushPromises()

    expect(w.text(), '库里有一份能用的模型，这一屏却走了空态').not.toContain(FIELD_MODEL.none)
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(w.findAll('.chart-stub'), '借来的模型下这一屏什么都没画').not.toHaveLength(0)
  })

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
    // 「照常渲染」现在拿什么当证据：状态句没了，`status` 一到（idle）屏上
    // 就该是那句准备前的预告 —— 空态那一支不会有它。
    expect(w.text()).toContain('几十秒')
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
