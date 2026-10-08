import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import App from './App.vue'
import { createAppRouter } from './router'
import { NAV_ITEMS, SYSTEM_TITLE } from './design/copy'
import { useDataset } from './composables/useDataset'
import { matchPayload, PAGE_PAYLOADS } from './test/fixtures'

/**
 * 这一组测的是外壳，但它经 RouterView 把页①（DataView）也挂了起来，
 * 而页① 现在要用调色板（Ruling P5）：jsdom 不加载 tokens.css，`readPalette()`
 * 读不到就抛。所以外壳测试也得先把令牌装上。
 *
 * ⚠️ **EChart 要换掉**（与 `routes.smoke.test.ts` 同一手法）。原来这一组不需要它
 * —— 页① 的数据接口回 404，两张图都是 null，图表压根不挂。`数据集闸门`那一段
 * 起不了这个作用：它喂的是真形状载荷，两张图会真的去 mount，而 jsdom 没有
 * canvas，zrender 会抛 `Cannot read properties of null (reading 'clearRect')`。
 * 那一抛还是**未捕获异常** —— 会把跑在它前后的用例一起带红，
 * 报错位置与真正的原因隔得很远。`vi.mock` 会被提升到文件顶端，
 * 所以它对整个文件生效；这与外壳测试要测的东西无关。
 */
vi.mock('./charts/EChart.vue', () => ({
  default: { name: 'EChart', props: ['option'], template: '<div />' },
}))
function installTokens() {
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

function stubFetch() {
  // 按路径回答：/api/health 给侧栏用；其余接口回 404，让页① 走错误分支。
  // 外壳测试不关心页① 的内容，但页① 也不该因为拿到一个健康载荷而崩。
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('/api/health')) {
      return new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }
    return new Response('{"detail":"外壳测试不打这个接口"}', { status: 404 })
  }))
}

async function mountApp() {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  return mount(App, { global: { plugins: [router] } })
}

describe('应用外壳', () => {
  beforeEach(() => {
    installTokens()
    vi.restoreAllMocks()
  })

  it('标题常驻，且用的是 copy.ts 那一个名字', async () => {
    stubFetch()
    const w = await mountApp()
    expect(w.get('header').text()).toContain(SYSTEM_TITLE)
  })

  it('导航四项齐全，次序就是流水线的次序', async () => {
    stubFetch()
    const w = await mountApp()
    const rail = w.get('nav[aria-label="页面"]')
    for (const item of NAV_ITEMS) expect(rail.text()).toContain(item.label)
  })

  it('未开放的项是禁用的按钮，不是链接', async () => {
    stubFetch()
    const w = await mountApp()
    const rail = w.get('nav[aria-label="页面"]')
    const links = rail.findAll('a').map((a) => a.text())
    // 按 NAV_ITEMS 推导，不写死清单：写死的清单会在**页面开放的当天过期**，
    // 而"打开一个页面"恰恰就是本任务在做的事。同一个文件第 71 行就是这么写的。
    expect(links).toEqual(NAV_ITEMS.filter((i) => i.enabled).map((i) => i.label))
    // ⚠️ `/models` 不在 `NAV_ITEMS` 里，所以它不参与上面这条对账，
    // 到了那一页左栏也不高亮任何一项 —— 那是**有意的**（规格书 D8）。
    for (const item of NAV_ITEMS.filter((i) => !i.enabled)) {
      expect(rail.text()).toContain(item.why)   // 理由看得见，不藏在 title 里
    }
  })

  it('侧栏报出后端版本 —— 一台机器上可能跑着两个后端', async () => {
    stubFetch()
    const w = await mountApp()
    await flushPromises()
    expect(w.text()).toContain('0.1.0')
  })

  it('实时模式开关点得动，切过去到 /live，导航收起', async () => {
    stubFetch()
    const w = await mountApp()
    const modes = w.get('nav[aria-label="模式"]')
    const live = modes.findAll('button').find((b) => b.text().includes('实时模式'))
    expect(live).toBeTruthy()
    expect(live!.attributes('disabled')).toBeUndefined()

    await live!.trigger('click')
    // **不能用 `flushPromises()` 等这一跳**：`/live` 是懒加载的（`router/index.ts`），
    // 那一块 chunk 在**宏任务**边界才解析完 —— 实测点完两次 `flushPromises()` 之后
    // `currentRoute` 还是 `/data`，`setTimeout(20)` 之后才是 `/live`。
    // 轮询等待，断言的东西没变：点完就切过去了。超时上限是 `vi.waitFor` 的默认 1s。
    await vi.waitFor(() => {
      expect((w.vm as unknown as { $route: { path: string } }).$route.path).toBe('/live')
    })

    // 导航收起了 —— 导航是这一屏唯一「不提数据」的控件，留着它就是噪声。
    // `mountApp()` 把 router 包在 `global.plugins` 里、**没有把它交出来**
    // （同文件好几条用例都用着这个 helper，不动它的签名），所以上面那句从组件
    // 实例上读它挂着的那个 `$route`。
    expect(w.find('nav[aria-label="页面"]').exists()).toBe(false)
  })
})


describe('数据集闸门与重挂载', () => {
  // 外壳要挂到 document.body 上：页③ 有一个 `<Teleport to="#rail-extra">` 落点，
  // 而字符串选择器的落点是在 **document** 上用 `querySelector` 找的 ——
  // 游离挂载时找不到落点，Teleport 子树一个都不挂载，下一次重渲染就对着
  // 从未挂载的旧 vnode 调 `patchElement` → 崩。与 routes.smoke.test.ts 同一个理由。
  enableAutoUnmount(afterEach)

  const JSON_HEAD = { 'Content-Type': 'application/json' }

  /** 一份导入摘要。文件名与 `PAGE_PAYLOADS['/api/dataset']` 里那份**故意不同**。 */
  const IMPORTED = {
    signature: '新', file: '人参棚 副本.xlsx', n_times: 1308, n_columns: 52,
    time_start: '2026-07-23T11:00:00', time_end: '2026-07-27T23:55:00',
  }

  /**
   * 一个记请求的替身：`calls` 里是每一条请求的 URL。
   *
   * ⚠️ **除 `/api/dataset` 之外一律喂真形状**（`PAGE_PAYLOADS`），不是 `{}`。
   * 因为闸门在 `probing` 那一瞬是**开着的**（见 App.vue 的注释）—— 页面会先
   * 真的挂一次并取数。喂 `{}` 的话，`features.default_groups.join()` 这类
   * 取值会当场抛，而报错看起来像「闸门写错了」。
   */
  function stubCounting(datasetStatus: number) {
    const calls: string[] = []
    // 只认**整条** `/api/dataset`：它是 `/api/dataset/timeseries` 的前缀，
    // 用 includes 会把那两张图的取数一起打成 409。
    const isProbe = (u: string) => /\/api\/dataset$/.test(u)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const s = String(url)
      calls.push(s)
      if (isProbe(s)) {
        return new Response(
          JSON.stringify(datasetStatus === 200
            ? PAGE_PAYLOADS['/api/dataset']
            : { detail: '还没有导入数据集。' }),
          { status: datasetStatus, headers: JSON_HEAD })
      }
      const hit = matchPayload(s)
      return new Response(JSON.stringify(hit ?? {}), {
        status: hit === undefined ? 404 : 200, headers: JSON_HEAD })
    }))
    return calls
  }

  async function mountAt(path: string) {
    const router = createAppRouter(createMemoryHistory())
    await router.push(path)
    await router.isReady()
    const w = mount(App, { attachTo: document.body, global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  beforeEach(() => {
    installTokens()
    vi.restoreAllMocks()
    useDataset().reset()
  })

  for (const path of ['/train', '/field', '/live']) {
    it(`空态下 ${path} 说的是「先导入数据集」`, async () => {
      stubCounting(409)
      const w = await mountAt(path)
      expect(w.text()).toContain('先导入数据集')
    })
  }

  it('空态下页① 照常渲染它自己的内容（那一页就是入口）', async () => {
    stubCounting(409)
    const w = await mountAt('/data')
    // 页① 是**唯一**不挂空态闸门的一页：它就是导入的入口，
    // 把它也换成「先导入数据集」等于把用户关在门外。
    expect(w.text()).not.toContain('先导入数据集')
    expect(w.text()).toContain('数据导入与检查')
  })

  it('后端挂了不显示空态 —— 那不是「你还没开始」', async () => {
    stubCounting(500)
    const w = await mountAt('/train')
    expect(w.text()).not.toContain('先导入数据集')
  })

  it('导入之后，当前挂着的那一页当场重取一遍', async () => {
    // T11：防「key 没接上，或者接在了别处」。
    //
    // ⚠️ 这一条用 **200**，不用 409。计划原文写的是 409 —— 那样闸门是开着的，
    // 页② 压根没挂上（渲染的是 NoDataset），`before` 会是 0，这条测试**自己
    // 那条「守不住任何东西」的断言**就会先炸。200 才是「页② 真挂在那儿」的前提。
    const calls = stubCounting(200)
    await mountAt('/train')
    const before = calls.filter((u) => u.includes('/api/features')).length
    expect(before, '页② 一开始就没取数，这条测试守不住任何东西').toBeGreaterThan(0)

    useDataset().onImported(IMPORTED)
    await flushPromises()
    await flushPromises()

    const after = calls.filter((u) => u.includes('/api/features')).length
    expect(after, '导入之后页② 没有被重新挂载').toBeGreaterThan(before)
  })

  it('重挂载之后，页① 那一行「当前数据集」还在', async () => {
    // ⚠️ 这一条**只有在这里测得出来**。`DataView.test.ts` 直接 mount 页①，
    // 没有 `RouterView`、没有 `:key`，那个实例根本不会被卸掉 —— 于是
    // 「摘要是组件里的 ref」这个写法在那里是**全绿**的，而在真机上那一行
    // 会在写上去的同一瞬间被自己的重挂载抹掉。
    //
    // 文件名故意与 `/api/dataset` 载荷里的那份不同（载荷里是下划线那份）：
    // 找得到它，就证明它来自导入摘要，而不是取数回来的载荷。
    stubCounting(200)
    const w = await mountAt('/data')
    useDataset().onImported(IMPORTED)
    await flushPromises()
    await flushPromises()

    expect(w.text()).toContain('人参棚 副本.xlsx')
    expect(w.text()).toContain('1308 个时刻')
  })
})
