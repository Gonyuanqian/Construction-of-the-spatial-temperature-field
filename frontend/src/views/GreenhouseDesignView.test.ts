import {beforeEach,afterEach,it,expect,vi} from 'vitest'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import {createRouter,createMemoryHistory} from 'vue-router'
import View from './GreenhouseDesignView.vue'
import {designsApi,newDesign,type DesignPreview} from '../api/greenhouseDesigns'
import {loginAs} from '../test/authFixture'
vi.mock('../api/greenhouseDesigns',async original=>({...await original<object>(),designsApi:{list:vi.fn(),get:vi.fn(),create:vi.fn(),update:vi.fn(),remove:vi.fn(),activate:vi.fn(),preview:vi.fn()}}))
vi.mock('../components/GreenhouseDesignScene.vue',()=>({default:{template:'<div>三维预览</div>'}}))
enableAutoUnmount(afterEach)
const fixture:DesignPreview={beds:[{x:.7,y:.8,width:1.2,length:16.6}],rows:[],sprinklers:[{x:1,y:2}],area_m2:108,usable_length_m:16.6,plant_count:996,notices:[],ai:{available:false,status:'planned'},model:{geometry_only:true,monitoring_supported:true,detail:'几何示意'}}
beforeEach(()=>{vi.useFakeTimers();vi.clearAllMocks();loginAs('USER');vi.mocked(designsApi.list).mockResolvedValue({items:[],total:0});vi.mocked(designsApi.preview).mockResolvedValue(fixture)})
afterEach(()=>vi.useRealTimers())
async function open(){const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:View},{path:'/live',component:{template:'<div/>'}}]});await router.push('/');const w=mount(View,{global:{plugins:[router],stubs:{Teleport:true,MonitoringLocationDialog:true,DesignInspectionPanel:{template:'<section class="design-panel ai-design-panel">AI 检验</section>'}}}});await flushPromises();return{w,router}}
it('保留四组参数、三列与独立的AI检验模块',async()=>{const{w}=await open();expect(w.findAll('fieldset section')).toHaveLength(4);expect(w.find('.design-columns').exists()).toBe(true);expect(w.text()).toContain('位置与朝向');expect(w.text()).toContain('AI 检验');expect(designsApi.list).toHaveBeenCalledOnce()})
it('厘米输入按米发送，并将四组配置保存到服务端',async()=>{const{w}=await open();const row=w.findAll('label').find(l=>l.text().includes('植株间距'))!;await row.get('input').setValue(25);vi.mocked(designsApi.create).mockImplementation(async spec=>({id:'saved',revision:1,spec}));await w.findAll('button').find(b=>b.text()==='保存草稿')!.trigger('click');await flushPromises();expect(designsApi.create).toHaveBeenCalledWith(expect.objectContaining({planting:expect.objectContaining({plant_spacing_m:.25}),irrigation:expect.objectContaining({sprinkler_enabled:true})}));expect(w.text()).toContain('方案已保存')})
it('读取旧版本并提交修订号，冲突保留修改提示',async()=>{const spec=newDesign();vi.mocked(designsApi.list).mockResolvedValue({items:[{id:'old',revision:4,spec}],total:1});vi.mocked(designsApi.get).mockResolvedValue({id:'old',revision:4,spec});const{w}=await open();await w.get('.design-selector select').setValue('old');await flushPromises();vi.mocked(designsApi.update).mockRejectedValue(new Error('方案已在其他窗口更新'));await w.findAll('button').find(b=>b.text()==='保存草稿')!.trigger('click');await flushPromises();expect(designsApi.update).toHaveBeenCalledWith('old',4,expect.any(Object));expect(w.get('[role="alert"]').text()).toContain('其他窗口更新')})
it('手动喷头可修改，保存并用于监测先保存再激活指定版本',async()=>{const{w,router}=await open();await w.findAll('button').find(b=>b.text()==='手动调整')!.trigger('click');const x=w.findAll('label').find(l=>l.text().includes('横向 x'))!;await x.get('input').setValue(2);await vi.advanceTimersByTimeAsync(400);await flushPromises();vi.mocked(designsApi.create).mockImplementation(async spec=>({id:'new',revision:1,spec}));vi.mocked(designsApi.activate).mockResolvedValue({id:'new',revision:1,spec:newDesign()});await w.findAll('button').find(b=>b.text()==='保存并用于监测')!.trigger('click');await flushPromises();expect(designsApi.create).toHaveBeenCalledWith(expect.objectContaining({irrigation:expect.objectContaining({placement:'manual',sprinklers:[{x:2,y:2}]})}));expect(designsApi.activate).toHaveBeenCalledWith('new',1);expect(router.currentRoute.value.query).toEqual({applyDesign:'new',designRevision:'1'})})
it('不支持的棚型保留保存入口，禁用用于监测',async()=>{vi.mocked(designsApi.preview).mockResolvedValue({...fixture,model:{...fixture.model,monitoring_supported:false}});const{w}=await open();expect(w.findAll('button').find(b=>b.text()==='保存并用于监测')!.attributes('disabled')).toBeDefined();expect(w.findAll('button').find(b=>b.text()==='保存草稿')!.attributes('disabled')).toBeUndefined()})

it('旧方案可启用补光灯，保存间距和高度并绘制灯位',async()=>{
 const {lighting,...legacy}=newDesign()
 vi.mocked(designsApi.list).mockResolvedValue({items:[{id:'legacy',revision:2,spec:legacy}],total:1})
 vi.mocked(designsApi.get).mockResolvedValue({id:'legacy',revision:2,spec:legacy})
 vi.mocked(designsApi.preview).mockImplementation(async spec=>({...fixture,lights:spec.lighting?.enabled?[{x:1.3,y:2,z:1.5}]:[]}))
 vi.mocked(designsApi.update).mockImplementation(async (id,revision,spec)=>({id,revision:revision+1,spec}))
 const {w}=await open()
 await w.get('.design-selector select').setValue('legacy');await flushPromises()
 const enable=w.get<HTMLInputElement>('.lighting-heading input')
 expect(enable.element.checked).toBe(false)
 await enable.setValue(true)
 const lampField=(text:string)=>w.findAll('label').find(label=>label.text().includes(text))!.get('input')
 await lampField('补光灯纵向间距').setValue('2.5')
 await lampField('补光灯安装高度').setValue('1.5')
 await vi.advanceTimersByTimeAsync(400);await flushPromises()
 expect(w.get('.lighting-heading').text()).toContain('1 盏')
 expect(w.findAll('.lamp-position')).toHaveLength(1)
 await w.findAll('button').find(button=>button.text()==='保存草稿')!.trigger('click')
 await flushPromises()
 expect(designsApi.update).toHaveBeenCalledWith('legacy',2,expect.objectContaining({
  lighting:{...lighting,enabled:true,spacing_m:2.5,mounting_height_m:1.5},
 }))
})

it('取消保留方案，确认后按版本删除并返回新方案草稿',async()=>{
 const plan={id:'saved',revision:3,spec:{...newDesign(),name:'试验棚一号'}}
 const second={id:'second',revision:1,spec:{...newDesign(),name:'试验棚二号'}}
 vi.mocked(designsApi.list).mockResolvedValue({items:[plan,second],total:2})
 vi.mocked(designsApi.get).mockResolvedValue(plan)
 vi.mocked(designsApi.remove).mockResolvedValue({deleted:true})
 const {w}=await open()
 const button=w.get('button.design-delete'),select=w.get('.design-selector select')
 expect(button.attributes('disabled')).toBeDefined()
 await select.setValue(plan.id);await flushPromises()
 await button.trigger('click')
 expect(w.get('dialog').text()).toContain(plan.spec.name)
 await w.get('dialog button[autofocus]').trigger('click')
 expect(designsApi.remove).not.toHaveBeenCalled()
 await button.trigger('click')
 await w.get('dialog .design-delete-confirm').trigger('click');await flushPromises()
 expect(designsApi.remove).toHaveBeenCalledWith(plan.id,plan.revision)
 expect(w.find('dialog').exists()).toBe(false)
 expect((select.element as HTMLSelectElement).value).toBe('')
 expect(select.findAll('option').map(option=>option.attributes('value'))).toEqual(['',second.id])
 expect(w.get('[role="status"]').text()).toBe('方案已删除。')
})

it('删除被拒绝时保留当前方案和未保存的修改',async()=>{
 const plan={id:'locked',revision:1,spec:newDesign()}
 vi.mocked(designsApi.list).mockResolvedValue({items:[plan],total:1})
 vi.mocked(designsApi.get).mockResolvedValue(plan)
 vi.mocked(designsApi.remove).mockRejectedValue(new Error('请在温室控制中停止全部后再删除。'))
 const {w}=await open()
 const select=w.get('.design-selector select')
 await select.setValue(plan.id);await flushPromises()
 const name=w.get<HTMLInputElement>('.scheme-name input')
 await name.setValue('未保存的新名称')
 await w.get('button.design-delete').trigger('click')
 expect(w.get('dialog').text()).toContain('当前未保存的修改')
 await w.get('dialog .design-delete-confirm').trigger('click');await flushPromises()
 expect(w.get('dialog [role="alert"]').text()).toContain('停止全部')
 expect(name.element.value).toBe('未保存的新名称')
 expect((select.element as HTMLSelectElement).value).toBe(plan.id)
})
