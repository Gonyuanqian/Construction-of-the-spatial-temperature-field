import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => { sessionStorage.clear(); vi.resetModules(); vi.restoreAllMocks() })
afterEach(async () => { (await import('../api/session')).clearSession(); vi.restoreAllMocks() })
function stored() { sessionStorage.setItem('tfield.auth.session.v1', JSON.stringify({ token: 's'.repeat(43), expires: new Date(Date.now()+600000).toISOString() })) }
describe('restoring a browser session', () => {
  it('verifies the stored token with the server and uses the returned role', async () => {
    stored()
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ id: 'user', username: 'user001', display_name: '用户', role: 'USER', enabled: true })))
    vi.stubGlobal('fetch', fetcher)
    const { useAuth } = await import('./useAuth'); const auth = useAuth()
    await Promise.all([auth.restore(), auth.restore()])
    expect(fetcher).toHaveBeenCalledTimes(1); expect(auth.user.value?.role).toBe('USER')
    expect(new Headers((fetcher.mock.calls as unknown as [string, RequestInit][])[0]?.[1]?.headers).get('Authorization')).toBe(`Bearer ${'s'.repeat(43)}`)
  })
  it('keeps a stored token on a temporary outage and supports retry', async () => {
    stored(); vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const auth = (await import('./useAuth')).useAuth()
    await auth.restore(); expect(auth.phase.value).toBe('error'); expect(auth.token.value).not.toBeNull(); expect(auth.user.value).toBeNull()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ id: 'user', username: 'user001', display_name: '用户', role: 'USER', enabled: true }))))
    await auth.restore(true); expect(auth.phase.value).toBe('authenticated')
  })
  it('rejects an expired server session without restoring any account data', async () => {
    stored(); vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"请先登录。"}', { status: 401 })))
    const auth = (await import('./useAuth')).useAuth(); await auth.restore()
    expect(auth.token.value).toBeNull(); expect(auth.phase.value).toBe('anonymous')
  })
})
