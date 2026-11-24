import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { acceptLogin, clearSession, session } from './session'
import { authFetch, getJson, postJson, uploadDataset, deleteJson, writeJson } from './client'
import { assistantApi } from './assistant'
import { loginAs } from '../test/authFixture'

beforeEach(() => { clearSession(); vi.restoreAllMocks() })
afterEach(() => { clearSession(); vi.restoreAllMocks() })
const ok = () => new Response('{}', { headers: { 'Content-Type': 'application/json' } })
describe('authenticated transport', () => {
  it('carries the same Bearer header on JSON, upload and mutation requests', async () => {
    loginAs()
    const fetcher = vi.fn(async () => ok()); vi.stubGlobal('fetch', fetcher)
    await getJson('/api/models'); await postJson('/api/live/start')
    await uploadDataset(new File(['data'], 'sample.xlsx'))
    await deleteJson('/api/calibration/jobs/task'); await writeJson('PATCH', '/api/admin/users/user', { enabled: false })
    for (const call of fetcher.mock.calls as unknown as [string, RequestInit][]) expect(new Headers(call[1]?.headers).get('Authorization')).toBe(`Bearer ${'a'.repeat(43)}`)
    expect(sessionStorage.getItem('tfield.auth.session.v1')).not.toContain('ADMIN')
  })
  it('does not attach a token to login or external URLs and retains login errors', async () => {
    loginAs()
    const fetcher = vi.fn(async () => new Response('{"detail":"账号或密码不正确。"}', { status: 401 })); vi.stubGlobal('fetch', fetcher)
    await expect(postJson('/api/auth/login', { username: 'user', password: 'wrong' })).rejects.toMatchObject({ status: 401 })
    expect(new Headers((fetcher.mock.calls as unknown as [string, RequestInit][])[0]?.[1]?.headers).has('Authorization')).toBe(false)
    expect(session.user.value?.role).toBe('ADMIN')
    await authFetch('https://example.com/public')
    expect(new Headers((fetcher.mock.calls as unknown as [string, RequestInit][])[1]?.[1]?.headers).has('Authorization')).toBe(false)
  })
  it('clears an expired session on 401 but keeps a session on 403', async () => {
    loginAs()
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"无权访问"}', { status: 403 })))
    await expect(getJson('/api/admin/users')).rejects.toMatchObject({ status: 403 })
    expect(session.user.value).not.toBeNull()
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"请先登录。"}', { status: 401 })))
    await expect(getJson('/api/auth/me')).rejects.toMatchObject({ status: 401 })
    expect(session.user.value).toBeNull(); expect(session.token.value).toBeNull()
    expect(sessionStorage.getItem('tfield.auth.session.v1')).toBeNull()
  })
  it('a delayed old-user response cannot invalidate or populate the new session', async () => {
    loginAs('ADMIN')
    let resolve!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(r => { resolve = r })))
    const old = getJson('/api/models')
    loginAs('USER')
    resolve(new Response('{"detail":"expired"}', { status: 401 }))
    await expect(old).rejects.toMatchObject({ status: 401 })
    expect(session.user.value?.role).toBe('USER')
  })
  it('SSE uses the authenticated transport', async () => {
    loginAs()
    const fetcher = vi.fn(async () => new Response('event: ready\ndata: {"protocol_version":1}\n\n', { headers: { 'Content-Type': 'text/event-stream' } }))
    vi.stubGlobal('fetch', fetcher)
    await assistantApi.stream('conversation', 0, new AbortController().signal, () => {})
    const request = (fetcher.mock.calls as unknown as [string, RequestInit][])[0]!
    expect(new Headers(request[1].headers).get('Authorization')).toBe(`Bearer ${'a'.repeat(43)}`)
  })
  it('rejects a response body that finishes after an account switch', async () => {
    loginAs()
    let finish!: (value: unknown) => void, started!: () => void
    const reading = new Promise<void>(r => { started = r })
    vi.stubGlobal('fetch', vi.fn(async () => ({ status: 200, ok: true,
      json: () => { started(); return new Promise(r => { finish = r }) },
    })))
    const old = getJson('/api/models'); await reading; loginAs('USER'); finish({ private_admin_result: true })
    await expect(old).rejects.toMatchObject({ status: 401 }); expect(session.user.value?.role).toBe('USER')
  })
  it('rejects malformed login results instead of persisting an untrusted role', () => {
    expect(() => acceptLogin({ access_token: 'invalid', token_type: 'Bearer', expires_at: new Date(Date.now()+10000).toISOString(), user: { id: 'x', username: 'user', display_name: '用户', role: 'USER', enabled: true } })).toThrow()
    expect(session.user.value).toBeNull()
  })
})
