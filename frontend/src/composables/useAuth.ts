import { computed } from 'vue'
import { ApiError, getJson, postJson } from '../api/client'
import { acceptLogin, clearSession, session, setNotice, setPhase, setVerifiedUser, type Account, type LoginResult } from '../api/session'

let pending: { token: string; promise: Promise<void> } | null = null
export function homeFor(_role?: Account['role']) { return '/live' }
export function passwordError(value: string): string {
  return value.length < 8 || new TextEncoder().encode(value).length > 72
    ? '密码至少 8 个字符，UTF-8 编码不超过 72 字节。' : ''
}
async function restore(force = false): Promise<void> {
  const token = session.token.value
  if (!token || session.user.value && !force) return
  if (pending?.token === token) return pending.promise
  setPhase('checking')
  const promise = (async () => {
    try {
      const account = await getJson<Account>('/api/auth/me')
      if (session.token.value === token) { setVerifiedUser(account); setNotice('') }
    } catch (e) {
      if (session.token.value !== token) return
      if (e instanceof ApiError && e.status === 401) clearSession('登录已失效，请重新登录。')
      else { setPhase('error'); setNotice(e instanceof Error ? e.message : '暂时无法验证登录状态，请重试。') }
    } finally {
      if (pending?.token === token) pending = null
    }
  })()
  pending = { token, promise }
  return promise
}
async function login(username: string, password: string) {
  const result = await postJson<LoginResult>('/api/auth/login', { username, password })
  acceptLogin(result)
}
async function logout() {
  try { await postJson('/api/auth/logout') }
  finally { clearSession('已退出登录。') }
}
export function useAuth() {
  return { ...session, isAdmin: computed(() => session.user.value?.role === 'ADMIN'), restore, login, logout, clear: clearSession }
}
