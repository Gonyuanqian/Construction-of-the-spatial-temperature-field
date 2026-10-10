/**
 * 每个已注册的路由都点得进去，且不抛异常。
 *
 * SPA 的路由只有真的走一遍才知道崩没崩 —— 这正是 spec §〇 里说的
 * 「框架限制消失之后要自己补回来的东西」（Streamlit 是多页重跑，
 * 一页崩了其它页不受影响；SPA 不是）。
 *
 * 这一条覆盖的是「挂载期与首次取数期」的崩溃。真浏览器的渲染
 * （canvas、CSS 布局）不在这里 —— 见计划里的 Ruling。
 *
 * 另有一条**被禁字形**的扫描（裁定 R9）：把标题、导航、两页一起渲染出来，
 * 扫渲染后的文本。但它扫到的是**渲染结果与 mock 载荷** —— mock 里
 * `checks: []`、`checks_note: ''`、`notes: []`，所以页① 与 features 由
 * **真实后端**产出的文案不经过这里。
 *
 * 分工（谁守哪一份，别让两边都以为对方在守）：
 * - **前端守这条**：标题、导航、以及页面从 mock 载荷渲染出来的文本；
 * - **后端守真实文案**：`backend/tests/test_on_screen_copy.py` 扫
 *   `/api/dataset`、`/api/dataset/timeseries`、`/api/dataset/layer-timeheight`、
 *   `/api/features` 的**真实响应体**；`test_api_train.py` 扫标定包那一份。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import App from './App.vue'
import { createAppRouter } from './router'
import { MODELS, NAV_ITEMS } from './design/copy'
import { matchPayload } from './test/fixtures'

/**
 * 挂到 `document.body` 上、每条用例后自动卸载。
 *
 * **为什么必须挂上去**：页③ 用 `<Teleport to="#rail-extra">` 把左栏控件投进
 * NavRail 的落点，而字符串选择器的落点是**在 `document` 上**用 `querySelector`
 * 找的 —— 落点必须真的在文档里才找得到。VTU 的 `mount` 默认把容器建在**游离**的
 * div 里（源码里 `attachTo` 是可选分支，不给就 `app.mount(el)` 到一个没进文档的
 * el）。脱离文档挂载时 `#rail-extra` 找不着，Teleport 子树一个都不挂载（每个
 * vnode 的 `el` 都是 null），下一次取数回来的重渲染就对着这批从未挂载的旧 vnode
 * 调 `patchElement` → `Cannot set properties of null (setting '__vnode')`。
 *
 * 真实浏览器里应用挂在 `#app` 上，落点找得到，所以**测试也必须挂上去**，
 * 走浏览器那条路 —— 而不是把 Teleport stub 掉（那等于把这条覆盖又蒙上）。
 * （落点**在挂载期**还进没进文档，是另一半问题，由 FieldView 的 `defer` 解决；
 * 两者缺一不可，见 FieldView.vue 的注释。）
 */
enableAutoUnmount(afterEach)

// EChart 在 jsdom 里没有 canvas，这里换掉它 —— 冒烟测的是路由，不是画图。
// `vi.mock` 会被提升到文件顶端，放这里与放 beforeEach 里等价；写在模块作用域
// 是让「它管整个文件」这件事一眼可见。
vi.mock('./charts/EChart.vue', () => ({
  default: { name: 'EChart', props: ['option'], template: '<div />' },
}))

/**
 * jsdom 不加载 tokens.css，而两页都要 `readPalette()`；读不到它就**抛错**
 * （这是故意的：宁可不画，也不用个错的灰）。所以挂载页面的测试必须先把令牌
 * 装进 `document.documentElement` 的内联样式里 —— 与 `App.test.ts` 的
 * `installTokens()`、`DataView.test.ts` 的 `installEnvironment()` 同一手法。
 */
function installTokens(): void {
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
}

/** spec §8.5 禁的连接符与会漏成字面字符的 markdown 标记。 */
const BANNED = ['——', '**', '`', ' · ', '→', '↳'] as const

function assertCleanText(text: string, where: string): void {
  for (const bad of BANNED) {
    expect(text, `${where} 的渲染文本里出现了被禁的 ${JSON.stringify(bad)}`)
      .not.toContain(bad)
  }
}

describe('路由冒烟', () => {
  beforeEach(() => {
    installTokens()
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const hit = matchPayload(String(url))
      return new Response(JSON.stringify(hit ?? {}), {
        status: hit === undefined ? 404 : 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))
  })

  for (const item of NAV_ITEMS.filter((i) => i.enabled)) {
    it(`${item.to} 点得进去，并且在页面上看得见它的标题`, async () => {
      const router = createAppRouter(createMemoryHistory())
      await router.push(item.to)
      await router.isReady()
      const w = mount(App, { attachTo: document.body, global: { plugins: [router] } })
      await flushPromises()
      expect(router.currentRoute.value.path).toBe(item.to)
      expect(w.text()).toContain(item.label)
      // R9：整页渲染出来的文本必须干净 —— 两页 × 后端文案合起来扫一次。
      assertCleanText(w.text(), item.to)
    })
  }

  it('未开启的页没有路由，直接敲地址会落回页①', async () => {
    const router = createAppRouter(createMemoryHistory())
    for (const item of NAV_ITEMS.filter((i) => !i.enabled)) {
      await router.push(item.to)
      await router.isReady()
      expect(router.currentRoute.value.path).toBe('/data')
    }
  })

  it('实时模式那一屏没有禁用字形', async () => {
    // `/live` 不在 NAV_ITEMS 里（实时模式要收起导航），所以上面那个逐页循环扫不到它。
    // 这条**一写出来就是绿的** —— 它钉的是已经写好的文案，不是新行为。
    // 它的价值是回归覆盖：实时页那几十个字从此也过 `assertCleanText`，
    // 以后谁往里加一个 `→` 就会被拦下。
    //
    // 但它够不着什么，说清楚：渲染用的是**替身载荷**，所以后端那几条接口
    // （`/api/live/frame/{n}` 的 `note`、`/api/live/volume/{n}` 的 `note`）
    // 的**真实**文案不经过这里 —— 与上面逐页循环同一个缺口。
    const router = createAppRouter(createMemoryHistory())
    await router.push('/live')
    await router.isReady()
    const w = mount(App, { attachTo: document.body, global: { plugins: [router] } })
    installTokens()
    await flushPromises()

    expect(w.text()).toContain('实时模式')

    // ⚠️ 2026-10-09：这一屏的两块**互斥**，一次渲染只看得到一块（用户裁定
    // 「断面与三维共用一个位子」），而默认落的是**三维**。所以两块各扫一次 ——
    // 只扫默认那一块的话，断面那几十个字（气象、24 路读数、分级）就掉出
    // `assertCleanText` 的射程了，而它们原先正是在这里的。
    assertCleanText(w.text(), '/live（三维）')

    // 帧那一块确实渲染出来了（不然这不是一次扫描，只是扫了一句标题）。
    // 由用户走一遍那条路切过去 —— 与真人一样点那个按钮，而不是把默认值
    // 改回去（默认三维是裁定，不是测试的活）。
    await w.get('button[data-view="section"]').trigger('click')
    await flushPromises()
    expect(w.text(), '切到断面后帧那一块还是没渲染出来').toContain('棚顶气象')
    assertCleanText(w.text(), '/live（断面）')
  })

  it('模型库列表点得进去', async () => {
    // `/models` 不在 `NAV_ITEMS` 里（它是标题条上的图标），所以上面那个
    // 逐页循环扫不到它。与 `/live` 那一条同一个理由，也同一个缺口：
    // 渲染用的是**替身载荷**，后端真实文案不经过这里。
    const router = createAppRouter(createMemoryHistory())
    await router.push('/models')
    await router.isReady()
    const w = mount(App, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    expect(w.text()).toContain(MODELS.title)
    assertCleanText(w.text(), '/models')
  })

  it('模型库详情点得进去', async () => {
    // 与上一条同一个缺口：渲染用的是**替身载荷**，后端真实文案不经过这里。
    //
    // ⚠️ 这一条是**从 Task 6 挪过来的**：计划把它写在入口图标那一步，而那时
    // `ModelsView.vue` 还只有一句标题（Task 6 自己说「先建一个只有标题的最小
    // 版本」），断言的内容要等信息态建好才存在 —— 写在那里是一条永远红的用例。
    const router = createAppRouter(createMemoryHistory())
    await router.push('/models/1')
    await router.isReady()
    const w = mount(App, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    expect(w.text()).toContain('七月下旬那套')
    assertCleanText(w.text(), '/models/1')
  })
})
