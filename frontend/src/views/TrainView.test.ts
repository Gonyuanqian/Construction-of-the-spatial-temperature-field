import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {defineComponent} from 'vue'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import TrainView from './TrainView.vue'
import {provideModelTraining} from '../composables/useModelTraining'
import {useDataset} from '../composables/useDataset'
import type {GJob,WorkbenchResult,WorkbenchConfig} from '../api/weatherTraining'
vi.mock('../charts/EChart.vue',()=>({default:{name:'EChart',props:['option'],template:'<div class="chart-stub" />'}}))
vi.mock('../design/palette',()=>({readPalette:()=>({paper:'white',ink:'black',inkMuted:'gray',steel:'silver',leaf:'green',leafSoft:'white',net:'black',layerTop:'red',layerMid:'blue',layerLow:'green',bar:'orange',chartAxis:12,chartTitle:14})}))
enableAutoUnmount(afterEach)
let current:GJob|null=null,posts:{url:string;body:Record<string,unknown>}[]=[],auto=false
const points=()=>Array.from({length:8},(_,i)=>({key:'b'+i,label:'B'+(i+1),x:.15+i*.23,z:i%2?.7:.4,residual:.02*(i-3),mae:.16,rmse:.22,r2:.964,n:20,actual:[25,26],predicted:[25.1,25.9]}))
function completed(value:GJob){
 const w=value.options.workbench!,selected={...w.params,...(auto?{max_depth:3}:{})}
 const result:WorkbenchResult={protocol_version:3,training_target:w.target,options:value.options,note:'测试集不参与训练。',selected_params:selected,
  split:{method:'chronological',train_frames:72,validation_frames:18,train_start:'2026-07-23T00:00:00',train_end:'2026-07-23T05:55:00',validation_start:'2026-07-23T06:00:00',validation_end:'2026-07-23T07:25:00'},
  geometry:{width_m:2.1,height_m:1.3017,length_m:6},test:{mae:.16,rmse:.22,r2:.964,n:432,definition:'独立测试集'},
  tuning:{mode:w.mode,selection:'训练时段内验证',trials:auto?[{mae:.2,rmse:.3,r2:.9,n:20,params:selected}]:[]},
  plot:{times:['2026-07-23T06:00:00','2026-07-23T06:05:00'],arch:[[0,0],[1.05,1.3017],[2.1,0]],houses:['p1','p2','p3'].map(house_id=>({house_id,points:points()}))}}
 return{...value,state:'done',elapsed_s:42,result:result as unknown as GJob['result'],artifacts:{field:'a'.repeat(64)}} as GJob
}
beforeEach(()=>{useDataset().reset();current=null;posts=[];auto=false
 vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const url=String(input);let body:unknown={}
  if(init?.method==='POST'){
   const data=JSON.parse(String(init.body));posts.push({url,body:data})
   if(url.endsWith('/save')){body={id:current!.id,name:data.name,target:current!.options.workbench!.target};current={...current!,saved_model:body as GJob['saved_model']}}
   else{current={id:'job-1',state:'running',dataset_id:'dataset-1',filename:'训练.xlsx',options:data,name:data.name,elapsed_s:0,progress:'已提交训练',error:null,cancel_requested:false,result:null,artifacts:null,created_at:'2026-07-23T00:00:00'};body=current}
  }else if(url==='/api/weather-training')body={protocol_version:1,dataset_id:'dataset-1',filename:'训练.xlsx',dataset:{ready:true,n_frames:90,n_nodes:24,invalid_rows:0,inputs:[]},jobs:current?[current]:[],active_job:current?.state==='running'?current:null}
  else if(url.includes('/jobs/')){current=completed(current!);body=current}
  return new Response(JSON.stringify(body),{status:200})
 }))
})
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()})
async function open(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/train',component:TrainView},{path:'/models',component:{template:'<div>模型库</div>'}},{path:'/data',component:{template:'<div>数据</div>'}}]});await router.push('/train')
 const root=defineComponent({setup(){provideModelTraining()},template:'<RouterView />'})
 const wrapper=mount(root,{global:{plugins:[router]}});await flushPromises();return{wrapper,router}}
function button(w:ReturnType<typeof mount>,text:string){return w.findAll('button').find(n=>n.text()===text)!}
async function finish(){await vi.advanceTimersByTimeAsync(1600);await flushPromises()}

it('两个页签各自保留参数，五步按顺序展示且不请求旧标定接口',async()=>{
 const {wrapper:w}=await open()
 expect(w.findAll('h3').map(h=>h.text()[0])).toEqual(['1','2','3','4','5'])
 await w.get('input[type=number]').setValue(133)
 await w.get('#mapping-tab').trigger('click')
 expect(w.text()).toContain('单棚 8 个参考测点')
 expect(w.findAll('input[type=number]').map(n=>(n.element as HTMLInputElement).value)).toEqual(['120','12','2','42'])
 await w.get('#field-tab').trigger('click');expect((w.get('input[type=number]').element as HTMLInputElement).value).toBe('133')
 expect(vi.mocked(fetch).mock.calls.every(([url])=>String(url).startsWith('/api/weather-training'))).toBe(true)
})
it('切换算法后仅提交对应参数，数值无效时禁止训练',async()=>{
 const {wrapper:w}=await open();await w.get('.model-selectors select').setValue('ridge')
 await w.get('.model-selectors label:nth-child(2) select').setValue('rbf')
 expect(w.text()).toContain('正则强度 α');expect(w.text()).toContain('RBF 平滑系数');expect(w.text()).not.toContain('树的数量')
 await w.get('input[type=number]').setValue(0);expect(button(w,'开始训练').attributes('disabled')).toBeDefined()
 await w.get('input[type=number]').setValue(1);await button(w,'开始训练').trigger('click');await flushPromises()
 const value=posts[0]!.body.workbench as WorkbenchConfig
 expect(value).toMatchObject({target:'field',mode:'manual',algorithm:'ridge',interpolation:'rbf',params:{alpha:1,smoothing:.01,lx:.5,lz:.2}})
 expect(value.params).not.toHaveProperty('n_estimators')
})
it('映射默认预测温差，并将切换后的目标写入训练请求',async()=>{
 const {wrapper:w}=await open();await w.get('#mapping-tab').trigger('click')
 expect((w.get('select[aria-label="预测目标"]').element as HTMLSelectElement).value).toBe('delta')
 await w.get('select[aria-label="预测目标"]').setValue('absolute')
 await button(w,'开始训练').trigger('click');await flushPromises()
 expect((posts[0]!.body.workbench as WorkbenchConfig).prediction_target).toBe('absolute')
})
it('已完成的映射报告展示同口径基线和各测点公式',async()=>{
 vi.useFakeTimers();const {wrapper:w,router}=await open();await w.get('#mapping-tab').trigger('click')
 await button(w,'开始训练').trigger('click');await flushPromises();await finish()
 const report=current!.result as unknown as WorkbenchResult
 report.mapping_comparison={selected:'delta',definition:'同一时间留出集',winter_validated:false,
  rows:[{key:'formula',label:'外温＋光照温差公式',mae:.4,rmse:.5,r2:.9,n:432},{key:'delta',label:'预测温差 G',mae:.2,rmse:.3,r2:.95,n:432}],
  formula:{definition:'T_i = T_out + b_i + c_i × light / 10000',light_unit:'原数据单位',intercept:[1,2],light_coefficient:[.1,.2],winter_validated:false}}
 const previous=fetch
 vi.stubGlobal('fetch',vi.fn((input:RequestInfo|URL,init?:RequestInit)=>String(input).endsWith('/jobs/job-1')?Promise.resolve(new Response(JSON.stringify(current))):previous(input,init)))
 await router.push('/train?job=job-1');await flushPromises()
 expect(w.get('[aria-label="气象映射基线对照"]').text()).toContain('外温＋光照温差公式')
 expect(w.text()).toContain('本次保存对象');expect(w.text()).toContain('尚未验证冬季精度')
 await w.get('select[aria-label="预测目标"]').setValue('absolute')
 expect(w.text()).toContain('参数已修改')
})
it('真实回执提供测试指标和图表，保存成品后修改参数不能冒充新结果',async()=>{
 vi.useFakeTimers();const {wrapper:w}=await open()
 await button(w,'开始训练').trigger('click');await flushPromises();expect(w.text()).toContain('正在训练')
 await finish();expect(w.get('[aria-label="测试集指标"]').text()).toContain('0.9640');expect(w.find('.chart-stub').exists()).toBe(true)
 await w.get('.save-form input').setValue('新构场模型');await button(w,'保存模型').trigger('submit');await flushPromises()
 expect(posts.find(p=>p.url.endsWith('/save'))?.body).toEqual({name:'新构场模型'})
 expect(w.text()).toContain('模型已保存')
 await w.get('input[type=number]').setValue(200);expect(w.text()).toContain('参数已修改')
})
it('自动优选发送范围并回填最优参数，之后允许保存',async()=>{
 vi.useFakeTimers();auto=true;const {wrapper:w}=await open()
 await w.get('input[type=radio][value=auto]').setValue()
 await button(w,'开始训练').trigger('click');await flushPromises()
 expect((posts[0]!.body.workbench as WorkbenchConfig).search).toEqual({max_depth:[3,5],power:[1,2]})
 await finish();expect((w.findAll('input[type=number]')[1]!.element as HTMLInputElement).value).toBe('3')
 expect(w.text()).toContain('最优参数已回填');expect(w.find('.changed').exists()).toBe(false)
 await w.get('.save-form input').setValue('最优模型');expect(button(w,'保存模型').attributes('disabled')).toBeUndefined()
})
it('切路由后任务继续并恢复，两个页签不混用测试成绩',async()=>{
 vi.useFakeTimers();const {wrapper:w,router}=await open()
 await button(w,'开始训练').trigger('click');await flushPromises()
 await router.push('/models');await finish();await router.push('/train');await flushPromises()
 expect(w.get('[aria-label="测试集指标"]').text()).toContain('0.1600');expect(posts).toHaveLength(1)
 await w.get('#mapping-tab').trigger('click');expect(w.find('[aria-label="测试集指标"]').exists()).toBe(false)
 await button(w,'开始训练').trigger('click');await flushPromises();expect((posts[1]!.body.workbench as WorkbenchConfig).target).toBe('mapping')
 await finish();expect(w.text()).toContain('预测温度与实测温度对比')
})
it('切换页签后，迟到的历史报告响应不能把页面切回旧模型类型',async()=>{
 vi.useFakeTimers();const {wrapper:w,router}=await open()
 await button(w,'开始训练').trigger('click');await flushPromises();await finish()
 const previous=fetch;let resolve!:(value:Response)=>void
 vi.stubGlobal('fetch',vi.fn((input:RequestInfo|URL,init?:RequestInit)=>String(input).endsWith('/jobs/job-1')?new Promise<Response>(r=>resolve=r):previous(input,init)))
 await router.push('/train?job=job-1');await flushPromises()
 await w.get('#mapping-tab').trigger('click');await flushPromises()
 resolve(new Response(JSON.stringify(current)));await flushPromises()
 expect(w.get('#mapping-tab').attributes('aria-selected')).toBe('true')
 expect(w.find('[aria-label="测试集指标"]').exists()).toBe(false)
})
