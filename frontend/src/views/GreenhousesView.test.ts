import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import GreenhousesView from './GreenhousesView.vue'
import { greenhouseApi } from '../api/accounts'
import { regionApi } from '../api/regions'
import { testArchive, testRegionCatalog } from '../test/archiveFixture'
vi.mock('../api/accounts', () => ({ greenhouseApi: { list: vi.fn(), models: vi.fn(), bind: vi.fn(), create: vi.fn(), update: vi.fn() } }))
vi.mock('../api/regions', async original => ({ ...await original<object>(), regionApi: { list: vi.fn() } }))
enableAutoUnmount(afterEach)
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(greenhouseApi.list).mockResolvedValue([testArchive]); vi.mocked(regionApi.list).mockResolvedValue(testRegionCatalog)
  vi.mocked(greenhouseApi.models).mockResolvedValue([{ id: 'm1', name: '气象模型', status: 'PUBLISHED', model_id: 3, external_schema: 'two', package_id: 'p1' }])
})
async function open() { const w = mount(GreenhousesView); await flushPromises(); return w }
it('创建棚体配置只要求尺寸和名称，不绑定地区', async () => {
  vi.mocked(greenhouseApi.create).mockResolvedValue(testArchive)
  const w = await open(); const form = w.get('.archive-form')
  await form.get('input[maxlength="120"]').setValue('白山市默认人参棚')
  await form.trigger('submit'); await flushPromises()
  expect(greenhouseApi.create).toHaveBeenCalledWith({ name: testArchive.name, enabled: true, length_m: 18, width_m: 2.1, height_m: 1.3017 })
  expect(w.find('[aria-label="市（州）"]').exists()).toBe(false)
  expect(w.find('[aria-label="地区筛选"]').exists()).toBe(false)
  expect(regionApi.list).not.toHaveBeenCalled()
  expect(w.text()).toContain('棚体档案管理'); expect(w.text()).not.toContain('授予棚体权限')
})
it('编辑结构尺寸并绑定已发布模型，旧地区数据不写回', async () => {
  vi.mocked(greenhouseApi.bind).mockResolvedValue(testArchive)
  vi.mocked(greenhouseApi.update).mockResolvedValue(testArchive)
  const w = await open(); await w.get('button[aria-label="编辑档案 白山市默认人参棚"]').trigger('click')
  const edit = w.get('.archive-form'); await edit.findAll('input[type="number"]')[0]!.setValue(18)
  await edit.trigger('submit'); await flushPromises()
  expect(greenhouseApi.update).toHaveBeenCalledWith('h1', {name:testArchive.name,enabled:true,length_m:18,width_m:2.1,height_m:1.3017})
  expect(w.text()).not.toContain('区县专用')
  expect(w.text()).not.toContain('全市默认档案')
  const form = w.findAll('form').find(f => f.text().includes('已发布模型'))!
  await form.get('select').setValue('m1'); await form.trigger('submit'); await flushPromises()
  expect(greenhouseApi.bind).toHaveBeenCalledWith('h1', 'm1')
})

it('刷新后可配置训练页发布的组合，停用模型不进入选项', async () => {
  vi.mocked(greenhouseApi.models).mockResolvedValueOnce([])
  const w=await open(); await w.get('button[aria-label="编辑档案 白山市默认人参棚"]').trigger('click')
  expect(w.text()).toContain('与 F 成品组合发布')
  vi.mocked(greenhouseApi.models).mockResolvedValue([
    {id:'new-model',name:'训练页发布的 G/F',status:'PUBLISHED',model_id:3,external_schema:'full',package_id:'package-new'},
    {id:'disabled',name:'已停用组合',status:'DISABLED',model_id:3,external_schema:'two',package_id:'package-old'},
  ])
  await w.findAll('button').find(b=>b.text()==='刷新')!.trigger('click'); await flushPromises()
  const form=w.findAll('form').find(f=>f.text().includes('已发布模型'))!
  expect(form.text()).toContain('训练页发布的 G/F')
  expect(form.text()).not.toContain('已停用组合')
  vi.mocked(greenhouseApi.bind).mockResolvedValue(testArchive)
  await form.get('select').setValue('new-model'); await form.trigger('submit'); await flushPromises()
  expect(greenhouseApi.bind).toHaveBeenCalledWith('h1','new-model')
})
