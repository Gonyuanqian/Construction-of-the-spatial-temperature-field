// @vitest-environment jsdom
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loginAs } from '../test/authFixture'
import { clearSession } from '../api/session'
import {createRouter,createMemoryHistory} from 'vue-router'
import AssistantView from './AssistantView.vue'
import { assistantApi } from '../api/assistant'

Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() })

vi.mock('../api/assistant', () => ({ assistantApi: {
  capabilities: vi.fn(), snapshot: vi.fn(), submit: vi.fn(), run: vi.fn(), cancel: vi.fn(),
  conversations:vi.fn(),conversation:vi.fn(),snapshotInfo:vi.fn(),
  renameConversation:vi.fn(),deleteConversation:vi.fn(),
} }))
beforeEach(() => loginAs())
afterEach(() => { vi.clearAllMocks(); localStorage.clear(); clearSession() })
const snap = { snapshot_id: 's1', session_id: 'session', frame_index: 8,
  source_time: '2026-07-27 12:40:00', model_id: 3, data_mode: 'replay', facts: [] }
async function setup(configured = true) {
  vi.mocked(assistantApi.capabilities).mockResolvedValue({ model_configured: configured,
    knowledge_configured: false, model: 'deepseek-flash', min_cycles: 2, max_cycles: 6, limitations: [] })
  vi.mocked(assistantApi.snapshot).mockResolvedValue(snap)
  vi.mocked(assistantApi.conversations).mockResolvedValue([])
  const wrapper = mount(AssistantView, { global: { stubs: { Teleport: true, RouterLink:RouterLinkStub } } })
  await flushPromises()
  return wrapper
}

describe('农业助手页面', () => {
  it('历史改名保存到服务端，切换对话后不会被首问覆盖',async()=>{
    const wrapper=await setup()
    let conversation=''
    vi.mocked(assistantApi.submit).mockImplementation(async body=>{
      conversation=body.conversation_id!;return {id:'rename-run',question:body.question,conversation_id:conversation,status:'queued',cycle:0,events:[]}
    })
    vi.mocked(assistantApi.run).mockImplementation(async()=>({id:'rename-run',question:'原始问题',conversation_id:conversation,status:'answered',cycle:2,events:[]}))
    vi.mocked(assistantApi.renameConversation).mockResolvedValue({id:'unused',title:'棚内温差讨论'})
    await wrapper.get('textarea').setValue('原始问题');await wrapper.get('form.composer').trigger('submit');await flushPromises()
    await wrapper.get('.chat-more').trigger('click');await wrapper.get('.chat-menu button').trigger('click')
    await wrapper.get('#chat-name').setValue('棚内温差讨论');await wrapper.get('form.chat-dialog').trigger('submit');await flushPromises()
    expect(assistantApi.renameConversation).toHaveBeenCalledWith(conversation,'棚内温差讨论')
    expect(wrapper.get('.chat-title').text()).toBe('棚内温差讨论')
    await wrapper.get('.new-chat').trigger('click')
    expect(wrapper.get('.chat-title').text()).toBe('棚内温差讨论')
    wrapper.unmount()
  })
  it('删除失败保留会话，确认成功后清空当前对话，取消不发送删除请求',async()=>{
    const wrapper=await setup()
    let conversation=''
    vi.mocked(assistantApi.submit).mockImplementation(async body=>{
      conversation=body.conversation_id!;return {id:'delete-run',question:body.question,conversation_id:conversation,status:'queued',cycle:0,events:[]}
    })
    vi.mocked(assistantApi.run).mockImplementation(async()=>({id:'delete-run',question:'待删除问题',conversation_id:conversation,status:'answered',cycle:2,events:[]}))
    await wrapper.get('textarea').setValue('待删除问题');await wrapper.get('form.composer').trigger('submit');await flushPromises()
    await wrapper.get('.chat-more').trigger('click');await wrapper.get('.delete-chat').trigger('click')
    await wrapper.get('.chat-dialog button[type="button"]').trigger('click')
    expect(assistantApi.deleteConversation).not.toHaveBeenCalled()
    await wrapper.get('.chat-more').trigger('click');await wrapper.get('.delete-chat').trigger('click')
    vi.mocked(assistantApi.deleteConversation).mockRejectedValueOnce(new Error('删除未完成'))
    await wrapper.get('form.chat-dialog').trigger('submit');await flushPromises()
    expect(wrapper.get('.chat-dialog [role="alert"]').text()).toBe('删除未完成')
    expect(wrapper.find('.chat-title').exists()).toBe(true)
    vi.mocked(assistantApi.deleteConversation).mockResolvedValue({id:conversation,deleted:true})
    await wrapper.get('form.chat-dialog').trigger('submit');await flushPromises()
    expect(wrapper.find('.chat-title').exists()).toBe(false)
    expect(wrapper.find('.welcome').exists()).toBe(true)
    wrapper.unmount()
  })
  it('清除缓存中的单次检验和旧服务端摘要，同时保留普通与已追问的对话',async()=>{
    const automatic='请检验这份已保存的人参温室设计方案，分别检查位置与朝向'
    const root={id:'inspection-root',conversation_id:'inspection-chat',question:automatic,status:'answered',cycle:1,events:[],result:{claims:[],missing_conditions:[],citations:[],snapshot:{data_mode:'greenhouse_design'}}}
    const normal={id:'normal-root',conversation_id:'normal-chat',question:'正常农业对话',status:'answered',cycle:1,events:[],result:{claims:[]}}
    const continued={...root,id:'continued-root',conversation_id:'continued-chat'}
    localStorage.setItem('tfield-assistant-chats-v3:ADMIN:test-admin',JSON.stringify({active:'inspection-chat',chats:[
      {id:'inspection-chat',title:automatic,runs:[root],snapshot:null,server:true},
      {id:'summary-only',title:automatic,runs:[],snapshot:null,server:true},
      {id:'normal-chat',title:normal.question,runs:[normal],snapshot:null,server:true},
      {id:'continued-chat',title:automatic,runs:[continued,{id:'followup',parent_run_id:continued.id,question:'如何调整通道？',status:'answered',cycle:1,events:[]}],snapshot:null,server:true},
      {id:'partial-history',title:automatic,runs:[{id:'followup-only',parent_run_id:'earlier-root',question:'继续解释',status:'answered',cycle:1,events:[]}],snapshot:null,server:true}
    ]}))
    const w=await setup()
    expect(w.findAll('.chat-title')).toHaveLength(3)
    expect(w.text()).toContain('正常农业对话');expect(w.findAll('.exchange')).toHaveLength(0)
    const saved=JSON.parse(localStorage.getItem('tfield-assistant-chats-v3:ADMIN:test-admin')!)
    expect(saved.chats.map((c:{id:string})=>c.id)).toEqual(['normal-chat','continued-chat','partial-history']);w.unmount()
  })
  it('只打开单次检验不加入对话列表，发送追问后才保存为对话',async()=>{
    const old={id:'inspection-root',conversation_id:'inspection-chat',conversation_origin:'greenhouse_design_inspection' as const,question:'请检验这份已保存的人参温室设计方案',status:'answered',cycle:1,events:[],result:{claims:[{text:'保留的方案检验结果',evidence_ids:[]}],missing_conditions:[],citations:[],snapshot:{data_mode:'greenhouse_design'}}}
    vi.mocked(assistantApi.conversation).mockResolvedValue({id:'inspection-chat',title:old.question,head_run_id:old.id,updated_at:1,has_older:false,runs:[old]})
    const w=await linked('conversation=inspection-chat')
    expect(w.text()).toContain('保留的方案检验结果');expect(w.findAll('.chat-title')).toHaveLength(0)
    expect(assistantApi.submit).not.toHaveBeenCalled()
    vi.mocked(assistantApi.submit).mockResolvedValue({id:'inspection-followup',conversation_id:'inspection-chat',parent_run_id:old.id,question:'该怎样调整通道？',status:'answered',cycle:1,events:[]})
    await w.get('textarea').setValue('该怎样调整通道？');await w.get('form').trigger('submit');await flushPromises()
    expect(w.findAll('.chat-title')).toHaveLength(1);expect(w.get('.chat-list button').text()).toBe('该怎样调整通道？')
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({parent_run_id:old.id,conversation_id:'inspection-chat'}));w.unmount()
  })
  async function linked(query:string) {
    const initial=await setup();initial.unmount()
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/assistant',component:{template:'<div />'}}]})
    await router.push('/assistant?'+query)
    const wrapper=mount(AssistantView,{global:{plugins:[router],stubs:{RouterLink:RouterLinkStub}}});await flushPromises();return wrapper
  }
  it('从农事卡片恢复同一会话和气象快照，下一轮沿用父任务与阶段',async()=>{
    const old={id:'advice-run',conversation_id:'advice-chat',question:'农事建议',crop:'人参',stage:'现蕾开花期',snapshot_id:'weather-snapshot',status:'answered',cycle:2,events:[],result:{claims:[{text:'卡片中的原始农事建议',evidence_ids:[]}],missing_conditions:[],citations:[],snapshot:{data_mode:'external_weather'}}}
    vi.mocked(assistantApi.conversation).mockResolvedValue({id:'advice-chat',title:'农事建议',head_run_id:'advice-run',updated_at:1,has_older:false,runs:[old]})
    vi.mocked(assistantApi.snapshotInfo).mockResolvedValue({...snap,snapshot_id:'weather-snapshot',data_mode:'external_weather',model_id:null})
    const w=await linked('conversation=advice-chat')
    expect(w.text()).toContain('卡片中的原始农事建议');expect(w.text()).toContain('气象构场快照');expect(w.text()).not.toContain('模型 #null')
    vi.mocked(assistantApi.submit).mockRejectedValue(new Error('test'))
    await w.get('textarea').setValue('具体应该检查什么？');await w.get('form').trigger('submit');await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({conversation_id:'advice-chat',parent_run_id:'advice-run',snapshot_id:'weather-snapshot',crop:'人参',stage:'现蕾开花期'}));w.unmount()
  })
  it('无建议时仅预填人参与阶段，不自动调用模型',async()=>{
    const w=await linked('crop='+encodeURIComponent('人参')+'&stage='+encodeURIComponent('出苗展叶期'))
    vi.mocked(assistantApi.submit).mockRejectedValue(new Error('test'))
    expect(assistantApi.submit).not.toHaveBeenCalled()
    await w.get('textarea').setValue('想了解管理要点');await w.get('form').trigger('submit');await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({crop:'人参',stage:'出苗展叶期',snapshot_id:null,parent_run_id:null}));w.unmount()
  })
  it('无权读取链接会话时显示错误，不回落到其他历史回答',async()=>{
    vi.mocked(assistantApi.conversation).mockRejectedValue(new Error('会话不存在或无权访问'))
    const w=await linked('conversation=unowned')
    expect(w.text()).toContain('会话不存在或无权访问');expect(w.findAll('.exchange')).toHaveLength(0);w.unmount()
  })
  it('用户只恢复自己的本机记录，不加载管理员旧共享缓存',async()=>{
    loginAs('USER')
    const chat=(id:string,title:string)=>({active:id,chats:[{id,title,runs:[{id:'turn-'+id,question:title,status:'answered',cycle:0,events:[]}],snapshot:null}]})
    localStorage.setItem('tfield-assistant-chats-v1',JSON.stringify(chat('admin-chat','管理员私有旧记录')))
    localStorage.setItem('tfield-assistant-chats-v3:ADMIN:test-user',JSON.stringify(chat('old-admin-chat','降级前的管理员缓存')))
    localStorage.setItem('tfield-assistant-chats-v3:USER:test-user',JSON.stringify(chat('user-chat','当前用户记录')))
    const wrapper=await setup()
    expect(wrapper.text()).toContain('当前用户记录')
    expect(wrapper.text()).not.toContain('管理员私有旧记录')
    expect(wrapper.text()).not.toContain('降级前的管理员缓存')
    expect(localStorage.getItem('tfield-assistant-chats-v1')).not.toBeNull()
    wrapper.unmount()
  })
  it('原生推理完成后显示公开答复，不在正文插入通道工程状态',async()=>{
    const wrapper=await setup()
    vi.mocked(assistantApi.submit).mockResolvedValue({id:'native-turn',question:'点温',status:'queued',cycle:0,events:[]})
    vi.mocked(assistantApi.run).mockResolvedValue({id:'native-turn',question:'点温',status:'answered',cycle:2,events:[],
      thinking:{enabled:true,effort:'low',calls:2,reasoning_chars:300,status:'completed'},
      result:{claims:[{text:'审核后的公开回答',evidence_ids:[]}],missing_conditions:[],citations:[],snapshot:{}}})
    await wrapper.get('textarea').setValue('点温');await wrapper.get('form').trigger('submit');await flushPromises()
    expect(wrapper.text()).not.toContain('DeepSeek 原生 thinking')
    expect(wrapper.text()).not.toContain('页面展示分析摘要与核验后的回答')
    expect(wrapper.text()).toContain('审核后的公开回答')
    wrapper.unmount()
  })
  it('联网搜索默认开启，用户关闭后随问题发送，新对话恢复默认',async()=>{
    const wrapper=await setup()
    const toggle=wrapper.get('[aria-label="联网搜索"]')
    expect(toggle.attributes('aria-pressed')).toBe('true')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-pressed')).toBe('false')
    vi.mocked(assistantApi.submit).mockRejectedValue(new Error('test'))
    await wrapper.get('textarea').setValue('根区温度是什么？')
    await wrapper.get('form').trigger('submit');await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({web_search_enabled:false}))
    await wrapper.get('.new-chat').trigger('click')
    expect(wrapper.get('[aria-label="联网搜索"]').attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })
  it('外部原文单独显示来源链接、读取日期和未入库标记',async()=>{
    const wrapper=await setup()
    vi.mocked(assistantApi.submit).mockResolvedValue({id:'web-turn',question:'根温研究',status:'queued',cycle:0,events:[]})
    vi.mocked(assistantApi.run).mockResolvedValue({id:'web-turn',question:'根温研究',status:'answered',cycle:3,events:[],
      result:{claims:[{text:'有条件的原文研究说明',evidence_ids:['W:one']}],missing_conditions:[],snapshot:{},citations:[{
        id:'W:one',text:'原文摘录',origin:'web_original',source_title:'大学农业推广原文',source_url:'https://extension.purdue.edu/research',
        retrieved_at:'2026-10-31T10:00:00Z',review_status:'claim_review_passed'}]}})
    await wrapper.get('textarea').setValue('根温研究');await wrapper.get('form').trigger('submit');await flushPromises()
    expect(wrapper.text()).toContain('联网原文 · 2026-10-31 读取')
    expect(wrapper.text()).toContain('未入本地知识库')
    expect(wrapper.get('a[target="_blank"]').attributes('href')).toBe('https://extension.purdue.edu/research')
    wrapper.unmount()
  })
  it('连续提问关联同一会话上一轮，开启新对话后清空关联',async()=>{
    const wrapper=await setup()
    const seen:Parameters<typeof assistantApi.submit>[0][]=[]
    vi.mocked(assistantApi.submit).mockImplementation(async body=>{
      seen.push(body)
      return {id:'turn'+seen.length,question:body.question,conversation_id:body.conversation_id,status:'queued',cycle:0,events:[]}
    })
    vi.mocked(assistantApi.run).mockImplementation(async id=>({id,question:'已保存的问题',conversation_id:seen.at(-1)!.conversation_id,
      resolved_context:id==='turn2' ? {selection:{position:{x:2,y:1,z:.25}}} : undefined,
      status:'answered',cycle:2,events:[],result:{claims:[{text:'已保存的回答',evidence_ids:['K:1']}],missing_conditions:[],citations:[],snapshot:{}}}))
    for(const q of ['叶片温度是什么？','继续解释']) {
      await wrapper.get('textarea').setValue(q);await wrapper.get('form').trigger('submit');await flushPromises()
    }
    expect(seen[1]!.conversation_id).toBe(seen[0]!.conversation_id)
    expect(seen[1]!.parent_run_id).toBe('turn1')
    expect((wrapper.get('[aria-label="x 坐标"]').element as HTMLInputElement).value).toBe('2')
    await wrapper.get('.new-chat').trigger('click')
    await wrapper.get('textarea').setValue('新问题');await wrapper.get('form').trigger('submit');await flushPromises()
    expect(seen[2]!.conversation_id).not.toBe(seen[0]!.conversation_id)
    expect(seen[2]!.parent_run_id).toBeNull()
    expect(seen[2]!.position).toBeNull()
    wrapper.unmount()
  })
  it('从服务器会话列表恢复历史，并沿用其父任务及作物条件',async()=>{
    const wrapper=await setup()
    wrapper.unmount()
    vi.mocked(assistantApi.conversations).mockResolvedValue([{id:'server-chat',title:'服务端会话',head_run_id:'server-turn',updated_at:1}])
    vi.mocked(assistantApi.conversation).mockResolvedValue({id:'server-chat',title:'服务端会话',head_run_id:'server-turn',updated_at:1,has_older:false,
      runs:[{id:'server-turn',question:'历史问题',conversation_id:'server-chat',crop:'番茄',stage:'苗期',status:'answered',cycle:2,events:[],
        result:{claims:[{text:'服务端原始回答',evidence_ids:['K:1']}],missing_conditions:[],citations:[],snapshot:{}}}]})
    const restored=mount(AssistantView,{global:{stubs:{RouterLink:RouterLinkStub}}}); await flushPromises()
    await restored.get('.chat-list button').trigger('click');await flushPromises()
    expect(restored.text()).toContain('服务端原始回答')
    vi.mocked(assistantApi.submit).mockRejectedValue(new Error('test'))
    await restored.get('textarea').setValue('你回答错了');await restored.get('form').trigger('submit');await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({conversation_id:'server-chat',parent_run_id:'server-turn',crop:'番茄',stage:'苗期'}))
    restored.unmount()
  })
  it('提交两个区域的明确边界，不夹带点位坐标',async () => {
    const wrapper=await setup()
    vi.mocked(assistantApi.submit).mockRejectedValue(new Error('test response'))
    await wrapper.get('select').setValue('comparison')
    for (const index of [0,1]) {
      for (const axis of ['x','y','z']) {
        await wrapper.get(`[aria-label="区域${index} ${axis}下限"]`).setValue(String(index))
        await wrapper.get(`[aria-label="区域${index} ${axis}上限"]`).setValue(String(index+2))
      }
    }
    await wrapper.get('textarea').setValue('比较两个区域均温')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({position:null,region:null,
      regions:{first:{x_min:0,x_max:2,y_min:0,y_max:2,z_min:0,z_max:2},
        second:{x_min:1,x_max:3,y_min:1,y_max:3,z_min:1,z_max:3}}}))
    wrapper.unmount()
  })
  it('连接故障的部分结果保留提示、固定时刻和定位链接',async () => {
    const wrapper=await setup()
    vi.mocked(assistantApi.submit).mockResolvedValue({id:'partial',question:'热点？',status:'queued',cycle:0,events:[]})
    vi.mocked(assistantApi.run).mockResolvedValue({id:'partial',question:'热点？',status:'partial',cycle:1,events:[],error_code:'service_connection',
      detail:'连接未完成，仅显示工具确认的数值',result:{claims:[{text:'网格最高温28 °C',evidence_ids:['F:maximum']}],
        missing_conditions:[],citations:[],snapshot:snap,actions:[{type:'view_snapshot_point',snapshot_id:'s1',
          fact_id:'F:maximum',position:{x:1,y:2,z:0.5},label:'查看热点'}]}})
    await wrapper.get('textarea').setValue('热点？')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('连接未完成，仅显示工具确认的数值')
    expect(wrapper.get('.diagnostics').attributes('open')).toBeUndefined()
    expect(wrapper.get('.diagnostics').text()).toContain('service_connection')
    expect(wrapper.text()).toContain(snap.source_time)
    expect(wrapper.findAllComponents(RouterLinkStub).find(link=>typeof link.props('to')==='object')?.props('to')).toEqual({name:'assistant-field',params:{snapshotId:'s1'},
      query:{x:'1',y:'2',z:'0.5'}})
    wrapper.unmount()
  })
  it('知识提问不强制绑定现场快照',async () => {
    const wrapper=await setup()
    vi.mocked(assistantApi.submit).mockRejectedValue(new Error('test response'))
    await wrapper.get('textarea').setValue('空气温度能代表叶温吗？')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({snapshot_id:null}))
    wrapper.unmount()
  })
  it('不把缺失坐标默认为零',async () => {
    const wrapper=await setup()
    await wrapper.get('[aria-label="x 坐标"]').setValue('1')
    await wrapper.get('textarea').setValue('查询这个位置')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('请填写三个有效坐标')
    expect(assistantApi.submit).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('未配置模型时说明状态并禁用发送', async () => {
    const wrapper = await setup(false)
    await wrapper.get('[aria-label="分析依据与能力"]').trigger('click')
    expect(wrapper.text()).toContain('DeepSeek 尚未配置')
    expect(wrapper.get('button[type=submit]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('开启新对话、切回历史和重新挂载后，仍能查看原回答与固定快照',async () => {
    const wrapper=await setup()
    vi.mocked(assistantApi.submit).mockResolvedValue({id:'chat-run',question:'空气与叶温',status:'queued',cycle:0,events:[]})
    vi.mocked(assistantApi.run).mockResolvedValue({id:'chat-run',question:'空气与叶温',status:'answered',cycle:2,events:[],
      result:{claims:[{text:'温度对象应区分',evidence_ids:['K:1']}],missing_conditions:[],citations:[],snapshot:{}}})
    await wrapper.get('.bind-button').trigger('click'); await flushPromises()
    await wrapper.get('textarea').setValue('空气与叶温')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    await wrapper.get('.new-chat').trigger('click')
    expect(wrapper.find('.welcome').exists()).toBe(true)
    expect(wrapper.find('.context-strip').exists()).toBe(false)
    await wrapper.get('.chat-list button').trigger('click')
    expect(wrapper.text()).toContain('温度对象应区分')
    expect(wrapper.text()).toContain(snap.source_time)
    wrapper.unmount()
    const restored=await setup()
    expect(restored.text()).toContain('温度对象应区分')
    expect(restored.text()).toContain(snap.source_time)
    restored.unmount()
  })
  it('绑定快照后展示准确的回放帧与模型', async () => {
    const wrapper = await setup()
    await wrapper.get('.assistant-header button').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('第 8 帧')
    expect(wrapper.text()).toContain('模型 #3')
    wrapper.unmount()
  })
  it('发送使用绑定快照，最终回答保留该时刻与引用', async () => {
    const wrapper = await setup()
    vi.mocked(assistantApi.submit).mockResolvedValue({ id: 'r1', question: '来源？', status: 'queued', cycle: 0, events: [] })
    vi.mocked(assistantApi.run).mockResolvedValue({ id: 'r1', question: '来源？', status: 'answered', cycle: 2,
      events: [], result: { claims: [{ text: '来自文件回放', evidence_ids: ['F:context'] }],
        missing_conditions: [], citations: [{ id: 'F:context', text: '文件回放' }], snapshot: snap } })
    await wrapper.get('.assistant-header button').trigger('click'); await flushPromises()
    await wrapper.get('textarea').setValue('来源？')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(assistantApi.submit).toHaveBeenCalledWith(expect.objectContaining({ snapshot_id: 's1', question: '来源？' }))
    expect(wrapper.text()).toContain('来自文件回放')
    expect(wrapper.text()).toContain('F:context')
    expect(wrapper.text()).toContain(snap.source_time)
    wrapper.unmount()
  })
})
