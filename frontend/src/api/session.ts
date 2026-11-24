import { readonly, ref, shallowRef } from 'vue'

export interface Account {
  id: string
  username: string
  display_name: string
  role: 'ADMIN' | 'USER'
  enabled: boolean
}
export interface LoginResult {
  access_token: string
  expires_at: string
  token_type: 'Bearer'
  user: Account
}
type Phase = 'anonymous' | 'unknown' | 'checking' | 'authenticated' | 'error'
const KEY = 'tfield.auth.session.v1'
function stored(): { token: string; expires: string } | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(KEY) ?? 'null')
    if (value && /^[A-Za-z0-9_-]{43}$/.test(value.token) && Date.parse(value.expires) > Date.now()) return value
    sessionStorage.removeItem(KEY)
  } catch { /* A blocked or malformed storage entry is not an authenticated session. */ }
  return null
}
const initial = stored()
const token = ref<string | null>(initial?.token ?? null)
const user = shallowRef<Account | null>(null)
const phase = ref<Phase>(token.value ? 'unknown' : 'anonymous')
const revision = ref(0)
const notice = ref('')
let expiryTimer: ReturnType<typeof setTimeout> | undefined

function persist(value: { token: string; expires: string } | null) {
  try {
    if (value) sessionStorage.setItem(KEY, JSON.stringify(value))
    else sessionStorage.removeItem(KEY)
  } catch { /* In-memory login remains usable when browser storage is blocked. */ }
}
function schedule(expires: string) {
  if (expiryTimer) clearTimeout(expiryTimer)
  const current = token.value
  expiryTimer = setTimeout(() => {
    if (current === token.value) clearSession('登录已过期，请重新登录。')
  }, Math.max(0, Date.parse(expires) - Date.now()))
}
if (initial) schedule(initial.expires)

export const session = {
  token: readonly(token), user: readonly(user), phase: readonly(phase),
  revision: readonly(revision), notice: readonly(notice),
}
export function setPhase(value: Phase) { phase.value = value }
export function setNotice(value: string) { notice.value = value }
export function setVerifiedUser(value: Account) {
  if (!value.enabled || !['ADMIN', 'USER'].includes(value.role)) throw new Error('账号信息无效，请重新登录。')
  if (user.value && (user.value.id !== value.id || user.value.role !== value.role)) revision.value++
  user.value = value
  phase.value = 'authenticated'
}
export function acceptLogin(result: LoginResult) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(result.access_token) || !Number.isFinite(Date.parse(result.expires_at)) || Date.parse(result.expires_at) <= Date.now()) throw new Error('登录响应无效。')
  setVerifiedUser(result.user)
  token.value = result.access_token
  revision.value++
  notice.value = ''
  persist({ token: result.access_token, expires: result.expires_at })
  schedule(result.expires_at)
}
export function clearSession(message = '') {
  if (expiryTimer) clearTimeout(expiryTimer)
  expiryTimer = undefined
  token.value = null
  user.value = null
  phase.value = 'anonymous'
  revision.value++
  notice.value = message
  persist(null)
}
