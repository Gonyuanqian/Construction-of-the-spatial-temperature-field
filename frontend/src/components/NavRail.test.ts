import { describe, expect, it, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import NavRail from './NavRail.vue'
import { createAppRouter } from '../router'
import { LIVE_NAV_ITEMS } from '../design/copy'

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

/**
 * 页⑤ 精修（2026-10-16 用户第二部分要求）：实时那一屏的左栏不是卡片列，
 * 是**连续的菜单行**（图标在左、文字在右，选中项左缘一道青条）。
 *
 * ⚠️ 这里断的仍只是**结构**（图标在不在、哪一项是链接、`live` 挂上没有）。
 * 行高、那条青线、悬停过渡都是样式，jsdom 不做样式计算、看不见它们 ——
 * 由 `design/liveShell.test.ts` 那份读源码的守卫钉着。
 */
describe('实时那一屏的左栏（精修）', () => {
  beforeEach(() => { vi.restoreAllMocks(); stubFetch() })

  /** 在 `/live` 上挂一枚「实时那一屏」形态的左栏。 */
  async function mountLiveRail() {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/live')
    await router.isReady()
    return mount(NavRail, {
      props: { items: LIVE_NAV_ITEMS, variant: 'live' as const },
      global: { plugins: [router] },
    })
  }

  it('每一项左边都有一枚图标', async () => {
    const w = await mountLiveRail()
    const icons = w.findAll('.item .ico')
    expect(icons, '四项该有四枚图标').toHaveLength(LIVE_NAV_ITEMS.length)
    // 颜色走 `currentColor`：默认 / 悬停 / 选中三态的亮暗由**文字颜色**带着走。
    for (const el of icons) expect(el.attributes('stroke')).toBe('currentColor')
  })

  it('只有本屏那一项是链接，而且它带着选中态', async () => {
    const w = await mountLiveRail()
    const links = w.findAll('a.item')
    expect(links, '实时那一屏上应当恰好有一项可选').toHaveLength(1)
    expect(links[0]!.attributes('href')).toBe('/live')
    expect(links[0]!.classes(), '本屏那一项没带上选中态').toContain('router-link-active')
  })

  it('`live` 这个类只挂在这一档上', async () => {
    // 卡片那一套挂在 `.rail:not(.live)` 上（2026-10-06 的裁定只对训练侧那四页
    // 继续成立），所以这个类挂错了，训练侧就跟着变成菜单行。
    const live = await mountLiveRail()
    expect(live.get('nav').classes(), '实时那一屏的左栏没挂 live').toContain('live')

    const plain = await mountRail()
    expect(plain.get('nav').classes(), '训练侧的左栏也挂上了 live').not.toContain('live')
  })

  it('训练侧每个导航项都有对应图标', async () => {
    const w = await mountRail()
    expect(w.findAll('.item .ico')).toHaveLength(5)
  })
})
