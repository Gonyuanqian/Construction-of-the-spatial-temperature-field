import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from '../router'
import LoginView from './LoginView.vue'
import { clearSession, session } from '../api/session'
enableAutoUnmount(afterEach)
beforeEach(() => { clearSession(); vi.restoreAllMocks() })
afterEach(() => { clearSession(); vi.restoreAllMocks() })
it('uses the role returned by the backend and rejects a forbidden post-login destination', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ access_token: 'u'.repeat(43), token_type: 'Bearer', expires_at: new Date(Date.now()+60000).toISOString(), user: { id: 'u', username: 'user001', display_name: '用户', role: 'USER', enabled: true } }))))
  const router = createAppRouter(createMemoryHistory()); await router.push('/login?redirect=/admin/users')
  const w = mount(LoginView, { global: { plugins: [router] } })
  await w.get('input[name="username"]').setValue('user001'); await w.get('input[name="password"]').setValue('test-password')
  expect(w.find('select').exists()).toBe(false)
  await w.get('form').trigger('submit'); await flushPromises()
  await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/live'))
  expect(session.user.value?.role).toBe('USER')
  expect((w.get('input[name="password"]').element as HTMLInputElement).value).toBe('')
})
it('displays wrong-password feedback without entering the workspace', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"账号或密码不正确。"}', { status: 401 })))
  const router = createAppRouter(createMemoryHistory()); await router.push('/login')
  const w = mount(LoginView, { global: { plugins: [router] } })
  await w.get('input[name="username"]').setValue('user001'); await w.get('input[name="password"]').setValue('incorrect')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('[role="alert"]').text()).toContain('账号或密码不正确')
  expect(router.currentRoute.value.path).toBe('/login'); expect(session.user.value).toBeNull()
})
it('administrators also enter the user view after login, including an old developer return URL', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ access_token: 'a'.repeat(43), token_type: 'Bearer', expires_at: new Date(Date.now()+60000).toISOString(), user: { id: 'a', username: 'admin001', display_name: '管理员', role: 'ADMIN', enabled: true } }))))
  const router = createAppRouter(createMemoryHistory()); await router.push('/login?redirect=/models')
  const w = mount(LoginView, { global: { plugins: [router] } })
  await w.get('input[name="username"]').setValue('admin001'); await w.get('input[name="password"]').setValue('test-password')
  await w.get('form').trigger('submit'); await flushPromises()
  await vi.waitFor(() => expect(router.currentRoute.value.path).toBe('/live'))
  expect(session.user.value?.role).toBe('ADMIN')
})
