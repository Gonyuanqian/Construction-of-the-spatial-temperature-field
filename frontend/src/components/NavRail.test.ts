import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import NavRail from './NavRail.vue'
import { createAppRouter } from '../router'

/**
 * `#rail-extra` 是页③ 的 `Teleport` 落点。它是一个**空容器** ——
 * 页① ② 上什么都不显示（:empty 时不占高度），页③ 把视图切换与时刻游标投进来。
 *
 * 这条锚点丢了，页③ 的控件会静默地什么都不显示（Vue 的 Teleport 找不到目标
 * 时只会在控制台抱怨一句）—— 页面看起来只是"少了点东西"。
 *
 * 装**真路由**而不是 `stubs: { RouterLink: true }`：VTU 的桩默认**不渲染**
 * 默认插槽（要 `config.global.renderStubDefaultSlot = true` 才渲染），
 * 而四项里前两项是 `<RouterLink>{{ item.label }}</RouterLink>` ——
 * 桩一上，那两个标签就从 `w.text()` 里消失，「导航项仍然全在」会为了
 * 一个跟它无关的理由变红。真路由下 RouterLink 渲染成真的 `<a>`，标签在。
 */
function stubFetch() {
  // 侧栏挂载时会打 /api/health；不打桩的话 jsdom 里会去发一个真的相对地址请求
  // （Node 的 fetch 解析不了相对 URL，于是走错误分支）—— 测试不该出网。
  vi.stubGlobal('fetch', vi.fn(async () => new Response(
    JSON.stringify({ status: 'ok', version: '0.1.0' }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  )))
}

async function mountRail() {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/data')
  await router.isReady()
  return mount(NavRail, { global: { plugins: [router] } })
}

describe('侧栏给页面留的落点', () => {
  beforeEach(() => { vi.restoreAllMocks(); stubFetch() })

  it('有一个 id 为 rail-extra 的容器', async () => {
    const w = await mountRail()
    expect(w.find('#rail-extra').exists()).toBe(true)
  })

  it('它是空的（内容由页面投进来）', async () => {
    const w = await mountRail()
    expect(w.find('#rail-extra').element.childElementCount).toBe(0)
    expect(w.find('#rail-extra').text()).toBe('')
  })

  it('导航项仍然全在', async () => {
    const w = await mountRail()
    for (const label of ['数据导入与检查', '模型训练', '空间温度场的构建', '影响分析']) {
      expect(w.text()).toContain(label)
    }
  })
})
