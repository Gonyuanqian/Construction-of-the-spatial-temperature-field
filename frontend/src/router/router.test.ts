import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from './index'
import { NAV_ITEMS } from '../design/copy'

describe('路由', () => {
  it('只有导航里 enabled 的项才注册了路由', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    await router.isReady()
    const paths = router.getRoutes().map((r) => r.path)
    for (const item of NAV_ITEMS) {
      expect(paths.includes(item.to), `${item.label} 的路由状态与 enabled 不一致`)
        .toBe(item.enabled)
    }
  })

  it('/ 落到页①', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/data')
  })

  it('不认识的路径也回到页①，不是白屏', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/并没有这个页面')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/data')
  })

  it('实时模式的路由在，但不进左侧导航', () => {
    const r = createAppRouter(createMemoryHistory())
    const live = r.resolve('/live')
    expect(live.matched.length).toBeGreaterThan(0)
    expect(live.name).toBe('live')
    expect(live.meta.rail).toBe(false)
    // 导航里没有它 —— 有的话切过去会「导航说自己在一个不在导航里的页」。
    // 先摊平成 `readonly string[]`：`NAV_ITEMS` 是 `as const`，`i.to` 是字面量联合类型，
    // 直接 `i.to === '/live'` 会被 `vue-tsc` 判成「恒假的无意比较」而**构建不过**
    // （TS2367）—— 类型本来就写着没有，可这恰恰是这条用例要去断的东西。
    const navPaths: readonly string[] = NAV_ITEMS.map((i) => i.to)
    expect(navPaths.includes('/live')).toBe(false)
  })
})
