import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import App from './App.vue'
import { createAppRouter } from './router'
import { NAV_ITEMS, SYSTEM_TITLE } from './design/copy'

/**
 * 这一组测的是外壳，但它经 RouterView 把页①（DataView）也挂了起来，
 * 而页① 现在要用调色板（Ruling P5）：jsdom 不加载 tokens.css，`readPalette()`
 * 读不到就抛。所以外壳测试也得先把令牌装上。EChart 在这一组里不会挂载
 * （页① 的数据接口回 404，v1/v2 都是 null），故不需要 ResizeObserver 夹具。
 */
function installTokens() {
  const root = document.documentElement
  root.style.setProperty('--paper', '#F7F6F2')
  root.style.setProperty('--ink', '#211F1C')
  root.style.setProperty('--ink-muted', '#5C5850')
  root.style.setProperty('--steel', '#DEDCD6')
  root.style.setProperty('--leaf', '#14532D')
  root.style.setProperty('--leaf-soft', '#E7EFE9')
  root.style.setProperty('--net', '#0B0F0D')
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
