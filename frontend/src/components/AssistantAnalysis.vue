<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { AnalysisRecord } from '../api/assistant'

const props=defineProps<{analysis:AnalysisRecord; status:string}>()
const active=computed(()=>['queued','running'].includes(props.status))
const expanded=ref(active.value)
const now=ref(Date.now())
let timer:ReturnType<typeof setInterval>|undefined
watch(active,(value)=>{
  if(timer) {clearInterval(timer);timer=undefined}
  expanded.value=value
  if(value) {now.value=Date.now();timer=setInterval(()=>{now.value=Date.now()},1000)}
},{immediate:true})
onBeforeUnmount(()=>clearInterval(timer))
const seconds=computed(()=>{
  const a=props.analysis
  return Math.max(0,Math.round((active.value && a.started_at ? now.value-a.started_at*1000 : a.elapsed_ms)/1000))
})
const label=computed(()=>active.value ? (props.status==='queued' ? '等待分析' : '正在分析')
  : props.status==='answered' ? '分析完成' : props.status==='cancelled' ? '分析已取消'
    : props.status==='interrupted' ? '分析已中断' : props.status==='needs_clarification' ? '需要补充信息'
      : props.status==='needs_snapshot' ? '等待绑定快照' : props.status==='unsupported' ? '能力范围说明' : '分析记录')
const visibleNodes=computed(()=>props.analysis.public_nodes ?? props.analysis.steps)
const narrative=computed(()=>{
  const nodes=visibleNodes.value
  return nodes.filter((n,i)=>(n.id!=='outcome' || props.status!=='answered') &&
    (!n.id.startsWith('review:') || !nodes.slice(i+1).some(next=>next.id.startsWith('review:')))).map(n=>({
      id:n.id, text:[n.id==='goal' && n.summary==='本轮回答关注以下要点。' ? n.title : n.summary,
        ...(!['goal','review','outcome'].includes(n.id) && !n.id.startsWith('review:')
          ? n.items.map(item=>item.text) : [])].filter(Boolean).join(' ')
    }))
})
</script>

<template>
  <details class="analysis-record" :open="expanded" @toggle="expanded=($event.target as HTMLDetailsElement).open">
    <summary><span class="analysis-icon" :class="{active}">✧</span><span>分析摘要 · {{ label }}</span><span class="duration">用时 {{ seconds }} 秒</span><span class="chevron">⌄</span></summary>
    <div class="analysis-body">
      <p v-if="analysis.public_nodes && !analysis.public_nodes.length" class="record-note">正在整理本轮任务摘要…</p>
      <div class="narrative">
        <p v-for="item in narrative" :key="item.id">{{ item.text }}</p>
      </div>
    </div>
  </details>
</template>

<style scoped>
.analysis-record {margin:0 8px 22px; color:#687386; font-size:13px; line-height:1.8;}
summary {display:flex;align-items:center;gap:8px;cursor:pointer;width:fit-content;color:#727e92;list-style:none;}
summary::-webkit-details-marker {display:none;}
summary:focus-visible {outline:2px solid #4d6bfe;outline-offset:4px;border-radius:4px;}
.analysis-icon {color:#4d6bfe;font-size:21px;line-height:1;}
.analysis-icon.active {animation:pulse 1.6s ease-in-out infinite;}
.duration {font-size:12px;color:#a0a8b5;}
.chevron {margin-left:2px;transition:transform .15s;}
details[open] .chevron {transform:rotate(180deg);}
.analysis-body {border-left:2px solid #e9edf5;margin:14px 0 0 9px;padding:0 0 2px 20px;}
.record-note {font-size:11px;color:#a0a8b5;margin:0 0 14px;}
.narrative p {margin:0 0 12px;overflow-wrap:anywhere;}
p {margin:5px 0;} ul {padding-left:17px;margin:5px 0 0;} ul li {margin-bottom:5px;overflow-wrap:anywhere;}
small {display:block;color:#a7afbd;font-size:10px;overflow-wrap:anywhere;}
@keyframes pulse {50% {opacity:.35;}}
@media(prefers-reduced-motion:reduce) {.analysis-icon.active {animation:none;}}
</style>
