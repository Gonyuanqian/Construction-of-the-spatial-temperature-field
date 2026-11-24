// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AssistantAnalysis from './AssistantAnalysis.vue'
import type { AnalysisRecord } from '../api/assistant'

function record(): AnalysisRecord {
  return {version:1,kind:'execution_summary',started_at:100,finished_at:107,elapsed_ms:7000,
    steps:[{id:'intent',title:'需求解析',status:'completed',summary:'查询固定快照温度。',items:[]},
      {id:'data',title:'数据获取',status:'completed',summary:'已读取回放。',items:[{text:'最高温 28.00 °C。',tool:'find_temperature_extrema',evidence_ids:['F:maximum']}]},
      {id:'comparison',title:'对比分析',status:'blocked',summary:'模型连接中断，未完成复核。',items:[]},
      {id:'conclusion',title:'得出结论',status:'blocked',summary:'仅保留工具确认的事实。',items:[]}]}
}

describe('回答前的分析过程',()=>{
  it('历史重复审核合并为一段摘要，不展示工程编号和步骤编号',()=>{
    const value=record();value.public_nodes=[
      {id:'goal',title:'了解助手是否只支持切面。',summary:'本轮回答关注以下要点。',status:'completed',items:[]},
      {id:'review:1',title:'需要修订',summary:'第一次检查。',status:'blocked',items:[{text:'工程检查',evidence_ids:['F:sensor:1']}]},
      {id:'review:2',title:'需要修订',summary:'根据已知能力说明范围。',status:'blocked',items:[]}]
    const wrapper=mount(AssistantAnalysis,{props:{analysis:value,status:'partial'}})
    expect(wrapper.findAll('.narrative > p')).toHaveLength(2)
    expect(wrapper.text()).toContain('了解助手是否只支持切面。')
    expect(wrapper.text()).toContain('根据已知能力说明范围。')
    expect(wrapper.text()).not.toContain('第一次检查')
    expect(wrapper.text()).not.toContain('F:sensor:1')
    expect(wrapper.text()).not.toContain('工程检查')
    expect(wrapper.find('ol').exists()).toBe(false)
    wrapper.unmount()
  })
  it('动态摘要只渲染本轮存在的节点，不填充固定四步',()=>{
    const value=record();value.public_nodes=[{id:'goal',title:'解释温度如何影响生长',summary:'从生理过程与条件差异展开。',status:'completed',items:[]},
      {id:'review:1',title:'候选检查通过',summary:'已检查通用知识与适用范围。',status:'completed',items:[]}]
    const wrapper=mount(AssistantAnalysis,{props:{analysis:value,status:'answered'}})
    expect(wrapper.find('ol').exists()).toBe(false)
    expect(wrapper.findAll('.narrative > p')).toHaveLength(2)
    expect(wrapper.text()).toContain('从生理过程与条件差异展开。')
    expect(wrapper.text()).not.toContain('需求解析')
    expect(wrapper.text()).not.toContain('数据获取')
    expect(wrapper.get('summary').text()).toContain('分析摘要')
    wrapper.unmount()
  })
  it('尚无节点时显示等待摘要，不虚构取数和比对步骤',()=>{
    const value=record();value.public_nodes=[]
    const wrapper=mount(AssistantAnalysis,{props:{analysis:value,status:'running'}})
    expect(wrapper.findAll('ol > li')).toHaveLength(0)
    expect(wrapper.text()).toContain('正在整理本轮任务摘要')
    wrapper.unmount()
  })
  it('运行中展开，完成后折叠，保留真实记录与耗时',async()=>{
    const wrapper=mount(AssistantAnalysis,{props:{analysis:record(),status:'running'}})
    expect(wrapper.get('details').attributes('open')).toBeDefined()
    await wrapper.setProps({status:'partial'})
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('summary').text()).toContain('用时 7 秒')
    expect(wrapper.text()).toContain('28.00 °C')
    expect(wrapper.text()).not.toContain('F:maximum')
    expect(wrapper.text()).toContain('未完成复核')
    expect(wrapper.findAll('.narrative > p')).toHaveLength(4)
    wrapper.unmount()
  })
  it('取消后显示中止状态，并将文本作为纯文本呈现',()=>{
    const value=record(); value.steps[0]!.summary='<img src=x onerror=alert(1)>'
    const wrapper=mount(AssistantAnalysis,{props:{analysis:value,status:'cancelled'}})
    expect(wrapper.get('summary').text()).toContain('分析已取消')
    expect(wrapper.find('img').exists()).toBe(false)
    wrapper.unmount()
  })
})
