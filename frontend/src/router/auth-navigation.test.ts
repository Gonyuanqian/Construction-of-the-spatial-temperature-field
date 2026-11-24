import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { createAppRouter } from './index'
import { returnPath } from './access'
import { clearSession, session } from '../api/session'
import { loginAs } from '../test/authFixture'

beforeEach(() => { clearSession(); vi.restoreAllMocks() })
afterEach(() => { clearSession(); vi.restoreAllMocks() })
describe('role routing', () => {
  it('保留实时监测，并把原实时回放地址重定向到同一页面',async()=>{
    loginAs('USER'); const router=createAppRouter(createMemoryHistory())
    await router.push('/live')
    expect(router.currentRoute.value.matched.at(-1)?.components?.default.name).toBe('LiveView')
    await router.push('/replay')
    expect(router.currentRoute.value.path).toBe('/live')
  })
  it('anonymous deep links return to the login screen with an internal return address', async () => {
    const router = createAppRouter(createMemoryHistory()); await router.push('/models/3')
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/models/3')
  })
  it('ordinary users cannot visit developer training or administration', async () => {
    loginAs('USER'); const router = createAppRouter(createMemoryHistory())
    for (const path of ['/data', '/train', '/models/3', '/field', '/admin/users', '/admin/greenhouses']) {
      await router.push(path); expect(router.currentRoute.value.path).toBe('/live')
    }
    await router.push('/account'); expect(router.currentRoute.value.path).toBe('/account')
  })
  it('both roles enter the user workspace from the system root and the previous monitor URL', async () => {
    for (const role of ['ADMIN', 'USER'] as const) {
      loginAs(role)
      const router = createAppRouter(createMemoryHistory())
      await router.push('/'); expect(router.currentRoute.value.path).toBe('/live')
      expect(router.currentRoute.value.meta.workspace).toBe('user')
      await router.push('/monitor'); expect(router.currentRoute.value.path).toBe('/live')
    }
  })
  it.each(['ADMIN','USER'] as const)('role %s uses replay and assistant in the user workspace', async role => {
    loginAs(role); const router=createAppRouter(createMemoryHistory())
    for(const path of ['/live','/greenhouse-control','/assistant','/assistant/field/example']) {
      await router.push(path); expect(router.currentRoute.value.path).toBe(path)
      expect(router.currentRoute.value.meta.workspace).toBe('user')
    }
    await router.push('/developer/live'); expect(router.currentRoute.value.path).toBe('/live')
  })
  it('administrators retain all workspaces and can manage accounts', async () => {
    loginAs(); const router = createAppRouter(createMemoryHistory())
    for (const path of ['/train', '/admin/users', '/admin/greenhouses']) { await router.push(path); expect(router.currentRoute.value.path).toBe(path) }
  })
  it('login return links cannot redirect outside the app or to a forbidden role', () => {
    const router = createAppRouter(createMemoryHistory())
    for (const link of ['//example.com', 'https://example.com', '/\\example.com', '/login', '/admin/users']) expect(returnPath(router, link, 'USER')).toBe('/live')
    expect(returnPath(router, '/models/3', 'ADMIN')).toBe('/models/3')
    expect(session.user.value).toBeNull()
  })
})
