import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from './App.vue'

function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const hit = Object.keys(routes).find((k) => String(url).includes(k))
    if (!hit) return new Response('{}', { status: 404 })
    return new Response(JSON.stringify(routes[hit]), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
}

describe('App', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('标题是「人参棚空间温度场重建系统」', () => {
    stubFetch({})
    expect(mount(App).text()).toContain('人参棚空间温度场重建系统')
  })

  it('把后端报出的数据集形状原样显示出来', async () => {
    stubFetch({
      '/api/health': { status: 'ok' },
      '/api/dataset': { n_times: 1308, n_columns: 52, file: '数据.xlsx' },
    })
    const w = mount(App)
    await flushPromises()
    expect(w.text()).toContain('1308')
    expect(w.text()).toContain('52')
  })
})
