import { beforeEach as beforeAuthCase } from 'vitest'
import { loginAs } from '../test/authFixture'
beforeAuthCase(() => loginAs())
/**
 * 实时那一屏：三个控件各打哪个接口、气象概览说的是什么、分级句**收在哪儿**。
 *
 * 2026-11-06：顶部改为外部温度、湿度、光照强度与省市地区四项；
 * 使用当前气象帧保存的输入，棚内均温仍在底部环境参数中展示。
 *
 * 这一屏的风险比静态图高：静态图可以慢慢看标注，实时是一帧一帧刷过去的，
 * 观众只会记住「它在动」。**分级看不见，就等于把「混合出来的」渲染成
 * 「测出来的」** —— 规格书为这句话点过五次名。用户裁定的处置是把它
 * 从「常驻屏上」改成「折进『口径与出处』」：话一个字不丢，但要自己点开。
 * 再往下删（比如连折叠里那份也删）之前先回到规格书那五处看一眼。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

import { createMemoryHistory } from 'vue-router'

import LiveView from './LiveView.vue'
import { testArchive } from '../test/archiveFixture'
import { usableModels } from '../api/models'
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

// 一个测试文件只许调一次（调第二次当场抛），且它设的是**整份文件**的钩子 ——
// 与 `App.test.ts` 顶上那一句同一个处置，文件里两个 `describe` 一起用。
enableAutoUnmount(afterEach)

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
                   mean: number | null = 26.5,
                   initialReady = false) {
  // **替身必须与真后端同形，否则它守不住任何东西。** 两处照真契约来：
  //
  // ① `prepare` 的回执**只有** `{state, seconds}`（规格书 §五）—— 回一份完整的
  //    `LiveStatus` 会让「前端把回执当状态用」这个 bug 在这组测试里凭空消失。
  //    这条替身原来就是这么写的，于是那个 bug 一路绿着走到了终审。
  // ② `status` 得**有状态**：prepare 之前 idle、之后 ready，start / pause 改 running。
  //    回一个写死的状态，页面永远走不到第二条分支，控件那一组也白测。
  let prepared = initialReady
  let running = false
  let cursor = 0
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method ?? 'GET'} ${url}`)
    let body: unknown
    let status = 200
    if (url.includes('/api/user/greenhouses')) { body = usableModels(models as ReturnType<typeof makeModelsPayload>).length ? [testArchive] : []; status = modelsStatus }
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
    } else if (url.includes('/live/volume')) body = makeVolumePayload({ time: frame.frame.time, frame: { n: cursor, time: frame.frame.time }, mean })
    else if (url.includes('/live/frame')) body = frame
    else body = makeLiveStatus({ state: prepared ? 'ready' : 'idle', running, cursor })
    return new Response(JSON.stringify(body), {
      status, headers: { 'content-type': 'application/json' },
    })
  }))
}

/**
 * 页⑤ 的右栏投进 `App.vue` 渲染的 `<aside id="shell-side">`，
 * 而这一组用例只挂 `LiveView` —— 那个落点不在文档里。
 *
 * ⚠️ **必须自己造一个。** 字符串选择器的 Teleport 落点是在 `document` 上
 * 用 `querySelector` 找的：找不到时 Vue **静默不挂**（不报错、也不渲染在
 * 别处），于是右栏整块消失，而每一条「它不该在屏上」的断言照样绿。
 * 造在 `document.body` 上、每条用例后拆掉 —— 与 `routes.smoke.test.ts`
 * 挂整个 `App` 走的是同一条路。
 *
 * 空态那一支挂着 `<RouterLink>`，所以每一处挂载都要带路由 ——
 * 不给的话 Vue 按未知标签渲染并打警告，断言照样绿但每次都刷一遍。
 */
async function mountLive() {
  const rail = document.createElement('div')
  rail.id = 'rail-extra'
  document.body.appendChild(rail)
  const side = document.createElement('div')
  side.id = 'shell-side'
  document.body.appendChild(side)
  const liveRouter = createAppRouter(createMemoryHistory())
  await liveRouter.push('/live')
  await liveRouter.isReady()
  return mount(LiveView, {
    attachTo: document.body,
    global: { plugins: [liveRouter] },
  })
}

/** 右栏那一个落点（`mountLive` 造的那个）。 */
const sidePanel = (): HTMLElement => document.getElementById('shell-side')!

afterEach(() => { document.getElementById('shell-side')?.remove(); document.getElementById('rail-extra')?.remove() })

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
    const w = await mountLive()
    await flushPromises()
    const text = w.text()
    expect(text, '还在报一共多少帧').not.toContain('共 144 帧')
    expect(text, '还在报第几帧').not.toContain('第 0 帧')
    expect(text, '还在报多久一帧').not.toContain('5 分钟一帧')
  })

  it('会话恢复口径放在折叠说明中，不占温度场空间', async () => {
    stubFetch()
    const w = await mountLive()
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why, '「口径与出处」只有一个').toHaveLength(1)
    expect(why[0].text()).toContain('上次确认帧')
    expect(why[0].text()).toContain('恢复后保持暂停')
    expect(why[0].text()).toContain('重启')
  })

  it('准备响应丢失后重试复用请求编号', async () => {
    stubFetch()
    const original = globalThis.fetch
    const keys: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith('/live/prepare') && init?.method === 'POST') {
        const headers = init.headers as Record<string, string>
        keys.push(headers['Idempotency-Key'])
        expect(headers['X-TField-Expected-Session']).toBe('none')
        if (keys.length === 1) throw new TypeError('network unavailable')
      }
      return original(input, init)
    }))
    const w = await mountLive()
    await flushPromises()
    await w.get('[data-act="prepare"]').trigger('click')
    await flushPromises()
    await w.get('[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBeTruthy()
    expect(keys[1]).toBe(keys[0])
  })

  it('重启状态提示恢复，并在请求中携带原会话', async () => {
    stubFetch()
    const original = globalThis.fetch
    let restored = false
    const id = 'd700ffa7-78e2-4857-a59b-6afba18b606a'
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/live/status')) return new Response(JSON.stringify(makeLiveStatus({
        state: restored ? 'ready' : 'idle', session_id: id, recovery_required: !restored,
        model_name: '本次固定模型', running: false,
      })))
      if (url.endsWith('/live/prepare')) {
        expect((init?.headers as Record<string, string>)['X-TField-Expected-Session']).toBe(id)
        restored = true
      }
      return original(input, init)
    }))
    const w = await mountLive()
    await flushPromises()
    expect(w.get('[data-act="prepare"]').text()).toBe('恢复实时源')
    await w.get('[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('本次固定模型')
    expect(w.find('[data-act="start"]').exists()).toBe(true)
    expect(calls.some((c) => c.includes('session_id='+id))).toBe(true)
  })

  it('三个控件各打自己那条接口', async () => {
    stubFetch()
    const w = await mountLive()
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
    const w = await mountLive()
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
    const w = await mountLive()
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
    const w = await mountLive()
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
    const w = await mountLive()
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
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    expect(w.text(), '「看哪一块」还挂着').not.toContain('看哪一块')
    // 撤的是那行标签，不是开关本身 —— 反面：把整个 `fieldset` 一起删了也绿。
    const seg = w.find('fieldset.rail-box .seg')
    expect(seg.exists(), '分段控件跟着标签一起没了').toBe(true)
    expect(seg.findAll('button').map((b) => b.text())).toEqual(['断面', '三维'])
  })

  it('暂停时也核对重启，但同一会话同一帧不重复取场', async () => {
    // ⚠️ **两半都要断。** 只断「暂停时没多问一次」的话，把定时器整个删掉也照样
    // 绿 —— 那是一条靠「什么都没发生」通过的测试。所以第二半把「走起来必须问」
    // 也钉上，两半合起来才等于「轮询开关跟着 running 走」。
    //
    // `toFake` 只给定时器：`flushPromises()` 自己也走 `setTimeout(…, 0)`，
    // 把它一起伪掉的话每个 `await flushPromises()` 都会挂死。
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      stubFetch()
      const w = await mountLive()
      await flushPromises()
      await w.get('button[data-act="prepare"]').trigger('click')
      await flushPromises()

      const statusCalls = () => calls.filter((c) => c === 'GET /api/live/status').length

      // 等待懒加载三维模块自己的首次取数，不能把它算成暂停期间的重复取场。
      await vi.waitFor(() => expect(calls).toContain('GET /api/live/volume/0'))
      const paused = statusCalls()
      const fields = calls.filter((c) => c.includes('/api/live/frame/') || c.includes('/api/live/volume/')).length
      await vi.advanceTimersByTimeAsync(15000)     // 三个轮询周期
      expect(statusCalls()).toBe(paused + 3)
      expect(calls.filter((c) => c.includes('/api/live/frame/') || c.includes('/api/live/volume/')).length).toBe(fields)

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
    const w = await mountLive()
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

  it('气象概览横排四项，显示同一帧的外部输入与省市', async () => {
    const base = makeLiveFramePayload()
    stubFetch(makeLiveFramePayload({live: {...base.live,
      weather: {bg_temp: 22.5, bg_rh: 61.5, bg_light: 800},
      location: {province_code: '220000', province_name: '吉林省', city_code: '220600', city_name: '白山市', district_name: '抚松县'},
    }}), makeModelsPayload(), 200, 26.5, true)
    const w = await mountLive()
    await flushPromises()
    expect(w.findAll('.strip .label').map(cell => cell.text()))
      .toEqual(['外部温度', '相对湿度', '光照强度'])
    expect(w.findAll('.strip .value').map(cell => cell.text()))
      .toEqual(['22.5 °C', '61.5 %', '800'])
    expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
    expect(w.get('.strip').text()).not.toContain('抚松县')
    expect(w.get('.strip').text()).not.toContain('26.5')
  })

  it('底部棚内均温缺失时说不报数，不说零', async () => {
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, null, true)
    const w = await mountLive()
    await flushPromises()
    expect(w.get('.env-card').text()).toContain('不报数')
    expect(w.get('.env-card').text()).not.toContain('0.0 °C')
  })

  it('散文折进唯一一处「口径与出处」', async () => {
    stubFetch()
    const w = await mountLive()
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why.length).toBe(1)
    expect(why[0].find('summary').text()).toContain('口径与出处')
    // 折进去的东西还在 DOM 里（收起来不等于删掉 —— spec §八 选它不选弹层的理由）
    expect(why[0].text().length).toBeGreaterThan('口径与出处'.length)
  })

  it('实时监测顶部不再提供断面与三维切换', async () => {
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, 26.5, true)
    const w=await mountLive(); await flushPromises()
    expect(w.findAll('[data-view]')).toHaveLength(0)
    expect(w.find('.section-stage').exists()).toBe(false)
    expect(w.find('.stage').exists()).toBe(true)
  })

  it('去掉顶部重复标题后保留原三维区域', async () => {
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, 26.5, true)
    const w=await mountLive(); await flushPromises()
    expect(w.find('h2').exists()).toBe(false)
    expect(w.find('.empty-status').exists()).toBe(false)
    expect(w.find('.weather-overview').exists()).toBe(true)
    expect(w.findAll('.stage')).toHaveLength(1)
  })

  it('气象概览不再占用一格展示更新时间', async () => {
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, 26.5, true)
    const w = await mountLive()
    await flushPromises()
    expect(w.get('.strip').text()).not.toContain('更新时间')
    expect(w.get('.strip').text()).not.toContain('2026-07-27')
  })

  it('底栏展示环境监测预警与温度分布概览', async () => {
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, 26.5, true)
    const w = await mountLive()
    await flushPromises()
    const environment = w.get('.env-card')
    expect(environment.text()).toContain('环境监测预警')
    expect(environment.text()).toContain('温度预警')
    expect(environment.text()).toContain('湿度预警')
    expect(environment.text()).toContain('棚内平均温度')
    expect(environment.text()).not.toContain('拱跨宽')
    expect(environment.text()).not.toContain('拱顶高')
    expect(w.get('.temperature-overview').text()).toContain('温度分布概览')
    expect(document.body.textContent).toContain('都不进平均')
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
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    // ⚠️ 等的是右栏那一块**自己**（那两行说明撤掉之后，接管它们的就是右栏
    // 那张卡）。等「棚体三维温度场」那个串的话，2026-10-12 起概览第一格也叫
    // 这个名字，条件一进页面就成立，下面的断言会跑在三维还没上来的时候。
    await vi.waitFor(() => expect(sidePanel().textContent).toContain('棚体示意长度'))

    expect(w.text(), '壳长那句说明还占着画面的地方')
      .not.toContain('拱壳按拱形截面示意')
    expect(w.text()).not.toContain('测了这么长')
    // 接管它的那一句还在**右栏**里（左栏那一块 2026-10-12 搬进外壳了）。
    expect(sidePanel().textContent, '「棚体示意」的警示跟着那两行一起没了')
      .toContain('棚体示意长度')
  })

  it('右栏三张卡在三维那一档上齐了，且问数在最上面', async () => {
    // 规格书 §三 D8 那张表：问数（两档）/ 几何与剖切（只三维）/ 视图控制（只三维）。
    stubFetch()
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await vi.waitFor(() => expect(sidePanel().textContent).toContain('棚体示意长度'))

    const side = sidePanel()
    expect(side.textContent, '右栏里没有坐标查询').toContain('查一个坐标')
    expect(side.textContent).toContain('棚体示意长度')
    expect(side.textContent).toContain('三维视图控制')
    // ⚠️ 次序也钉上：问数在最上面（参考图那张表的次序）。
    const cards = Array.from(side.children) as HTMLElement[]
    expect(cards[0]!.textContent, '问数那一张不在最上面').toContain('查一个坐标')
    // 九枚视角按钮在右栏里，不在画布角上 —— 同一组按钮换了摆法。
    expect(side.querySelectorAll('[data-view-act]')).toHaveLength(9)
    // ⚠️ 反面：画布上那层叠层不该同时还在（同一组按钮印两处）。
    expect(w.find('.scene-wrap .view-ctl').exists(), '画布角上那份还留着').toBe(false)
  })

  it('断面那一档上右栏只剩问数那一张', async () => {
    // 几何与剖切、视图控制服务的是三维，断面档上没有它们的事（规格书 D8）。
    stubFetch()
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()

    const side = sidePanel()
    expect(side.textContent, '断面档的右栏里没有坐标查询').toContain('查一个坐标')
    expect(side.textContent, '几何那一块跟着断面来了').not.toContain('棚体示意长度')
    expect(side.textContent, '视图控制跟着断面来了').not.toContain('三维视图控制')
  })

  it('断面档的坐标查询走同一套判定，并把吸附后的坐标写出来', async () => {
    // ⚠️「做真的，只在右栏报数」（用户裁定）。吸附走 `snapIndex`、
    // 回答走 `interpretPick` / `pickText` —— 三条都是全前端唯一那处。
    // 这一条断的是「真的答了、且答的是**吸附后**的坐标」。
    //
    // 输进去的三个数**一个都不是格点上的数**，这一条才挡得住东西：
    //   x 0.8 → 最近格点 0.70（不是第 0 个 0.00）
    //   y 8.6 → 最近的棚位 p2（不是第 0 个 p1）
    //   z 0.8 → 最近格点 0.70
    // 若 y 被吞掉（写死 sheds[0]），断到的会是 p1；若吸附退化成取首格，
    // x 会写成 0.00 —— 两种错法各有一个断言接着。
    // ⚠️ 答案的形状是「棚位名 + 吸附后的 x、z」，与「点一个格子」之后那份
    // 读数（`readout`）**一模一样**：这一档里 y 的名字就是 p1/p2/p3。
    stubFetch()
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()

    const side = sidePanel()
    const inputs = side.querySelectorAll('input[type="number"]')
    expect(inputs, '断面档右栏里没有三个坐标框').toHaveLength(3)
    // 用 VTU 的 setValue 走真事件，别直接改 DOM 的 value。
    const ask = w.findAllComponents({ name: 'SectionAsk' })[0]!
    await ask.findAll('input')[0]!.setValue('0.8')
    await ask.findAll('input')[1]!.setValue('8.6')
    await ask.findAll('input')[2]!.setValue('0.8')
    await ask.get('button').trigger('click')
    await flushPromises()

    expect(side.textContent, '问了却没答').toContain('现场重算')
    expect(side.textContent, 'y = 8.6 没吸附到最近那个棚位 p2').toContain('p2')
    expect(side.textContent, 'x = 0.8 没吸附到 0.70').toContain('x 0.70 m')
    expect(side.textContent, 'z = 0.8 没吸附到 0.70').toContain('z 0.70 m')
    expect(side.textContent, '坐标超范围时该说的是那句话').not.toContain('超出这一帧的范围')
  })

  it('超出范围的坐标不吸附，直接把话说清楚', async () => {
    // ⚠️ 绝不从范围外吸进来：吸到最近的边上格点，屏幕上写的还是「最近格点」，
    // 而用户以为自己问的是 100 米处 —— 一个不是他问的答案，看起来却完全正常。
    stubFetch()
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()

    const ask = w.findAllComponents({ name: 'SectionAsk' })[0]!
    await ask.findAll('input')[0]!.setValue('0.7')
    await ask.findAll('input')[1]!.setValue('3')
    await ask.findAll('input')[2]!.setValue('99')
    await ask.get('button').trigger('click')
    await flushPromises()
    expect(sidePanel().textContent).toContain('超出这一帧的范围')
  })

  it('气象概览保持一条长条和四个单元', async () => {
    stubFetch(makeLiveFramePayload(), makeModelsPayload(), 200, 26.5, true)
    const w = await mountLive()
    await flushPromises()
    expect(w.find('.strip').exists()).toBe(true)
    expect(w.findAll('.stat')).toHaveLength(0)
    expect(w.findAll('.strip .cell')).toHaveLength(4)
  })

})

describe('实时模式与模型库', () => {
  beforeEach(() => { installEnvironment(); vi.restoreAllMocks(); calls.length = 0 })
  function noneUsable() {
    const payload = makeModelsPayload()
    payload.rows = payload.rows.map(row => ({...row, compatible: false, why: '数据来源不同：别人家的棚.xlsx'}))
    payload.current_id = null
    return payload
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
    const w = await mountLive()
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
    const w = await mountLive()
    await flushPromises()

    expect(w.text()).toContain('等待构建温度场')
    expect(w.text()).toContain('接入外部气象')
    expect(w.find('a[href="/models"]').exists()).toBe(false)
    expect(w.find('a[href="/train"]').exists()).toBe(false)
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
    await mountLive()
    await flushPromises()
    expect(calls.filter((c) => c.includes('/api/live/frame/') || c.includes('/api/live/volume/')),
      '没有当前气象结果却读取了温度场').toEqual([])
  })

  it('有可用模型时照常渲染帧（空态那两条的反面）', async () => {
    // 少了这条，一个「永远走空态」的实现照样全绿 —— 而那是这条规则
    // 最坏的坏法：页⑤ 从此什么都放不出来，还不报错。
    stubFetch()
    const w = await mountLive()
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
    const w = await mountLive()          // 故意不 flushPromises
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
    const w = await mountLive()
    await flushPromises()
    expect(w.text()).not.toContain(FIELD_MODEL.none)
    expect(w.text()).toContain('数据库连不上')
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.find('button[data-act="prepare"]').exists()).toBe(false)
  })

  it('成品读不动时，页⑤ 口径里印的是后端那句 artifact_note', async () => {
    const NOTE = '这一条的成品读不动（格式是第 2 版，现在是第 1 版），已退回现训。'
    stubFetch(makeLiveFramePayload({ artifact_note: NOTE }))
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()

    // ⚠️ 与页③ 一样：这一句住在口径那一块里，**不是**常驻在屏上 ——
    //    它是解释，不是读数。
    expect(w.text()).toContain(NOTE)
  })

  it('artifact_note 不改变页⑤ 那个「已标定 / 借来的」图章', async () => {
    const NOTE = '这一条的成品读不动（字节坏了），已退回现训。'
    stubFetch(makeLiveFramePayload({ mismatch_note: '', artifact_note: NOTE }))
    const w = await mountLive()
    await flushPromises()
    await w.get('button[data-act="prepare"]').trigger('click')
    await flushPromises()
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('已标定')
    expect(w.text()).not.toContain(`已标定（${BORROWED}）`)
    expect(w.text()).toContain(NOTE)
  })
})

 it('用户模式回放只读取棚体目录与本账号气象接口',async()=>{
   loginAs('USER'); stubFetch()
   const w=await mountLive(); await flushPromises()
   expect(calls.some(path=>path.includes('/api/user/greenhouses'))).toBe(true)
   expect(calls.some(path=>path.includes('/api/models') || path.includes('/api/dataset'))).toBe(false)
   expect(w.find('a[href="/models"]').exists()).toBe(false)
   expect(w.find('a[href="/train"]').exists()).toBe(false)
 })
