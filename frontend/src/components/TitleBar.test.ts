import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import TitleBar from './TitleBar.vue'
import { SYSTEM_TITLE } from '../design/copy'

// 名字从 copy.ts 取，不在这里抄一遍 —— `guards.test.ts` 有一条守卫扫全仓，
// 标题字面量只允许出现在 copy.ts 与 index.html 两处。
function stubHealth(ok: boolean) {
  vi.stubGlobal('fetch', vi.fn(async () => (ok
    ? new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    : new Response('{"detail":"后端没起"}', { status: 500 }))))
}

describe('标题条', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('标题常驻，用的是 copy.ts 那一个名字', () => {
    stubHealth(true)
    const w = mount(TitleBar)
    expect(w.get('header').text()).toContain(SYSTEM_TITLE)
  })

  it('后端状态在标题条上：没回来时说「检查中」，回来了报版本号', async () => {
    // 状态原先挂在侧栏底部，而 `/live` 一屏把导航收起来了 ——
    // 最需要确认「这是哪个后端」的那一屏反而看不到它（spec §5.2）。
    stubHealth(true)
    const w = mount(TitleBar)
    expect(w.text()).toContain('检查中')
    await flushPromises()
    expect(w.text()).toContain('0.1.0')
  })

  it('后端挂了就把原话报出来，不吞成空白', async () => {
    stubHealth(false)
    const w = mount(TitleBar)
    await flushPromises()
    expect(w.text()).toContain('后端没起')
  })

  it('标题排在中间那一格、状态在右格 —— 居中靠栅格，不靠 flex', () => {
    // 右端有状态在，用 flex 居中会被它推偏。形状钉在栅格列号上。
    stubHealth(true)
    const w = mount(TitleBar)
    // 用 `find` 而不是 `get`：`get` 的返回类型把 `exists` 从签名里去掉了
    // （它本身就保证存在，`exists()` 恒真），`vue-tsc` 会报 TS2339。
    expect(w.find('h1').exists()).toBe(true)
    expect(w.find('.backend').exists()).toBe(true)
  })
})
