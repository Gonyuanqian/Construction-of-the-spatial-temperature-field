import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import WeatherTrainingPanel from './WeatherTrainingPanel.vue'
import { provideWeatherTraining } from '../composables/useWeatherTraining'
import { loginAs } from '../test/authFixture'
import { clearSession } from '../api/session'
import type { GInfo, GJob, GResult } from '../api/weatherTraining'

const metric = {mae:.3, rmse:.4, r2:.9, n:480}
const result: GResult = { protocol_version:1, options: {} as GResult['options'], dataset: {} as GResult['dataset'], note:'时间留出不参与拟合', baseline:{...metric,mae:2}, split:{method:'chronological',train_frames:80,validation_frames:20,train_start:'2026-07-23T00:00:00',train_end:'2026-07-23T06:35:00',validation_start:'2026-07-23T06:40:00',validation_end:'2026-07-23T08:15:00'}, variants:[{key:'current',label:'单时刻版',training:metric,validation:metric,humidity_mae_pct:null,per_node:[{...metric,key:'p1_node'}],feature_names:['bg_temp']}] }
let info: GInfo, job: GJob | null, done: boolean, jobResult:GResult, requests: {url:string; method:string; body?:unknown}[]
enableAutoUnmount(afterEach)
beforeEach(() => {
  loginAs('ADMIN'); job = null; done = false; requests = []; jobResult=result
  info = {protocol_version:1,dataset_id:'dataset-g',filename:'当前训练.xlsx',dataset:{ready:true,reason:'',n_frames:100,n_nodes:24,invalid_rows:0,time_start:'2026-07-23T00:00:00',time_end:'2026-07-23T08:15:00',inputs:[{key:'bg_temp',label:'背景温度',unit:'℃'},{key:'bg_light',label:'背景光照强度',unit:'源数据单位'},{key:'bg_rh',label:'背景湿度',unit:'%'}]}, jobs:[]}
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url=String(input), method=init?.method ?? 'GET'
    const body=init?.body ? JSON.parse(String(init.body)) : undefined
    requests.push({url,method,body})
    if (url === '/api/weather-training/field-models' || url.endsWith('/deployments')) return new Response('[]')
    if (url === '/api/weather-training/jobs') job={id:'job-g',name:'我的 G 模型',filename:info.filename,dataset_id:info.dataset_id,options:body,state:'running',progress:'训练中',created_at:'2026-11-05T05:00:00Z',elapsed_s:1,error:null,cancel_requested:false,result:null,artifacts:null}
    if (url.endsWith('/cancel') && job) job={...job,state:'cancelled',progress:'已取消'}
    else if (url.includes('/jobs/job-g') && done && job) job={...job,state:'done',progress:'训练完成',result:jobResult,artifacts:{current:'sha',history:'sha'}}
    info.jobs = job ? [job] : []
    return new Response(JSON.stringify(url === '/api/weather-training' ? info : job))
  }))
})
afterEach(() => {clearSession(); vi.unstubAllGlobals(); vi.useRealTimers()})
async function open(corrected=false,readOnly=false) {
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/g',component:WeatherTrainingPanel,props:{corrected,readOnly}},{path:'/away',component:{template:'<p>其他页面</p>'}}]})
  const Host=defineComponent({setup(){provideWeatherTraining();return () => h(RouterView)}})
  await router.push('/g'); const w=mount(Host,{global:{plugins:[router]}}); await flushPromises()
  return {w,router}
}

it('显示三项外部气象及原始光照口径，提交独立 G 配置',async()=>{
  const {w}=await open()
  expect(w.text()).toContain('背景光照强度'); expect(w.text()).toContain('背景湿度')
  await w.get('form').trigger('submit'); await flushPromises()
  const post=requests.find(r=>r.method==='POST')!
  expect(post.url).toBe('/api/weather-training/jobs')
  expect(post.body).toMatchObject({external_schema:'full',algorithm:'extra_trees',validation_fraction:.2})
  expect(requests.some(r=>r.url.includes('/calibration'))).toBe(false)
})

it('切换其他页面后继续轮询，回来显示结果且不重复训练',async()=>{
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
  const {w,router}=await open()
  await w.get('form').trigger('submit'); await flushPromises()
  await router.push('/away'); await flushPromises(); done=true
  await vi.advanceTimersByTimeAsync(1500); await flushPromises()
  await router.push('/g'); await flushPromises()
  expect(w.text()).toContain('背景温度基线'); expect(w.text()).toContain('0.3000')
  expect(requests.filter(r=>r.method==='POST' && r.url==='/api/weather-training/jobs')).toHaveLength(1)
})

it('无效数据阻止训练，取消后保留明确状态',async()=>{
  info.dataset.ready=false; info.dataset.reason='存在缺失气象值'
  const {w}=await open()
  expect(w.text()).toContain('存在缺失气象值')
  expect(w.findAll('button').find(b=>b.text()==='开始训练 G 模型')!.attributes('disabled')).toBeDefined()
  info.dataset.ready=true
  await w.findAll('button').find(b=>b.text()==='刷新')!.trigger('click'); await flushPromises()
  await w.get('form').trigger('submit'); await flushPromises()
  await w.findAll('button').find(b=>b.text()==='取消训练')!.trigger('click'); await flushPromises()
  expect(w.text()).toContain('已取消')
})

it('单棚入口提交 v2 协议，分开展示时间、空间和整棚验证，禁止旧协议组合发布',async()=>{
 vi.useFakeTimers({toFake:['setTimeout','clearTimeout']})
 jobResult={...result,protocol_version:2,spatial_protocol:'independent_house_section_v2',
  field_validation:{mae:.2,rmse:.3,n:240,best_params:{power:2},per_point:[{...metric,house_id:'p1',position:'top'}]},
  variants:result.variants.map(v=>({...v,cross_house:[{...metric,house_id:'p3',training_houses:['p1','p2']}]}))}
 const {w,router}=await open(true)
 expect(w.text()).toContain('基准棚长 6 m');expect(w.text()).toContain('三座独立棚')
 await w.get('form').trigger('submit');await flushPromises()
 expect(requests.find(r=>r.method==='POST')!.body).toMatchObject({spatial_protocol:'independent_house_section_v2'})
 await router.push('/away');done=true;await vi.advanceTimersByTimeAsync(1500);await flushPromises()
 await router.push('/g');await flushPromises()
 expect(w.text()).toContain('F 棚内空间验证');expect(w.text()).toContain('整棚留出 G → F 验证')
 expect(w.text()).toContain('p1、p2')
 expect(requests.some(r=>r.url.includes('field-models'))).toBe(false)
 expect(requests.filter(r=>r.method==='POST'&&r.url==='/api/weather-training/jobs')).toHaveLength(1)
})

it('旧版页面只读，不再提交错误空间协议的新训练',async()=>{
 const {w}=await open(false,true)
 expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
 await w.get('form').trigger('submit');expect(requests.some(r=>r.method==='POST')).toBe(false)
})
