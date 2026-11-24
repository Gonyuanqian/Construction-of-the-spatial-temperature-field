<script setup lang="ts">
import {computed,onActivated,onDeactivated,ref,toRef} from 'vue'
import {useDesignInspection} from '../composables/useDesignInspection'
import Icon from './Icon.vue'
const props=defineProps<{designId:string|null;revision:number|null;dirty:boolean}>()
const active=ref(true);onActivated(()=>active.value=true);onDeactivated(()=>active.value=false)
const task=useDesignInspection(toRef(props,'designId'),toRef(props,'revision'),toRef(props,'dirty'),active)
const {capability,inspection,history,error,starting,loading,connecting,working,stale,canStart}=task
const run=computed(()=>inspection.value?.run)
const claims=computed(()=>run.value?.result?.claims??[])
const findings=computed(()=>claims.value.filter(c=>c.text.startsWith('【检验结果】')))
const suggestions=computed(()=>claims.value.filter(c=>c.text.startsWith('【调整建议】')))
const missing=computed(()=>claims.value.filter(c=>c.text.startsWith('【待补充】')))
const clean=(text:string)=>text.replace(/^【(?:检验结果|调整建议|待补充)】\s*/,'')
const basisLabel=(basis?:string)=>basis==='general_knowledge'?'通用知识分析':basis==='inference'?'条件性推断':'方案与资料分析'
const status=computed(()=>loading.value?'读取检验记录…':starting.value?'正在提交…':connecting.value?'连接中断，正在重连':working.value?'AgriSeek 正在检验':run.value?.status==='answered'?'检验分析已完成':run.value?.status==='partial'?'已形成部分分析':run.value?.status==='cancelled'?'本次检验已取消':run.value?'本次检验未完成':inspection.value?'提交尚未确认':!props.designId?'保存方案后可检验':!capability.value?.model_configured?'AgriSeek 尚未就绪':'尚未检验')
const lastStep=computed(()=>run.value?.analysis?.steps.slice().reverse().find(s=>s.status==='running')?.summary||'正在读取方案与核验依据，请稍候。')
const failure=computed(()=>run.value&&!working.value&&!claims.value.length?(run.value.error_code==='review_stalled'?'本次候选未通过依据核验，没有发布结论。':run.value.detail||'本次没有形成可发布的检验结果，可重试。'):'')
function sourceUrl(value?:string){try{const url=new URL(value??'');return ['https:','http:'].includes(url.protocol)?url.href:null}catch{return null}}
function time(value:string){const date=new Date(value);return Number.isFinite(date.getTime())?date.toLocaleString('zh-CN',{hour12:false}):value}
</script>
<template><section class="design-panel ai-design-panel" aria-label="AgriSeek AI方案检验">
 <h3><span>AI 检验</span><small>AgriSeek</small></h3>
 <div class="inspection-body" role="region" aria-label="AI 检验回答" tabindex="0">
 <p class="inspection-status" role="status"><Icon :name="working?'rotate':'check'"/>{{status}}</p>
 <p v-if="inspection" class="inspection-binding">对应方案 v{{inspection.revision}} · {{time(inspection.created_at)}}</p>
 <p v-if="stale" class="inspection-warning" role="status">方案已修改。以下记录对应保存版本 v{{inspection?.revision}}，请保存当前修改后重新检验。</p>
 <p v-if="dirty||!designId" class="inspection-hint">请先保存当前方案，再开始 AI 检验。</p>
 <p v-if="error" class="inspection-error" role="alert">{{error}}</p>
 <p v-if="working" class="inspection-progress">{{lastStep}}</p>
 <p v-if="claims.length" class="inspection-hint">初步方案分析。通用知识可用于定性建议，具体工程条件另行核实。</p>
 <div v-if="claims.length" class="inspection-results">
  <section><h4>检验结果</h4><p v-for="(claim,i) in findings" :key="i">{{clean(claim.text)}}<small>{{basisLabel(claim.basis)}}</small><small v-if="claim.conditions?.length">适用条件：{{claim.conditions.join('；')}}</small></p><p v-if="!findings.length" class="inspection-hint">未形成可核验的方案结论。</p></section>
  <section><h4>调整建议</h4><p v-for="(claim,i) in suggestions" :key="i">{{clean(claim.text)}}<small>{{basisLabel(claim.basis)}}</small><small v-if="claim.conditions?.length">适用条件：{{claim.conditions.join('；')}}</small></p><p v-if="!suggestions.length" class="inspection-hint">本次未形成可核验的调整建议。</p></section>
  <section v-if="missing.length||run?.result?.missing_conditions.length"><h4>待补充信息</h4><p v-for="(claim,i) in missing" :key="i">{{clean(claim.text)}}</p><ul><li v-for="item in run?.result?.missing_conditions" :key="item">{{item}}</li></ul></section>
  <details><summary>查看依据</summary><p v-if="!run?.result?.citations.length">本次未引用外部资料。结论按所标注的设计事实和适用条件理解。</p><div v-for="source in run?.result?.citations" :key="source.id" class="inspection-source"><strong>{{source.source_title||source.title||source.text}}</strong><p>{{source.text}}</p><a v-if="sourceUrl(source.source_url)" :href="sourceUrl(source.source_url)!" target="_blank" rel="noopener noreferrer">查看来源</a><small>{{source.id}}</small></div></details>
 </div>
 <ol v-else-if="!working&&!failure" class="inspection-topics"><li v-for="(topic,i) in ['位置与朝向','棚体结构与覆盖','作物与种植布局','滴灌与喷灌布局']" :key="topic"><b>{{i+1}}</b>{{topic}}</li></ol>
 <p v-if="failure" class="inspection-error">{{failure}}</p>
 </div>
 <div class="inspection-footer">
 <div class="inspection-actions"><button type="button" :disabled="!canStart" @click="task.start">{{working?'检验中…':inspection&&!inspection.run&&!stale?'重试确认提交':inspection?'重新检验':'开始 AI 检验'}}</button><button v-if="working&&!starting" type="button" class="secondary" @click="task.cancel">取消</button><button v-if="(error||capability&&!capability.model_configured)&&!working" type="button" class="secondary" @click="task.load">重新连接</button></div>
 <label v-if="history.length>1" class="inspection-history">历史检验<select :value="inspection?.id" :disabled="working||loading" @change="task.select(($event.target as HTMLSelectElement).value)"><option v-for="item in history" :key="item.id" :value="item.id">v{{item.revision}} · {{time(item.created_at)}}</option></select></label>
 <p class="inspection-hint">检验使用已保存的四组设计参数。AI 分析用于方案调整，不代替工程认证；不会自动修改方案或控制设备。</p>
 </div>
 </section></template>
<style scoped>
.ai-design-panel{display:flex;flex-direction:column;min-width:0}.ai-design-panel h3{display:flex;align-items:center;gap:8px;margin:0 -13px 13px;min-height:49px;padding:11px 13px;border-bottom:var(--rule);background:color-mix(in srgb,var(--card-2) 60%,var(--card));font-size:17px}.ai-design-panel h3:before{content:'';width:3px;height:17px;background:var(--edge)}.ai-design-panel h3 small{margin-left:auto;font-size:13px;font-weight:var(--w-body);color:var(--ink-muted)}.inspection-status{display:flex;align-items:center;gap:8px;background:var(--card-2);border-radius:4px;padding:11px 10px;margin:0;font-size:14px;font-weight:var(--w-strong)}.inspection-status :deep(.icon){--icon-size:18px}.inspection-binding{font-size:11px;color:var(--ink-muted);margin:8px 0}.inspection-hint,.inspection-progress{font-size:12px;color:var(--ink-muted);line-height:1.7;margin:10px 0 0}.inspection-warning,.inspection-error{font-size:12px;line-height:1.7;background:var(--training-warning-soft);color:var(--training-warning);padding:8px;border-radius:4px;margin:9px 0}.inspection-results{max-height:650px;overflow-y:auto;scrollbar-width:thin;padding-right:4px;margin-top:12px}.inspection-results section+section{border-top:var(--rule);margin-top:14px;padding-top:12px}.inspection-results h4{color:var(--edge);font-size:14px;margin:0 0 8px}.inspection-results p,.inspection-results li{font-size:13px;line-height:1.8;margin:8px 0;white-space:pre-wrap;overflow-wrap:anywhere}.inspection-results small{display:block;color:var(--ink-muted);font-size:11px;line-height:1.7;margin-top:4px}.inspection-results ul{padding-left:18px}.inspection-results details{font-size:12px;color:var(--ink-muted);border-top:var(--rule);margin-top:12px;padding-top:10px}.inspection-source{padding:8px 0;border-bottom:var(--rule)}.inspection-source strong{font-size:12px;color:var(--ink)}.inspection-source a{color:var(--edge)}.inspection-topics{list-style:none;padding:0;margin:6px 0 14px;flex:1}.inspection-topics li{display:flex;align-items:center;gap:9px;padding:18px 0;border-bottom:var(--rule);font-size:14px}.inspection-topics b{display:grid;place-content:center;width:23px;height:23px;border-radius:50%;background:var(--card-2);font-size:12px}.inspection-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:16px}.inspection-actions button{flex:1;min-height:40px;padding:7px 10px;font:inherit;font-size:13px;border:1px solid var(--interact);border-radius:var(--radius);background:var(--interact);color:var(--on-face);cursor:pointer}.inspection-actions button:disabled{opacity:.5;cursor:default}.inspection-actions button.secondary{background:var(--card);color:var(--ink-muted);border-color:var(--steel)}.inspection-actions button:focus-visible,.inspection-history select:focus-visible{outline:2px solid var(--edge);outline-offset:2px}.inspection-history{display:grid;gap:5px;font-size:12px;color:var(--ink-muted);margin-top:13px}.inspection-history select{width:100%;min-width:0;padding:7px;background:var(--card-2);border:1px solid var(--steel);border-radius:4px;color:var(--ink);font:inherit}@media(max-width:850px){.inspection-results{max-height:none}}
/* Desktop height follows the adjacent preview, never the response length. */
.ai-design-panel{contain:size;min-height:0;overflow:hidden}
.ai-design-panel>h3,.inspection-footer{flex:none}
.inspection-body{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior-y:contain;scrollbar-gutter:stable;scrollbar-width:thin;padding-right:4px;overflow-wrap:anywhere}
.inspection-body:focus-visible{outline:2px solid var(--edge);outline-offset:-2px}
.inspection-results{max-height:none;overflow:visible;padding-right:0}
/* In the stacked layout the card has its own fixed height. */
@media(max-width:1190px){.ai-design-panel{contain:none;height:640px}}
</style>
