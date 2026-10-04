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
})
