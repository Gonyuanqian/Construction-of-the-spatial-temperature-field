import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, enableAutoUnmount } from '@vue/test-utils'
import UsersView from './UsersView.vue'
import { accountApi } from '../api/accounts'
import { loginAs } from '../test/authFixture'
import { clearSession } from '../api/session'
vi.mock('../api/accounts', () => ({ accountApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), password: vi.fn() } }))
enableAutoUnmount(afterEach)
const account = { id: 'u1', username: 'user001', display_name: '用户一', role: 'USER' as const, enabled: true }
beforeEach(() => { loginAs(); vi.clearAllMocks(); vi.mocked(accountApi.list).mockResolvedValue({ items: [account], total: 1 }) })
afterEach(() => clearSession())
const options = { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } }
it('creates an ordinary account and clears the initial password after saving', async () => {
  vi.mocked(accountApi.create).mockResolvedValue(account)
  const w = mount(UsersView, options); await flushPromises()
  const form = w.get('form')
  await form.findAll('input')[0]!.setValue('user001'); await form.findAll('input')[1]!.setValue('用户一')
  await form.get('input[type="password"]').setValue('test-password-123')
  expect((form.get('select').element as HTMLSelectElement).value).toBe('USER')
  await form.trigger('submit'); await flushPromises()
  expect(accountApi.create).toHaveBeenCalledWith({ username: 'user001', display_name: '用户一', password: 'test-password-123', role: 'USER' })
  expect(w.text()).toContain('账号已创建'); expect(w.html()).not.toContain('test-password-123')
})
it('updates enabled state only after a save and displays a backend conflict', async () => {
  vi.mocked(accountApi.update).mockRejectedValue(new Error('至少保留一个启用的管理员。'))
  const w = mount(UsersView, options); await flushPromises(); await w.get('button[aria-label="管理 user001"]').trigger('click')
  await w.get('input[type="checkbox"]').setValue(false)
  expect(accountApi.update).not.toHaveBeenCalled()
  await w.get('form').trigger('submit'); await flushPromises()
  expect(accountApi.update).toHaveBeenCalledWith('u1', { display_name: '用户一', role: 'USER', enabled: false })
  expect(w.get('[role="alert"]').text()).toContain('至少保留一个启用的管理员')
})
it('requires matching reset passwords before revoking a user session', async () => {
  vi.mocked(accountApi.password).mockResolvedValue({})
  const w = mount(UsersView, options); await flushPromises(); await w.get('button[aria-label="管理 user001"]').trigger('click')
  const reset = w.findAll('form')[1]!
  await reset.findAll('input')[0]!.setValue('new-password-123'); await reset.findAll('input')[1]!.setValue('different-password')
  await reset.trigger('submit'); expect(accountApi.password).not.toHaveBeenCalled()
  await reset.findAll('input')[1]!.setValue('new-password-123'); await reset.trigger('submit'); await flushPromises()
  expect(accountApi.password).toHaveBeenCalledWith('u1', 'new-password-123')
  expect(w.text()).toContain('已有登录已撤销')
  expect(reset.findAll('input').every(i => (i.element as HTMLInputElement).value === '')).toBe(true)
})
