import { acceptLogin, clearSession, type Account } from '../api/session'

/** Existing workspace tests exercise an already authenticated administrator. */
export function loginAs(role: Account['role'] = 'ADMIN') {
  clearSession()
  acceptLogin({ access_token: (role === 'ADMIN' ? 'a' : 'u').repeat(43), token_type: 'Bearer',
    expires_at: new Date(Date.now() + 43200000).toISOString(),
    user: { id: role === 'ADMIN' ? 'test-admin' : 'test-user', username: role === 'ADMIN' ? 'admin001' : 'user001', display_name: role === 'ADMIN' ? '测试管理员' : '测试用户', role, enabled: true },
  })
}
