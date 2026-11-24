<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {routeLocationKey} from 'vue-router'
import AssistantAnalysis from '../components/AssistantAnalysis.vue'
import AssistantActivity from '../components/AssistantActivity.vue'
import { ConversationSession, type ConnectionState } from '../assistant/session'
import { useAuth } from '../composables/useAuth'
import type { ConversationTurn } from '../assistant/conversation'
import { assistantApi, type AnalysisSnapshot, type AssistantCapabilities, type AssistantRun, type FieldAction, type FieldRegion } from '../api/assistant'

const capabilities = ref<AssistantCapabilities | null>(null)
const snapshot = ref<AnalysisSnapshot | null>(null)
const question = ref('')
const questionInput = ref<HTMLTextAreaElement | null>(null)
watch(question, () => {
  const input = questionInput.value
  if (!input) return
  input.style.height = 'auto'
  input.style.height = `${Math.min(120, Math.max(28, input.scrollHeight))}px`
}, { flush: 'post' })
const crop = ref('')
const stage = ref('')
const webSearchEnabled = ref(true)
const position = ref({ x: '', y: '', z: '' })
const selectionMode = ref<'point'|'region'|'comparison'>('point')
const regionKeys = ['x_min','x_max','y_min','y_max','z_min','z_max'] as const
const emptyRegion = () => Object.fromEntries(regionKeys.map(k => [k,''])) as Record<keyof FieldRegion,string>
const regions = ref([emptyRegion(),emptyRegion()])
const messages = ref<AssistantRun[]>([])
const turns = ref<readonly ConversationTurn[]>([])
const connection = ref<ConnectionState>('idle')
const error = ref('')
const busy = ref(false)
const capturing = ref(false)
const historyLoading = ref(false)
const history = ref<HTMLElement | null>(null)
const sidebarOpen = ref(window.innerWidth > 600)
const infoOpen = ref(false)
const chatId = ref<string>(crypto.randomUUID())
const chats = ref<{id:string;title:string;runs:AssistantRun[];snapshot:AnalysisSnapshot|null;server?:boolean}[]>([])
const chatMenu = ref<string|null>(null)
const chatDialog = ref<{id:string;mode:'rename'|'delete';title:string}|null>(null)
const chatName = ref('')
const managingChat = ref(false)
const chatDialogError = ref('')
function manageChat(id:string,mode:'rename'|'delete') {
  const chat=chats.value.find(c=>c.id===id)
  if(!chat)return
  chatMenu.value=null;chatDialog.value={id,mode,title:chat.title};chatName.value=chat.title;chatDialogError.value=''
  void nextTick(()=>document.getElementById('chat-name')?.focus())
}
async function confirmChatManagement() {
  const dialog=chatDialog.value
  if(!dialog || managingChat.value)return
  const chat=chats.value.find(c=>c.id===dialog.id)
  if(!chat)return
  const title=chatName.value.trim()
  if(dialog.mode==='rename' && (!title || title.length>80)) {chatDialogError.value='请输入1至80个字符的名称。';return}
  managingChat.value=true;chatDialogError.value=''
  try {
    if(dialog.mode==='rename') {
      const renamed=chat.server ? await assistantApi.renameConversation(chat.id,title) : {title}
      chat.title=renamed.title
    } else {
      if(chat.server)await assistantApi.deleteConversation(chat.id)
      if(chat.id===chatId.value) {
        session.close();messages.value=[];turns.value=[];snapshot.value=null;activeId=null;busy.value=false
        chatId.value=crypto.randomUUID();resetConditions()
      }
      chats.value=chats.value.filter(c=>c.id!==chat.id)
    }
    persistChats();chatDialog.value=null
  } catch(e) {chatDialogError.value=e instanceof Error?e.message:'操作未完成，请重试。'}
  finally {managingChat.value=false}
}
const auth=useAuth()
const route=inject(routeLocationKey,null)
const queryText=(key:string)=>typeof route?.query[key]==='string'?route.query[key] as string:''
const linkedEntry=()=>!!(queryText('conversation')||queryText('crop'))
let initialized=false
const historyKey=`tfield-assistant-chats-v3:${auth.user.value?.role ?? 'NONE'}:${auth.user.value?.id ?? 'anonymous'}`
const legacyHistoryKeys=auth.isAdmin.value?[`tfield-assistant-chats-v2:${auth.user.value?.id}`,'tfield-assistant-chats-v1']:[]
function inspectionPreview(runs:AssistantRun[],context:AnalysisSnapshot|null) {
  if(runs.length!==1||runs[0]!.parent_run_id)return false
  const run=runs[0]!
  return run.conversation_origin==='greenhouse_design_inspection'||
    (run.result?.snapshot?.data_mode==='greenhouse_design'||context?.data_mode==='greenhouse_design')&&
    run.question.startsWith('请检验这份已保存的人参温室设计方案')
}
function staleInspectionCache(chat:typeof chats.value[number]) {
  if(inspectionPreview(chat.runs,chat.snapshot))return true
  if(chat.runs.some(run=>run.parent_run_id))return false
  // Older server summaries may have no loaded snapshot or run origin yet.
  return !!chat.server&&chat.runs.length<=1&&chat.title.startsWith('请检验这份已保存的人参温室设计方案')
}
function persistChats() {
  try { localStorage.setItem(historyKey,JSON.stringify({active:chatId.value,chats:chats.value})) }
  catch { error.value='本机对话记录未能保存，当前回答仍可查看。' }
}
function saveChat() {
  if (!messages.value.length) return
  if(inspectionPreview(messages.value,snapshot.value)) {
    chats.value=chats.value.filter(chat=>chat.id!==chatId.value);persistChats();return
  }
  const title=messages.value.length>1&&inspectionPreview([messages.value[0]!],snapshot.value)
    ?messages.value[1]!.question:messages.value[0]!.question
  const value={id:chatId.value,title:chats.value.find(c=>c.id===chatId.value)?.title || title,runs:[...messages.value],snapshot:snapshot.value,
    server:messages.value.some(r=>r.conversation_id===chatId.value)}
  const index=chats.value.findIndex(c=>c.id===chatId.value)
  if(index<0) chats.value.unshift(value); else chats.value[index]=value
  persistChats()
}
function resetConditions() {
  question.value=''; crop.value=''; stage.value=''; webSearchEnabled.value=true; position.value={x:'',y:'',z:''}
  selectionMode.value='point'; regions.value=[emptyRegion(),emptyRegion()]; pending=null; error.value=''
}
function newChat() {
  if(busy.value || capturing.value || historyLoading.value) return
  session.close(); saveChat(); chatId.value=crypto.randomUUID(); messages.value=[]; turns.value=[]; snapshot.value=null; resetConditions()
  persistChats()
}
function restoreConditions(run?:AssistantRun) {
  resetConditions()
  if(!run) return
  webSearchEnabled.value=run.web_search_enabled!==false
  crop.value=run.crop ?? run.resolved_context?.crop ?? ''; stage.value=run.stage ?? run.resolved_context?.stage ?? ''
  const selection=run.resolved_context?.selection || run
  if(selection.position) position.value={x:String(selection.position.x),y:String(selection.position.y),z:String(selection.position.z)}
  const boxes=selection.regions ? [selection.regions.first,selection.regions.second] : selection.region ? [selection.region] : []
  if(boxes.length) {
    selectionMode.value=boxes.length===2 ? 'comparison' : 'region'
    boxes.forEach((box,index)=>regionKeys.forEach(key=>{regions.value[index]![key]=String(box[key])}))
  }
}
async function loadServerChat(id:string) {
  const out=await assistantApi.conversation(id)
  if(disposed || chatId.value!==id) return
  const chat=chats.value.find(c=>c.id===id)
  if(chat)chat.title=out.title
  session.open(id,out)
  restoreConditions(out.runs.at(-1))
  const last=out.runs.at(-1)
  const snapshotId=last?.resolved_context?.snapshot_id || last?.snapshot_id
  if(!snapshot.value && snapshotId) {
    const value=await assistantApi.snapshotInfo(snapshotId)
    if(disposed || chatId.value!==id)return
    snapshot.value=value
  }
  saveChat()
}
async function openLinkedEntry() {
  saveChat();session.close();messages.value=[];turns.value=[];snapshot.value=null;busy.value=false;activeId=null;resetConditions()
  const id=queryText('conversation')
  chatId.value=id||crypto.randomUUID()
  if(id) {
    historyLoading.value=true
    try {await loadServerChat(id)}catch(e){if(!disposed&&chatId.value===id){failure(e);if(!messages.value.length)chatId.value=crypto.randomUUID()}}
    finally {historyLoading.value=false}
  } else {crop.value=queryText('crop').slice(0,80);stage.value=queryText('stage').slice(0,80);persistChats()}
}
watch(()=>route?.fullPath,()=>{if(initialized && linkedEntry())void openLinkedEntry()})
async function selectChat(id:string) {
  if(busy.value || capturing.value || historyLoading.value) return
  saveChat(); const chat=chats.value.find(c=>c.id===id)
  if(chat) {
    session.close(); chatId.value=id; messages.value=[...chat.runs]; turns.value=[]; snapshot.value=chat.snapshot; restoreConditions(chat.runs.at(-1))
    if(chat.server) {
      historyLoading.value=true
      try {await loadServerChat(id)} catch(e) {failure(e)} finally {historyLoading.value=false}
    }
    const running=messages.value.find(r=>['queued','running'].includes(r.status))
    if(running && !chat.server) session.follow(id,messages.value)
    void scroll()
  }
  persistChats()
}
function onQuestionKey(event:KeyboardEvent) {
  if(event.key==='Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); void send()}
}
let disposed = false
let activeId: string | null = null
const session = new ConversationSession(assistantApi,(nodes,state)=>{
  if(disposed) return
  const pane=history.value
  const followAnswer=!pane || pane.scrollHeight-pane.scrollTop-pane.clientHeight<64
  const previousActive=activeId
  turns.value=nodes;messages.value=nodes.map(node=>node.run);connection.value=state
  const last=messages.value.at(-1)
  activeId=last && ['queued','running'].includes(last.status) ? last.id : null
  busy.value=!!activeId
  if(previousActive && !activeId) {restoreConditions(last);if(followAnswer)void scroll()}
  else if(activeId && followAnswer)void nextTick(()=>history.value?.scrollTo({top:history.value.scrollHeight,behavior:'auto'}))
  saveChat()
})
let pending: Parameters<typeof assistantApi.submit>[0] | null = null
const ready = computed(() => capabilities.value?.model_configured && !busy.value && !capturing.value && !historyLoading.value)
const suggestions = ['当前有效网格最热的位置在哪里？', '查询这个位置的温度', '空气温度能代表叶片温度吗？']
function viewLink(action: FieldAction) {
  return { name: 'assistant-field', params: { snapshotId: action.snapshot_id }, query: {
    x: String(action.position.x), y: String(action.position.y), z: String(action.position.z) } }
}
function sourceLink(value?: string) {
  try { const url = new URL(value || ''); return url.protocol === 'https:' ? url.href : undefined }
  catch { return undefined }
}

function failure(e: unknown) { error.value = e instanceof Error ? e.message : '暂时无法连接助手服务' }
async function refresh() {
  if (busy.value) return
  capturing.value = true; error.value = ''
  try {
    const data = await assistantApi.snapshot()
    if (!disposed) { snapshot.value = data; pending = null; saveChat() }
  } catch (e) { if (!disposed) failure(e) }
  finally { capturing.value = false }
}
async function scroll() { await nextTick(); history.value?.scrollTo({ top: history.value.scrollHeight, behavior: 'smooth' }) }
function update(run: AssistantRun) {
  session.accept(run)
}
async function send() {
  if (!ready.value || !question.value.trim()) return
  busy.value = true; error.value = ''
  const filled = Object.values(position.value).some(v => String(v).trim() !== '')
  const numbers = Object.fromEntries(Object.entries(position.value).map(([k,v]) => [k, Number(v)])) as {x:number;y:number;z:number}
  if (selectionMode.value === 'point' && filled && (Object.values(position.value).some(v => String(v).trim() === '') || Object.values(numbers).some(v => !Number.isFinite(v)))) {
    error.value = '请填写三个有效坐标，或全部留空。'; busy.value = false; return
  }
  let selectedRegion: FieldRegion | null = null
  let selectedRegions: {first:FieldRegion;second:FieldRegion} | null = null
  if (selectionMode.value !== 'point') {
    const parsedRegions: FieldRegion[] = []
    for (const raw of regions.value.slice(0,selectionMode.value === 'comparison' ? 2 : 1)) {
      if (Object.values(raw).some(v => String(v).trim() === '' || !Number.isFinite(Number(v)))) {
        error.value = '请填写区域的全部坐标上下限。'; busy.value = false; return
      }
      const parsedRegion = Object.fromEntries(Object.entries(raw).map(([k,v]) => [k,Number(v)])) as unknown as FieldRegion
      if (parsedRegion.x_min > parsedRegion.x_max || parsedRegion.y_min > parsedRegion.y_max || parsedRegion.z_min > parsedRegion.z_max) {
        error.value = '区域下限不能大于上限。'; busy.value = false; return
      }
      parsedRegions.push(parsedRegion)
    }
    if (selectionMode.value === 'region') selectedRegion = parsedRegions[0]!
    else selectedRegions = {first:parsedRegions[0]!,second:parsedRegions[1]!}
  }
  const input = { snapshot_id: snapshot.value?.snapshot_id || null, question: question.value.trim(),
    web_search_enabled:webSearchEnabled.value,
    conversation_id:chatId.value,parent_run_id:messages.value.at(-1)?.id || null,
    legacy_run_ids:messages.value.length && messages.value.every(r=>!r.conversation_id)
      ? messages.value.slice(-20).map(r=>r.id) : [],
    crop: crop.value.trim() || null, stage: stage.value.trim() || null,
    position: selectionMode.value === 'point' && filled ? numbers : null, region:selectedRegion, regions:selectedRegions }
  if (!pending || pending.snapshot_id !== input.snapshot_id || pending.question !== input.question ||
      pending.conversation_id!==input.conversation_id || pending.parent_run_id!==input.parent_run_id ||
      pending.crop !== input.crop || pending.stage !== input.stage || pending.web_search_enabled!==input.web_search_enabled || JSON.stringify([pending.position,pending.region,pending.regions]) !== JSON.stringify([input.position,input.region,input.regions])) pending = { ...input, request_key: crypto.randomUUID() }
  try {
    const run = await assistantApi.submit(pending)
    if (disposed) return
    activeId = run.id; question.value = ''; pending = null
    session.follow(chatId.value,[...messages.value,run])
    void scroll()
  } catch (e) { if (!disposed) { failure(e); busy.value = false } }
}
async function cancel() {
  if (!activeId) return
  try {
    const run = await assistantApi.cancel(activeId)
    if (!disposed) { session.close(); update(run); busy.value = false; activeId = null }
  } catch (e) { failure(e) }
}
onMounted(async () => {
  historyLoading.value=true
  try {
    const saved=JSON.parse(localStorage.getItem(historyKey)||legacyHistoryKeys.map(key=>localStorage.getItem(key)).find(Boolean)||'null')
    if(saved && Array.isArray(saved.chats)) {
      chats.value=saved.chats.filter((c: typeof chats.value[number])=> typeof c?.id==='string' && typeof c.title==='string'
        && Array.isArray(c.runs) && c.runs.every(r=>typeof r?.id==='string' && typeof r.question==='string' && Array.isArray(r.events))
        && !inspectionPreview(c.runs,c.snapshot))
      const chat=chats.value.find(c=>c.id===saved.active)
      if(chat && !linkedEntry()) {
        chatId.value=chat.id; messages.value=[...chat.runs]; snapshot.value=chat.snapshot
        restoreConditions(chat.runs.at(-1))
      }
    }
  } catch { error.value='本机对话记录暂时无法读取，可以开启新对话。' }
  try { const result = await assistantApi.capabilities(); if (!disposed) capabilities.value = result }
  catch (e) { if (!disposed) failure(e) }
  try {
    const summaries=await assistantApi.conversations()
    if(!disposed) {
      const known=new Set(summaries.map(c=>c.id))
      const missing=new Set<string>()
      await Promise.all(chats.value.filter(c=>c.server&&!known.has(c.id)).map(async c=>{
        try {await assistantApi.conversation(c.id)}
        catch(e) {if((e as {status?:number})?.status===404)missing.add(c.id)}
      }))
      const hadCachedActive=chats.value.some(c=>c.id===chatId.value)
      chats.value=[...summaries.map(c=>({id:c.id,title:c.title,runs:chats.value.find(old=>old.id===c.id)?.runs||[],
        snapshot:chats.value.find(old=>old.id===c.id)?.snapshot||null,server:true})),...chats.value.filter(c=>!missing.has(c.id)&&!known.has(c.id)&&!staleInspectionCache(c))]
      if(!linkedEntry() && known.has(chatId.value)) await loadServerChat(chatId.value)
      else if(!linkedEntry()&&hadCachedActive&&!chats.value.some(c=>c.id===chatId.value)) {
        session.close();chatId.value=crypto.randomUUID();messages.value=[];turns.value=[];snapshot.value=null;resetConditions()
      }
      persistChats()
    }
  } catch(e) {if(!disposed) failure(e)}
  finally {historyLoading.value=false}
  if(!disposed && linkedEntry())await openLinkedEntry()
  initialized=true
  if(!disposed) {
    const running=messages.value.find(r=>['queued','running'].includes(r.status))
    if(running && !turns.value.length) session.follow(chatId.value,messages.value)
  }
})
onBeforeUnmount(() => {
  disposed = true; session.close()
})
</script>

<template>
  <div class="assistant-workspace" :class="{ 'sidebar-closed': !sidebarOpen }">
    <aside class="chat-sidebar" aria-label="对话导航" v-show="sidebarOpen">
      <div class="brand-row"><span class="brand-mark">✦</span><strong>AgriSeek</strong><button class="icon-button" aria-label="收起侧栏" @click="sidebarOpen=false">◧</button></div>
      <button class="new-chat" :disabled="busy || capturing || historyLoading" @click="newChat"><span>＋</span> 开启新对话</button>

      <div class="chat-list"><p class="section-label">历史对话</p><p v-if="!chats.length" class="empty-history">你的温度探索，从这里开始</p>
        <div v-for="chat in chats" :key="chat.id" class="chat-row" :class="{selected:chat.id===chatId}">
          <button class="chat-title" :class="{selected:chat.id===chatId}" :title="chat.title" :disabled="busy || capturing || historyLoading || managingChat" @click="chatMenu=null;selectChat(chat.id)">{{ chat.title }}</button>
          <button class="chat-more" :aria-label="`管理对话：${chat.title}`" :aria-expanded="chatMenu===chat.id" :disabled="busy || capturing || historyLoading || managingChat" @click="chatMenu=chatMenu===chat.id?null:chat.id">⋯</button>
          <div v-if="chatMenu===chat.id" class="chat-menu" @keydown.esc="chatMenu=null">
            <button @click="manageChat(chat.id,'rename')">改名</button><button class="delete-chat" @click="manageChat(chat.id,'delete')">删除</button>
          </div>
        </div>
      </div>
      <div class="sidebar-footer"><span class="avatar">A</span><div><strong>AgriSeek</strong><small>会话已接入服务端上下文</small></div></div>
    </aside>
    <section class="chat-main" :class="{ 'has-messages':messages.length }">
      <header class="assistant-header"><div class="header-title"><button v-if="!sidebarOpen" class="icon-button" aria-label="展开侧栏" @click="sidebarOpen=true">☰</button><span>AgriSeek</span><span class="beta">农业专属</span></div>
        <div class="header-actions"><button class="bind-button" :disabled="busy || capturing || historyLoading" @click="refresh">{{ capturing ? '正在绑定…' : historyLoading ? '读取会话…' : snapshot ? '重新绑定当前帧' : '绑定当前帧' }}</button><button class="icon-button" aria-label="分析依据与能力" :aria-expanded="infoOpen" @click="infoOpen=!infoOpen">ⓘ</button></div>
      </header>
      <div v-if="snapshot" class="context-strip"><span class="status-dot"></span><span>{{ snapshot.data_mode==='greenhouse_design' ? `温室设计快照 · v${snapshot.design_revision??'未知'}` : snapshot.data_mode==='external_weather' ? '气象构场快照' : `文件回放 · 第 ${snapshot.frame_index} 帧` }}</span><strong>{{ snapshot.source_time }}</strong><span>{{ snapshot.data_mode==='greenhouse_design' ? '设计参数与几何事实' : snapshot.model_id===null ? '棚体原型模型' : `模型 #${snapshot.model_id}` }} · 分析时刻已固定</span></div>
      <aside v-if="infoOpen" class="info-panel"><h2>分析依据与能力</h2><p>DeepSeek {{ capabilities?.model_configured ? '已配置' : '尚未配置' }}</p><p>农业知识库{{ capabilities?.knowledge_configured ? '已配置，查询时核验发布资料' : '尚未配置审核资料' }}</p><p>正常回答至少复核两轮，最多六轮。缺少证据时会保留判断。</p><p v-for="item in capabilities?.limitations" :key="item">{{ item }}</p><p>联网检索{{ capabilities?.web_search_configured ? '可用：支持机构与论文来源检索、原文读取和引用复核' : '暂不可用' }}。</p><p>测点均温与棚体空间均温是不同统计口径。</p><div v-if="snapshot"><p v-for="fact in snapshot.facts.filter(f=>f.value!==undefined)" :key="fact.id">{{ fact.text }} <strong>{{ fact.value?.toFixed(2) }} {{ fact.unit }}</strong></p></div></aside>
      <div class="conversation">
        <div ref="history" class="messages" aria-live="polite">
        <article v-for="run in messages" :key="run.id" class="exchange">
          <p class="user-question">{{ run.question }}</p>
          <AssistantAnalysis v-if="run.analysis?.version === 1" :analysis="run.analysis" :status="run.status" />
          <div v-if="run.answer_stream?.text && !run.result" class="answer answer-preview">
            <small class="muted">{{ ['queued','running'].includes(run.status) ? '正在生成 · 内容待核验' : '生成未完成 · 以下为未核验草稿' }}</small>
            <p style="white-space:pre-wrap">{{ run.answer_stream.text }}</p>
          </div>
          <div v-if="run.result" class="answer">
            <p v-if="run.detail" class="muted" role="status">{{ run.detail }}</p>
            <p v-for="(claim, i) in run.result.claims" :key="i">{{ claim.text }}</p>
            <p v-for="item in run.result.missing_conditions" :key="item" class="muted">需要补充：{{ item }}</p>
            <div class="suggestions"><RouterLink v-for="action in run.result.actions" :key="action.fact_id" :to="viewLink(action)">{{ action.label }}</RouterLink></div>
            <details><summary>查看依据与计算口径</summary>
              <p v-if="run.result.snapshot.source_time" class="muted">依据：{{ run.result.snapshot.source_time }} · {{ run.result.snapshot.data_mode==='greenhouse_design' ? `温室设计快照 · v${run.result.snapshot.design_revision??'未知'}` : run.result.snapshot.data_mode==='external_weather' ? '气象构场快照' : `回放第 ${run.result.snapshot.frame_index} 帧` }}</p>
              <template v-for="(claim, i) in run.result.claims" :key="i">
                <div v-if="claim.basis || claim.conditions?.length || claim.evidence_ids.length" class="citation">
                  <strong>第 {{ i + 1 }} 段</strong>
                  <p v-if="claim.basis">{{ claim.basis==='inference' ? '条件性推断' : claim.basis==='general_knowledge' ? '通用知识' : '资料依据' }}</p>
                  <p v-if="claim.conditions?.length">适用条件：{{ claim.conditions.join('；') }}</p>
                  <small v-if="claim.evidence_ids.length">{{ claim.evidence_ids.join(' · ') }}</small>
                </div>
              </template>
              <div v-for="item in run.result.citations" :key="item.id" class="citation">
                <strong>{{ item.id }} · {{ item.title || item.text }}</strong>
                <p v-if="item.value !== undefined">{{ item.value }} {{ item.unit }}</p>
                <p v-if="item.position">坐标：({{ item.position.x }}, {{ item.position.y }}, {{ item.position.z }}) m</p>
                <p v-if="item.title">{{ item.text }}</p><small>{{ item.locator || item.statistic_definition }}</small>
                <p v-if="item.source_title"><a v-if="sourceLink(item.source_url)" :href="sourceLink(item.source_url)" target="_blank" rel="noopener noreferrer">{{ item.source_title }}</a><span v-else>{{ item.source_title }}</span></p>
                <small v-if="item.origin==='web_original'">联网原文 · {{ item.retrieved_at?.slice(0,10) }} 读取 · 本轮引用已复核，未入本地知识库</small>
                <small v-if="item.doi">DOI：{{ item.doi }}</small>
              </div>
            </details>
          </div>
          <p v-else-if="['queued', 'running'].includes(run.status)" class="muted">{{ run.answer_stream?.text ? '正在继续生成或核验回答…' : '正在组织回答…' }}</p>
          <p v-else class="muted">{{ run.detail || '本次问答未生成可发布答案。' }}</p>
          <details v-if="run.error_code || turns.find(t=>t.run.id===run.id)?.activities.length" class="diagnostics">
            <summary>查看执行诊断</summary>
            <AssistantActivity :activities="turns.find(t=>t.run.id===run.id)?.activities || []" :running="['queued','running'].includes(run.status)" />
            <small v-if="run.error_code" class="muted">错误编号：{{ run.error_code }}</small>
          </details>
        </article>

        </div>
        <div class="compose-area">
          <div v-if="!messages.length" class="welcome"><div class="welcome-heading"><span class="welcome-mark">✦</span><h1>你好，我是 AgriSeek</h1></div><p>从棚内的一处温度，到作物生长的每一份关切。</p></div>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <p v-if="busy && connection==='reconnecting'" class="muted" role="status">正在重新连接，分析任务继续执行。</p>
          <form class="composer" @submit.prevent="send">
            <label class="question-label" for="assistant-question">你的问题</label>
            <textarea id="assistant-question" ref="questionInput" v-model="question" maxlength="2000" rows="1" placeholder="向 AgriSeek 提问，探索温度与生长的关系…" :disabled="busy || historyLoading" @keydown="onQuestionKey" />
            <details class="conditions"><summary>补充作物与位置条件<span v-if="crop || stage || Object.values(position).some(v=>v!=='') || selectionMode!=='point'"> · 已设置</span></summary>
        <div class="crop-fields"><label>作物<input v-model="crop" maxlength="80" placeholder="可选，例如番茄" :disabled="busy || historyLoading"></label>
          <label>生育期<input v-model="stage" maxlength="80" placeholder="未知可留空" :disabled="busy || historyLoading"></label></div>
        <details class="selection"><summary>位置或区域条件（选填）</summary>
          <label>分析范围<select v-model="selectionMode" :disabled="busy || historyLoading"><option value="point">指定位置</option><option value="region">单个区域</option><option value="comparison">比较两个区域</option></select></label>
          <div v-if="selectionMode === 'point'" class="crop-fields"><label v-for="axis in (['x','y','z'] as const)" :key="axis">{{ axis }} / m<input v-model="position[axis]" type="number" step="any" :aria-label="`${axis} 坐标`" placeholder="选填" :disabled="busy || historyLoading"></label></div>
          <div v-for="(box,index) in (selectionMode === 'point' ? [] : regions.slice(0,selectionMode === 'comparison' ? 2 : 1))" :key="index" class="region-fields">
            <strong>区域 {{ index === 0 ? 'A' : 'B' }}（米）</strong><div class="crop-fields"><label v-for="axis in (['x','y','z'] as const)" :key="axis">{{ axis }}<input v-model="box[`${axis}_min`]" type="number" step="any" placeholder="下限" :aria-label="`区域${index} ${axis}下限`" :disabled="busy || historyLoading"><span>至</span><input v-model="box[`${axis}_max`]" type="number" step="any" placeholder="上限" :aria-label="`区域${index} ${axis}上限`" :disabled="busy || historyLoading"></label></div>
          </div>
        </details>

            </details>
            <div class="composer-footer"><div class="tool-chips"><span class="tool-chip"><span>✧</span> 证据复核</span><span class="tool-chip"><span>◎</span> 农业知识</span><button type="button" class="tool-chip" :class="{'web-off':!webSearchEnabled}" aria-label="联网搜索" :aria-pressed="webSearchEnabled" :disabled="busy || historyLoading || capabilities?.web_search_configured===false" title="本地资料不足时联网补充原文；也可在问题中明确要求联网检索" @click="webSearchEnabled=!webSearchEnabled"><span>◎</span> {{ webSearchEnabled ? '联网搜索' : '联网已关闭' }}</button></div><div class="send-tools"><small v-if="question.length">{{ question.length }}/2000</small><button v-if="busy" class="send-button stop" type="button" aria-label="取消分析" title="取消分析" @click="cancel">■</button><button v-else class="send-button" type="submit" aria-label="发送问题" title="发送问题" :disabled="!ready || !question.trim()">↑</button></div></div>
          </form>
          <div v-if="!messages.length" class="suggestions starter-suggestions"><button v-for="item in suggestions" :key="item" @click="question=item">{{ item }} <span>↗</span></button></div>
          <p v-if="capabilities && !capabilities.model_configured" class="error">DeepSeek 尚未配置，暂时无法发送问题。</p>
        </div>
      </div>
    </section>
    <div v-if="chatDialog" class="chat-dialog-backdrop" @click.self="!managingChat && (chatDialog=null)" @keydown.esc="!managingChat && (chatDialog=null)">
      <form class="chat-dialog" role="dialog" aria-modal="true" aria-labelledby="chat-dialog-title" @submit.prevent="confirmChatManagement">
        <h2 id="chat-dialog-title">{{ chatDialog.mode==='rename' ? '更改对话名称' : '删除对话' }}</h2>
        <label v-if="chatDialog.mode==='rename'" for="chat-name">对话名称<input id="chat-name" v-model="chatName" maxlength="80" :disabled="managingChat" autocomplete="off"></label>
        <p v-else>确定删除“{{ chatDialog.title }}”吗？该会话将从历史列表中移除。</p>
        <p v-if="chatDialogError" class="error" role="alert">{{ chatDialogError }}</p>
        <div class="chat-dialog-actions"><button type="button" :disabled="managingChat" @click="chatDialog=null">取消</button><button class="confirm" type="submit" :disabled="managingChat || (chatDialog.mode==='rename' && !chatName.trim())">{{ managingChat ? '正在保存…' : chatDialog.mode==='rename' ? '保存' : '确认删除' }}</button></div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.chat-row {position:relative;display:flex;align-items:center;border-radius:9px;margin-bottom:4px;}
.chat-row.selected {background:#e9ecf4;}
.chat-list .chat-title {flex:1;min-width:0;margin:0;}
.chat-list .chat-more {flex:none;width:30px;margin:0;padding:8px 0;text-align:center;font-size:21px;}
.chat-menu {position:absolute;right:4px;top:calc(100% - 2px);z-index:12;background:white;border:1px solid #e9ebf1;box-shadow:0 6px 20px #20264015;border-radius:9px;min-width:110px;padding:4px;}
.chat-list .chat-menu button {margin:0;padding:7px 12px;}
.delete-chat {color:#b54c45;}
.chat-dialog-backdrop {position:fixed;inset:0;background:#17233b55;z-index:1000;display:grid;place-items:center;padding:20px;}
.chat-dialog {background:white;border-radius:16px;padding:24px;width:min(400px,100%);box-shadow:0 12px 48px #17233b33;}
.chat-dialog h2 {margin:0 0 14px;font-size:18px;}.chat-dialog p {overflow-wrap:anywhere;}
.chat-dialog input {width:100%;box-sizing:border-box;margin-top:8px;}
.chat-dialog-actions {display:flex;justify-content:flex-end;gap:12px;margin-top:20px;}.chat-dialog-actions button {padding:7px 18px;border-radius:8px;background:#edf0f6;}
.chat-dialog-actions .confirm {background:var(--blue);color:white;}
.diagnostics {margin:12px 8px;color:var(--muted);font-size:12px;}
.assistant-workspace { color-scheme:light; position:relative; --blue:#4d6bfe; --text:#252936; --muted:#8b909c; display:flex; flex-direction:row-reverse; flex:1; min-width:0; min-height:0; color:var(--text); background:#fff; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; font-size:14px; line-height:1.65; }
button,input,textarea,select { font:inherit; } button { border:0; box-shadow:none; color:inherit; background:transparent; cursor:pointer; } button:disabled { opacity:.45; cursor:not-allowed; } button:hover:not(:disabled) { background:#eef0f6; } a { color:var(--blue); text-decoration:none; } button:focus-visible,a:focus-visible,summary:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible { outline:2px solid var(--blue); outline-offset:3px; }
.chat-sidebar { width:252px; flex:none; background:#f8f9fb; border-left:1px solid #eff0f4; display:flex; flex-direction:column; padding:25px 16px 18px; }
.brand-row { display:flex; align-items:center; gap:9px; padding:0 8px; color:var(--blue); margin-bottom:28px; } .brand-row strong { font-size:23px; letter-spacing:1px; } .brand-mark { font-size:34px; line-height:1; } .brand-row .icon-button { margin-left:auto; color:#8b909c; }
.icon-button { width:32px; height:32px; border-radius:8px; font-size:20px; padding:0; flex:none; }
.new-chat { display:flex; align-items:center; justify-content:center; gap:8px; background:#fff; border:1px solid #e9ebf1; border-radius:24px; padding:10px; box-shadow:0 2px 4px #20264006; font-size:15px; } .new-chat span {font-size:21px;line-height:1;}
.workspace-links { display:flex; flex-direction:column; gap:5px; margin:22px 0 26px; } .workspace-links a {color:#646b79; padding:8px 12px; border-radius:8px;} .workspace-links a:hover {background:#edf0f6;} .workspace-links span {margin-right:9px; font-size:19px;}
.chat-list { margin-top:28px; flex:1; overflow-y:auto; min-height:0; } .section-label {color:#969ba5; font-size:12px; margin:0 12px 10px;} .empty-history {color:#a0a5af; font-size:12px; margin:16px 12px;} .chat-list button {text-align:left; width:100%; display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:11px 12px; border-radius:9px; margin-bottom:4px;} .chat-list button.selected {background:#e9ecf4; color:#303749;}
.sidebar-footer {display:flex; align-items:center; gap:10px; border-top:1px solid #e9ebf1; padding:18px 6px 0; margin-top:16px;} .avatar {background:#e7ecff; color:var(--blue); border-radius:50%; width:34px; height:34px; display:grid; place-items:center;} .sidebar-footer strong {font-size:13px;font-weight:500;} .sidebar-footer small {display:block; font-size:11px; color:#969ba5;}
.chat-main {flex:1; display:flex; flex-direction:column; min-width:0; position:relative;} .assistant-header {display:flex; align-items:center; justify-content:space-between; padding:23px 32px; gap:12px; flex:none;} .header-title,.header-actions {display:flex; align-items:center; gap:12px;} .header-title {color:#626978; font-size:14px;} .beta {font-size:10px; color:#7d89b8; border:1px solid #e3e8fa; border-radius:5px; padding:1px 6px;} .bind-button {border:1px solid #e6e9ef; border-radius:18px; padding:5px 13px; font-size:12px;color:#697282;}
.context-strip {display:flex; gap:10px; justify-content:center; align-items:center; flex-wrap:wrap; font-size:12px; color:#7c8492; padding:4px 24px 12px;} .context-strip strong {font-weight:500;} .status-dot {width:6px;height:6px;background:#53af91;border-radius:50%;}
.conversation {flex:1; min-height:0; display:flex; flex-direction:column; overflow-y:auto; padding:0 32px 12px;} .messages {width:100%; max-width:820px; margin:0 auto; min-height:0;} .messages:empty {display:none;} .compose-area {width:100%;max-width:820px; margin:auto; padding-bottom:24px;}
.welcome {text-align:center; margin-bottom:32px;} .welcome-heading {display:flex; justify-content:center; align-items:center; gap:14px;} .welcome-mark {color:var(--blue); font-size:44px; line-height:1;} .welcome h1 {font-size:28px; font-weight:600; color:#202633; letter-spacing:.5px;} .welcome p {color:#969ca8; font-size:13px; margin:14px 0 0;}
.composer {border:1px solid #e4e7ee; border-radius:18px; padding:10px 14px; box-shadow:0 10px 36px #1d2f5e06; background:#fff;} .composer:focus-within {border-color:#b7c3ff;} .question-label {position:absolute; width:1px;height:1px;overflow:hidden;clip-path:inset(50%);} textarea {display:block; width:100%; resize:none; height:28px; min-height:28px; max-height:120px; overflow-y:auto; border:0; background:transparent; color:#303746; outline:none; padding:0 2px; line-height:1.7; font-size:15px;} textarea:focus-visible {outline:none;} textarea::placeholder {color:#a8aeb9;} .composer-footer {display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:6px;} .tool-chips,.send-tools {display:flex; gap:8px; align-items:center;} .tool-chip {border:1px solid #d8e0ff; background:#f3f6ff; color:#657cf0; padding:3px 10px; border-radius:18px; font-size:12px; white-space:nowrap;} .tool-chip span {margin-right:3px;} .tool-chips {flex-wrap:wrap;} .tool-chip.web-off {background:#f7f8fa;border-color:#e5e8ef;color:#8b94a4;} .send-button {width:32px;height:32px;border-radius:50%;background:var(--blue);color:#fff;font-size:27px;line-height:1;padding:0;} .send-button:disabled {background:#b0beff;opacity:1;color:#fff;} .send-button:hover:not(:disabled) {background:#3c59e9;} .send-button.stop {font-size:13px;} .send-tools small {font-size:10px;color:#a0a6b1;}
.conditions {font-size:12px; margin-top:4px;} summary {cursor:pointer; color:#8d96a7; width:fit-content;} .conditions[open] {padding:10px;background:#f8f9fc;border-radius:10px;} .crop-fields {display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;} .crop-fields label {display:flex;align-items:center;gap:6px;color:#626b7d; flex-wrap:wrap;} input,select {background:#fff;border:1px solid #dde2ec;border-radius:7px;color:#303746;padding:5px 8px;width:130px;} .selection {margin-top:10px;} .selection select {width:auto; margin:8px;} .region-fields input {width:75px;} .region-fields {margin-top:12px;}
.suggestions {display:flex; flex-wrap:wrap;gap:10px;} .starter-suggestions {margin-top:22px;justify-content:center;} .starter-suggestions button {border:1px solid #edf0f5; border-radius:18px; padding:6px 12px;font-size:12px;color:#8a92a2;} .starter-suggestions span {margin-left:6px;color:#a9b2c4;}
.has-messages .conversation {overflow:hidden;} .has-messages .messages {flex:1;overflow-y:auto;padding:18px 0 10px;} .has-messages .compose-area {margin:0 auto;padding:6px 0 0; flex:none;} .exchange {margin:0 0 36px;} .user-question {margin:0 0 22px auto; width:fit-content;max-width:85%; background:#f1f4fb; border-radius:18px 18px 4px 18px;padding:12px 20px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere;} .answer {padding:0 8px;line-height:1.9;} .answer p {margin-bottom:16px;} .answer small {display:block;overflow-wrap:anywhere; font-size:11px; color:#9ba4b4;} .answer .suggestions {margin:14px 0;} .answer .suggestions a {font-size:12px;background:#f4f6ff;border-radius:14px;padding:4px 10px;} .muted {color:#8b94a4;font-size:13px;} .citation {font-size:12px; padding:14px 0; border-bottom:1px solid #edf0f5;} .citation strong {font-weight:500;} .citation p {margin:6px 0;} .error {font-size:12px;color:#bd5b43; margin:8px 0;}
.info-panel {position:absolute;right:28px;top:68px;z-index:5; background:#fff; border:1px solid #e7eaf1; box-shadow:0 8px 35px #22305414; border-radius:16px; padding:22px; width:min(350px,calc(100% - 32px));max-height:70%;overflow:auto;font-size:12px;color:#838c9d;} .info-panel h2 {font-size:15px;color:#303746;margin-bottom:15px;} .info-panel p {margin-bottom:12px;}
@media(min-width:1700px) {.chat-sidebar{width:280px;} .compose-area,.messages{max-width:900px;}}
@media(max-width:900px) {.chat-sidebar{width:210px;} .assistant-header{padding:18px 20px;} .conversation{padding:0 24px 12px;} .beta{display:none;} .welcome h1{font-size:23px;} .welcome-mark{font-size:34px;} .starter-suggestions{gap:7px;} }
@media(max-width:600px) {.chat-sidebar{width:185px;padding:18px 10px;position:absolute;right:0;top:0;bottom:0;z-index:10;box-shadow:-8px 0 30px #22305412;} .chat-main{width:100%;} .assistant-header{padding:16px;} .header-title{font-size:12px;gap:6px;} .conversation{padding:0 16px 10px;} .welcome h1{font-size:22px;} .welcome-heading{gap:9px;} .welcome p{font-size:11px;} .compose-area{padding-bottom:20px;} .composer{padding:10px 12px;border-radius:16px;} .starter-suggestions button{font-size:11px;} .tool-chip{font-size:11px;padding:3px 8px;} .has-messages .compose-area{padding-top:8px;} .context-strip{font-size:10px;gap:5px;} }
</style>
