import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ModelsView from './ModelsView.vue'
import { fetchModelDetail, fetchModels, setCurrentModel, renameModel, deleteModels } from '../api/models'
import { makeModelDetailPayload, makeModelsPayload } from '../test/fixtures'
import type { ModelsPayload } from '../api/types'
import { filterModels, emptyModelFilters, modelListCsv } from './modelLibrary'
import {gTrainingApi} from '../api/weatherTraining'

vi.mock('../api/models', () => ({ fetchModels: vi.fn(), fetchModelDetail: vi.fn(), setCurrentModel: vi.fn(), renameModel: vi.fn(), deleteModels: vi.fn() }))
vi.mock('../api/weatherTraining',()=>({gTrainingApi:{savedModels:vi.fn()}}))
enableAutoUnmount(afterEach)
let list: ModelsPayload
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(gTrainingApi.savedModels).mockResolvedValue([])
  list = makeModelsPayload()
  vi.mocked(fetchModels).mockImplementation(async () => structuredClone(list))
  vi.mocked(fetchModelDetail).mockImplementation(async id => ({ ...makeModelDetailPayload(), ...list.rows.find(row => row.id === id)! }))
  vi.mocked(renameModel).mockImplementation(async (id, name) => { const row = list.rows.find(row => row.id === id)!; row.name = name; return row })
  vi.mocked(deleteModels).mockImplementation(async ids => { list.rows = list.rows.filter(row => !ids.includes(row.id)); return { deleted: ids } })
})
async function show(path = '/models') {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/models', name: 'models', component: ModelsView },
    { path: '/models/:id', name: 'model-detail', component: ModelsView },
    { path: '/train', component: { template: '<div>训练</div>' } },
    { path: '/field', component: { template: '<div>构场</div>' } },
  ] })
  await router.push(path); await router.isReady()
  const w = mount(ModelsView, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return { w, router }
}
const dialog = () => new DOMWrapper(document.querySelector('dialog')!)

describe('模型库管理工作台', () => {
  it('单棚训练保存成品在模型库展示，并能打开对应报告',async()=>{
    vi.mocked(gTrainingApi.savedModels).mockResolvedValue([{id:'saved-job',name:'新构场成品',target:'field',algorithm:'ridge',interpolation:'rbf',filename:'训练.xlsx',dataset_id:'dataset',saved_at:'2026-11-14T00:00:00Z',params:{alpha:10},test:{mae:.16,rmse:.22,r2:.96,n:432},artifacts:{field:'hash'}}])
    const {w,router}=await show()
    expect(w.get('[aria-label="单棚训练成品"]').text()).toContain('新构场成品')
    await w.get('a[href="/train?job=saved-job"]').trigger('click');await flushPromises()
    expect(router.currentRoute.value.query.job).toBe('saved-job')
  })
  it('默认展示完整列表，查看之前不请求详情或更换工作区模型', async () => {
    const { w } = await show()
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
    expect(document.querySelector('dialog')).toBeNull()
    expect(fetchModelDetail).not.toHaveBeenCalled()
    expect(setCurrentModel).not.toHaveBeenCalled()
    expect(w.get('.model-table thead').text()).toContain('保存时间')
    expect(w.get('a[href="/train"]').text()).toContain('新增模型')
    expect(w.find('.workspace-card').exists()).toBe(false)
    expect(w.text()).not.toContain('工作区选用')
    expect(w.text()).not.toContain('设为工作区模型')
    for (const row of w.findAll('.model-table tbody tr')) {
      expect(row.get('.row-actions').findAll('a,button').map(action => action.text())).toEqual(['查看', '编辑', '删除'])
    }
  })
  it('名称筛选在提交后应用，重置恢复完整列表', async () => {
    const { w } = await show()
    await w.get('input[type="search"]').setValue(list.rows[1]!.name)
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
    await w.get('form[aria-label="模型筛选"]').trigger('submit')
    expect(w.findAll('.model-table tbody tr')).toHaveLength(1)
    await w.findAll('button').find(button => button.text() === '重置')!.trigger('click')
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
  })
  it('无匹配结果时显示空态并可清空条件', async () => {
    const { w } = await show()
    await w.get('input[type="search"]').setValue('不存在的模型')
    await w.get('form[aria-label="模型筛选"]').trigger('submit')
    expect(w.get('.empty-cell').text()).toContain('没有符合筛选条件')
    await w.get('.empty-cell button').trigger('click')
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
  })
  it('保存日期顺序错误时保留现有查询并提示', async () => {
    const { w } = await show()
    await w.get('[aria-label="保存开始日期"]').setValue('2026-11-01')
    await w.get('[aria-label="保存结束日期"]').setValue('2026-10-01')
    await w.get('form[aria-label="模型筛选"]').trigger('submit')
    expect(w.get('[role="alert"]').text()).toContain('开始日期不能晚于')
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
  })
  it('分页与本页全选只作用于当前展示的记录', async () => {
    list.rows = Array.from({ length: 23 }, (_, i) => ({ ...list.rows[0]!, id: i + 1, name: `模型 ${i + 1}`, is_current: i === 0 }))
    const { w } = await show()
    expect(w.findAll('.model-table tbody tr')).toHaveLength(10)
    await w.get('[aria-label="选择本页模型"]').setValue(true)
    expect(w.get('.pagination').text()).toContain('已选 10 项')
    await w.get('[aria-label="下一页"]').trigger('click')
    expect(w.get('.model-table tbody').text()).toContain('模型 11')
    expect((w.get('[aria-label="选择本页模型"]').element as HTMLInputElement).checked).toBe(false)
  })
  it('查看打开详情抽屉，关闭后保留筛选条件', async () => {
    const { w, router } = await show()
    await w.get('input[type="search"]').setValue(list.rows[0]!.name)
    await w.get('form[aria-label="模型筛选"]').trigger('submit')
    await router.push('/models/1'); await flushPromises()
    expect(dialog().attributes('aria-label')).toBe('模型详情')
    expect(dialog().text()).toContain('空间留出验证')
    expect(fetchModelDetail).toHaveBeenCalledWith(1)
    expect(setCurrentModel).not.toHaveBeenCalled()
    await dialog().get('[aria-label="关闭模型详情"]').trigger('click'); await flushPromises()
    expect(document.querySelector('dialog')).toBeNull()
    expect(w.findAll('.model-table tbody tr')).toHaveLength(1)
  })
  it('详情抽屉仅展示模型信息，参数记录也不提供选用或用于构场操作', async () => {
    list.rows[1]!.has_artifact = false
    await show('/models/2')
    expect(dialog().text()).toContain('仅保存参数')
    expect(dialog().text()).not.toContain('设为工作区模型')
    expect(dialog().findAll('button').some(button => button.text() === '用于构场')).toBe(false)
    expect(dialog().find('.current-status').exists()).toBe(false)
    expect(setCurrentModel).not.toHaveBeenCalled()
  })
  it('仍保护被构场配置引用的模型，不兼容模型可以正常编辑和删除', async () => {
    const { w } = await show()
    const rows = w.findAll('.model-table tbody tr')
    expect(rows[0]!.findAll('button').find(button => button.text() === '删除')!.attributes('disabled')).toBeDefined()
    expect(rows[2]!.findAll('button').every(button => button.attributes('disabled') === undefined)).toBe(true)
  })
  it('编辑提交后刷新列表，名称始终作为纯文本渲染', async () => {
    const { w } = await show()
    await w.findAll('.model-table tbody tr')[1]!.findAll('button').find(button => button.text() === '编辑')!.trigger('click')
    await dialog().get('input').setValue('<img src=x onerror=alert(1)>')
    await dialog().get('form').trigger('submit'); await flushPromises()
    expect(renameModel).toHaveBeenCalledWith(2, '<img src=x onerror=alert(1)>')
    expect(w.find('img').exists()).toBe(false)
    expect(w.get('.model-table').text()).toContain('<img src=x')
  })
  it('删除确认之前不提交，成功后从列表移除', async () => {
    const { w } = await show()
    await w.findAll('.model-table tbody tr')[1]!.findAll('button').find(button => button.text() === '删除')!.trigger('click')
    expect(deleteModels).not.toHaveBeenCalled()
    await dialog().findAll('button').find(button => button.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(deleteModels).toHaveBeenCalledWith([2])
    expect(w.findAll('.model-table tbody tr')).toHaveLength(2)
  })
  it('后端拒绝删除时保留记录并显示原因', async () => {
    vi.mocked(deleteModels).mockRejectedValue(new Error('已被实时会话引用，不能删除'))
    const { w } = await show()
    await w.findAll('.model-table tbody tr')[1]!.findAll('button').find(button => button.text() === '删除')!.trigger('click')
    await dialog().findAll('button').find(button => button.text() === '确认删除')!.trigger('click'); await flushPromises()
    expect(dialog().get('[role="alert"]').text()).toContain('实时会话引用')
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
  })
  it('列表读取失败保留旧记录并显示真实原因', async () => {
    const { w } = await show()
    vi.mocked(fetchModels).mockRejectedValue(new Error('数据库暂不可用'))
    await w.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises()
    expect(w.get('[role="alert"]').text()).toContain('数据库暂不可用')
    expect(w.findAll('.model-table tbody tr')).toHaveLength(3)
  })
})

describe('模型筛选与导出', () => {
  it('组合来源、状态与日期，不自行重算兼容性', () => {
    const rows = makeModelsPayload().rows
    const filters = { ...emptyModelFilters(), fit: 'borrowed', source: rows[1]!.data_file }
    expect(filterModels(rows, filters).map(row => row.id)).toEqual([2])
    expect(filterModels(rows, { ...filters, start: '2099-01-01' })).toEqual([])
  })
  it('CSV 转义引号和换行，并阻止名称被解释成公式', () => {
    const row = { ...makeModelsPayload().rows[0]!, name: '=HYPERLINK("bad")\n名称' }
    const csv = modelListCsv([row])
    expect(csv.startsWith('\uFEFF')).toBe(true)
    expect(csv).toContain('"\'=HYPERLINK(""bad"")\n名称"')
    expect(csv).toContain('保存时间')
    expect(csv).not.toContain('工作区选用')
  })
})
