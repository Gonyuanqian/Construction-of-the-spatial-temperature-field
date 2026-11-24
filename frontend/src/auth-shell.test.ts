import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import App from './App.vue'
import { createAppRouter } from './router'
import { clearSession } from './api/session'
import { loginAs } from './test/authFixture'

// jsdom 不加载全局样式；空态大屏仍会读取图表调色板。
vi.mock('./design/palette', () => ({ readPalette: () => ({
  paper: '#071D38', ink: '#FFFFFF', inkMuted: '#89A9C8', steel: '#223E5E',
  leaf: '#00CFFF', leafSoft: '#102E50', net: '#223E5E', layerTop: '#C44E52',
  layerMid: '#4C72B0', layerLow: '#55A868', bar: '#D98C2B', chartAxis: 12, chartTitle: 14,
}) }))
enableAutoUnmount(afterEach)
beforeEach(() => { clearSession(); vi.restoreAllMocks() })
afterEach(() => { clearSession(); vi.restoreAllMocks(); document.body.innerHTML = '' })
it.each(['USER', 'ADMIN'] as const)('role %s starts in the user workbench without probing the developer dataset', async role => {
  loginAs(role)
  const requests: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => { requests.push(url); return new Response(JSON.stringify(url === '/api/health' ? { status: 'ok', version: 'test' } : url === '/api/user/greenhouses' ? [] : url === '/api/live/status' ? {state:'idle',running:false,cursor:0,total:0,interval_s:300} : {})) }))
  const router = createAppRouter(createMemoryHistory()); await router.push('/live')
  const w = mount(App, { attachTo: document.body, global: { plugins: [router] } }); await flushPromises()
  await vi.waitFor(() => expect(w.text()).toContain('等待构建温度场'))
  expect(w.get('nav[aria-label="页面"]').findAll('a').map(a => a.attributes('href'))).toEqual(['/live','/greenhouse-design','/greenhouse-control','/assistant'])
  expect(w.find('nav[aria-label="模式"]').exists()).toBe(false)
  expect(w.find('a.workspace-entry').exists()).toBe(role === 'ADMIN')
  expect(requests.every(path => ['/api/health', '/api/user/greenhouses','/api/live/status','/api/live/prototype'].includes(path))).toBe(true)
  clearSession('登录已失效，请重新登录。'); await flushPromises()
  await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/login'))
  expect(w.find('nav[aria-label="页面"]').exists()).toBe(false)
})
