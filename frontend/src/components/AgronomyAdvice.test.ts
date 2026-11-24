// @vitest-environment jsdom
import {flushPromises,mount,enableAutoUnmount,RouterLinkStub} from '@vue/test-utils'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import AgronomyAdvice from './AgronomyAdvice.vue'
import {assistantApi,type AssistantRun} from '../api/assistant'
import {loginAs} from '../test/authFixture'
import {clearSession} from '../api/session'
import {ginsengStages} from '../assistant/agronomy'

vi.mock('../api/assistant',()=>({assistantApi:{capabilities:vi.fn(),snapshot:vi.fn(),submit:vi.fn(),run:vi.fn(),cancel:vi.fn()}}))
enableAutoUnmount(afterEach)
const answered:AssistantRun={id:'r1',conversation_id:'c1',question:'农事建议',crop:'人参',stage:ginsengStages[0],status:'answered',cycle:2,events:[],result:{claims:[{text:'已核验的条件性农事建议',evidence_ids:[],conditions:['需现场核实栽培方式']}],missing_conditions:['参龄'],citations:[],snapshot:{data_mode:'external_weather'}}}
beforeEach(()=>{
 vi.useFakeTimers();localStorage.clear();loginAs('USER');vi.resetAllMocks()
 vi.mocked(assistantApi.capabilities).mockResolvedValue({model_configured:true,knowledge_configured:true,model:'test',min_cycles:2,max_cycles:6,limitations:[]})
 vi.mocked(assistantApi.snapshot).mockImplementation(async id=>({snapshot_id:'s1',session_id:id!,frame_index:0,source_time:'2026-11-14',model_id:null,data_mode:'external_weather',facts:[]}))
 vi.mocked(assistantApi.submit).mockResolvedValue(answered)
 vi.mocked(assistantApi.cancel).mockResolvedValue({...answered,status:'cancelled'})
})
afterEach(()=>{vi.useRealTimers();clearSession()})
function open(id:string|null='field-1'){return mount(AgronomyAdvice,{props:{sessionId:id,active:true},global:{stubs:{RouterLink:RouterLinkStub}}})}
async function generate(w:ReturnType<typeof open>){await w.get('select').setValue(ginsengStages[0]);await w.get('.advice-update').trigger('click');await flushPromises()}
it('不猜测阶段或自动请求，未构场时保持占位并禁用生成',async()=>{
 const w=open(null);expect((w.get('select').element as HTMLSelectElement).value).toBe('')
 await w.get('select').setValue(ginsengStages[0]);expect(w.get('.advice-update').attributes('disabled')).toBeDefined()
 expect(w.text()).toContain('温度场构建完成后');expect(assistantApi.capabilities).not.toHaveBeenCalled()
})
it('显式生成绑定画布快照与阶段，保留条件，继续提问链接沿用同一会话',async()=>{
 const w=open();await generate(w)
 expect(assistantApi.snapshot).toHaveBeenCalledWith('field-1')
 expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({crop:'人参',stage:ginsengStages[0],snapshot_id:'s1',question:expect.stringContaining('外部湿度不是棚内湿度')}))
 expect(w.text()).toContain('已核验的条件性农事建议');expect(w.text()).toContain('需现场核实栽培方式');expect(w.text()).toContain('参龄')
 expect(w.findComponent(RouterLinkStub).props('to')).toEqual({path:'/assistant',query:{conversation:'c1'}})
})
it('网络重试复用幂等键，不重复捕获或创建新会话',async()=>{
 vi.mocked(assistantApi.submit).mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce(answered)
 const w=open();await generate(w);expect(w.text()).toContain('连接中断')
 await w.get('.advice-update').trigger('click');await flushPromises()
 expect(assistantApi.snapshot).toHaveBeenCalledTimes(1)
 expect(vi.mocked(assistantApi.submit).mock.calls[0]![0]).toEqual(vi.mocked(assistantApi.submit).mock.calls[1]![0])
})
it('字段快照错位时阻止提交，未配置助手时给出真实错误',async()=>{
 const w=open();vi.mocked(assistantApi.snapshot).mockResolvedValue({snapshot_id:'s2',session_id:'other',frame_index:0,source_time:'',model_id:null,data_mode:'external_weather',facts:[]})
 await generate(w);expect(w.text()).toContain('快照与当前画布不一致');expect(assistantApi.submit).not.toHaveBeenCalled()
 vi.mocked(assistantApi.capabilities).mockResolvedValue({model_configured:false,knowledge_configured:false,model:'',min_cycles:2,max_cycles:6,limitations:[]})
 await w.get('.advice-update').trigger('click');await flushPromises();expect(w.text()).toContain('尚未配置')
})
it('阶段、温度场、账号变更均清除旧结果，未请求时可带条件进入问答',async()=>{
 const w=open();await generate(w);await w.get('select').setValue(ginsengStages[1]);expect(w.text()).not.toContain('已核验')
 expect(w.findComponent(RouterLinkStub).props('to')).toEqual({path:'/assistant',query:{crop:'人参',stage:ginsengStages[1]}})
 await w.get('.advice-update').trigger('click');await flushPromises();await w.setProps({sessionId:'field-2'});expect(w.text()).not.toContain('已核验')
 loginAs('ADMIN');await flushPromises();expect((w.get('select').element as HTMLSelectElement).value).toBe('')
})
it('更换温度场后，迟到的提交响应不会出现在新场景',async()=>{
 let resolve!:(value:AssistantRun)=>void
 vi.mocked(assistantApi.submit).mockImplementationOnce(()=>new Promise(r=>{resolve=r}))
 const w=open();await generate(w);await w.setProps({sessionId:'field-2'});resolve(answered);await flushPromises()
 expect(w.text()).not.toContain('已核验');expect(w.findComponent(RouterLinkStub).props('to')).not.toHaveProperty('query.conversation')
})
it('离页暂停轮询，返回跟进原任务，结束后仅展示已发布结果',async()=>{
 vi.mocked(assistantApi.submit).mockResolvedValue({...answered,status:'queued',result:null})
 vi.mocked(assistantApi.run).mockResolvedValue(answered)
 const w=open();await generate(w);expect(w.text()).toContain('正在分析与核验')
 await w.setProps({active:false});await vi.advanceTimersByTimeAsync(10_000);expect(assistantApi.run).not.toHaveBeenCalled()
 await w.setProps({active:true});await vi.advanceTimersByTimeAsync(2000);expect(w.text()).toContain('已核验')
 expect(assistantApi.submit).toHaveBeenCalledTimes(1);w.unmount();await vi.advanceTimersByTimeAsync(10_000);expect(assistantApi.run).toHaveBeenCalledTimes(1)
})
it('核验未通过时显示简洁状态，保留查看原会话的入口，不编造建议',async()=>{
 vi.mocked(assistantApi.submit).mockResolvedValue({...answered,status:'failed',error_code:'review_stalled',detail:'关于“内部完整提示语”这次尚未形成可靠结论',result:null})
 const w=open();await generate(w)
 expect(w.text()).toContain('本次建议未通过依据核验，暂未发布')
 expect(w.text()).not.toContain('内部完整提示语');expect(w.findAll('.advice-item')).toHaveLength(0)
 expect(w.findComponent(RouterLinkStub).props('to')).toEqual({path:'/assistant',query:{conversation:'c1'}})
})
