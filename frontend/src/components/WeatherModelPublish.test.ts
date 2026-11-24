import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import WeatherModelPublish from './WeatherModelPublish.vue'
import { gTrainingApi, type GJob } from '../api/weatherTraining'
import type { WeatherDeployment } from '../api/accounts'

vi.mock('../api/weatherTraining', () => ({gTrainingApi: {
  fieldModels: vi.fn(), deployments: vi.fn(), publish: vi.fn(), deploymentStatus: vi.fn(),
}}))
enableAutoUnmount(afterEach)
const job: GJob = {id:'saved-g', name:'已完成 G', state:'done', options:{name:'已完成 G',external_schema:'two',algorithm:'ridge',validation_fraction:.2,n_estimators:120,max_depth:12,min_samples_leaf:2,alpha:10,seed:42}, artifacts:{current:'sha',history:'sha'},dataset_id:'dataset-g',filename:'训练.xlsx',created_at:'2026-11-06T00:00:00Z',elapsed_s:10,progress:'已完成',error:null,cancel_requested:false,result:null}
const published: WeatherDeployment = {id:'deployment-1',name:'已完成 G · 气象构场',model_id:3,package_id:'package-1',external_schema:'two',status:'PUBLISHED',g_training_job_id:'saved-g',field_model_name:'冻结 F'}
const operationKey = vi.fn(() => 'stable-operation')
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(gTrainingApi.fieldModels).mockResolvedValue([{id:3,name:'冻结 F',has_artifact:true,saved_at:'2026-11-06'}])
  vi.mocked(gTrainingApi.deployments).mockResolvedValue([])
  vi.mocked(gTrainingApi.publish).mockResolvedValue(published)
})
async function open() {
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{template:'<div />'}},{path:'/admin/greenhouses',component:{template:'<div />'}}]})
  await router.push('/')
  const w=mount(WeatherModelPublish,{props:{job,operationKey},global:{plugins:[router]}})
  await flushPromises(); return w
}
it('选择已保存 F 后才允许组合发布，并给出档案配置入口',async()=>{
  const w=await open()
  expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  await w.get('select').setValue(3)
  await w.get('form').trigger('submit'); await flushPromises()
  expect(gTrainingApi.publish).toHaveBeenCalledWith('saved-g',{name:published.name,field_model_id:3},'stable-operation')
  expect(w.text()).toContain('气象模型已发布')
  expect(w.get('a').attributes('href')).toBe('/admin/greenhouses')
  expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
})
it('返回页面从服务端恢复发布记录，阻止重复创建同名组合',async()=>{
  vi.mocked(gTrainingApi.deployments).mockResolvedValue([published])
  const w=await open(); await w.get('select').setValue(3)
  await w.get('form').trigger('submit'); await flushPromises()
  expect(gTrainingApi.publish).not.toHaveBeenCalled()
  expect(w.text()).toContain('该组合已有发布记录（已发布）')
  expect(w.text()).toContain('冻结 F')
})
it('响应失败后可以直接重试，并复用操作编号',async()=>{
  vi.mocked(gTrainingApi.publish).mockRejectedValueOnce(new Error('连接中断')).mockResolvedValue(published)
  const w=await open(); await w.get('select').setValue(3)
  await w.get('form').trigger('submit'); await flushPromises()
  expect(w.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  expect(w.text()).toContain('连接中断')
  await w.get('form').trigger('submit'); await flushPromises()
  expect(gTrainingApi.publish).toHaveBeenCalledTimes(2)
  expect(vi.mocked(gTrainingApi.publish).mock.calls.map(c=>c[2])).toEqual(['stable-operation','stable-operation'])
})
it('旧任务的发布回执不会写到另一个 G 的页面',async()=>{
  let resolve!: (value: WeatherDeployment)=>void
  vi.mocked(gTrainingApi.publish).mockReturnValue(new Promise(r=>{resolve=r}))
  const w=await open(); await w.get('select').setValue(3); await w.get('form').trigger('submit')
  await w.setProps({job:{...job,id:'other-g',name:'另一个 G'}}); await flushPromises()
  resolve(published); await flushPromises()
  expect(w.find('.publication-table').exists()).toBe(false)
  expect(w.text()).not.toContain('气象模型已发布')
})
it('支持停用和重新发布，保留同一条组合记录',async()=>{
  vi.mocked(gTrainingApi.deployments).mockResolvedValue([published])
  vi.mocked(gTrainingApi.deploymentStatus).mockResolvedValueOnce({...published,status:'DISABLED'}).mockResolvedValueOnce(published)
  const w=await open()
  await w.get('.publication-table button').trigger('click'); await flushPromises()
  expect(gTrainingApi.deploymentStatus).toHaveBeenLastCalledWith('deployment-1','DISABLED')
  expect(w.text()).toContain('已停用')
  await w.get('.publication-table button').trigger('click'); await flushPromises()
  expect(gTrainingApi.deploymentStatus).toHaveBeenLastCalledWith('deployment-1','PUBLISHED')
  expect(w.findAll('.publication-table tbody tr')).toHaveLength(1)
})
it('没有 F 成品时引导训练并阻止发布',async()=>{
  vi.mocked(gTrainingApi.fieldModels).mockResolvedValue([])
  const w=await open(); await w.get('form').trigger('submit'); await flushPromises()
  expect(w.text()).toContain('暂无 F 成品')
  expect(gTrainingApi.publish).not.toHaveBeenCalled()
})
