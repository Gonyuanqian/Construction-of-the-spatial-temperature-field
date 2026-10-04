import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import App from './App.vue'
import { createAppRouter } from './router'
import { MODES, NAV_ITEMS, SYSTEM_TITLE } from './design/copy'

function stubFetch() {
  vi.stubGlobal('fetch', vi.fn(async () =>
    new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))
}

async function mountApp() {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/')
  await router.isReady()
  return mount(App, { global: { plugins: [router] } })
}

describe('应用外壳', () => {
  beforeEach(() => vi.restoreAllMocks())

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

  it('未开放的两项是禁用的按钮，不是链接', async () => {
    stubFetch()
    const w = await mountApp()
    const rail = w.get('nav[aria-label="页面"]')
    const links = rail.findAll('a').map((a) => a.text())
    expect(links).toEqual(['数据导入与检查', '模型训练'])
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

  it('实时模式开关在，但点不动，并说明为什么', async () => {
    stubFetch()
    const w = await mountApp()
    const modes = w.get('nav[aria-label="模式"]')
    const live = modes.findAll('button').find((b) => b.text().includes('实时模式'))
    expect(live).toBeTruthy()
    expect(live!.attributes('disabled')).toBeDefined()
    // 断言对齐 copy.ts 里实时模式那条 why 的真实用词（「重新标定」）。
    const why = MODES.filter((m) => !m.enabled).map((m) => m.why).join('')
    expect(modes.text()).toContain(why)
  })
})
