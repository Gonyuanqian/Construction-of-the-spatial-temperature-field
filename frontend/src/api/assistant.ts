import { ApiError, authFetch, getJson, postJson } from './client'
import { readEventStream } from './eventStream'

export interface Evidence {
  id: string; text: string; title?: string; locator?: string
  value?: number; unit?: string; origin?: string; statistic_definition?: string
  source_title?: string; source_url?: string; doi?: string; source_access?: string
  retrieved_at?:string; published_at?:string|null; review_status?:string
  position?: { x: number; y: number; z: number }; x?: number; y?: number; z?: number; kind?: string
}
export interface FieldAction { type: 'view_snapshot_point'; snapshot_id: string; position: { x: number; y: number; z: number }; label: string; fact_id: string }
export interface FieldRegion { x_min: number; x_max: number; y_min: number; y_max: number; z_min: number; z_max: number }
export interface AnalysisSnapshot {
  design_id?:string; design_revision?:number
  snapshot_id: string; session_id: string; frame_index: number; source_time: string
  model_id: number|null; data_mode: string; facts: Evidence[]
}
export interface AssistantCapabilities {
  native_thinking_enabled?:boolean
  web_search_configured?:boolean
  model_configured: boolean; knowledge_configured: boolean; model: string
  min_cycles: number; max_cycles: number; limitations: string[]
}
export interface AssistantRun {
  answer_stream?:{generation:number;text:string}
  thinking?:{enabled:boolean;effort:string;calls:number;reasoning_chars:number;status:string}
  web_search_enabled?:boolean
  event_seq?:number
  protocol_repairs?:number
  id: string; question: string; status: string; cycle: number; events: string[]; detail?: string
  analysis?: AnalysisRecord | null
  conversation_id?: string; parent_run_id?: string | null; snapshot_id?: string | null
  conversation_origin?: 'greenhouse_design_inspection'
  crop?: string | null; stage?: string | null; error_code?: string | null
  position?: {x:number;y:number;z:number} | null; region?: FieldRegion | null
  regions?: {first:FieldRegion;second:FieldRegion} | null
  resolved_context?: {snapshot_id?:string|null;crop?:string|null;stage?:string|null;
    selection?:{position?:AssistantRun['position'];region?:FieldRegion|null;regions?:AssistantRun['regions']}}
  result?: { claims: { text: string; evidence_ids: string[]; basis?:string; conditions?:string[] }[]; missing_conditions: string[]
    citations: Evidence[]; snapshot: Partial<AnalysisSnapshot>; actions?: FieldAction[]; route?: string } | null
}
export interface ConversationSummary {id:string; title:string; head_run_id:string; updated_at:number}
export interface Activity {
  id:string; kind:'model'|'tool'; status:'running'|'completed'|'failed'|'interrupted'|'cancelled'; label:string
  received_chars?:number; tool_count?:number; evidence_count?:number
}
export interface SessionEvent {
  seq:number; type:string; time:number; turn_id:string; step_id:string|null
  data:{run?:AssistantRun;generation?:number;text?:string} & Partial<Activity>
}
export interface Conversation extends ConversationSummary {
  runs:AssistantRun[]; has_older:boolean; cursor?:number; timeline?:SessionEvent[]; protocol_version?:number
}
export interface AnalysisRecord {
  public_nodes?:{id:string;title:string;summary:string;status:string;items:{text:string;evidence_ids?:string[]}[]}[]
  version: 1; kind: 'execution_summary'; started_at: number | null; finished_at: number | null; elapsed_ms: number
  steps: { id: string; title: string; status: string; summary: string;
    items: { text: string; tool?: string; evidence_ids?: string[] }[] }[]
}
export const assistantApi = {
  capabilities: () => getJson<AssistantCapabilities>('/api/assistant/capabilities'),
  snapshot: (sessionId?:string) => postJson<AnalysisSnapshot>('/api/assistant/snapshots', sessionId?{session_id:sessionId,frame_index:0}:{}),
  submit: (body: { snapshot_id: string | null; request_key: string; question: string; crop: string | null; stage: string | null;
    web_search_enabled?:boolean;
    conversation_id?:string; parent_run_id?:string|null; legacy_run_ids?:string[];
    position?: { x: number; y: number; z: number } | null; region?: FieldRegion | null;
    regions?: {first: FieldRegion; second: FieldRegion} | null }) =>
    postJson<AssistantRun>('/api/assistant/runs', body),
  run: (id: string) => getJson<AssistantRun>(`/api/assistant/runs/${id}`),
  cancel: (id: string) => postJson<AssistantRun>(`/api/assistant/runs/${id}/cancel`, {}),
  snapshotInfo: (id: string) => getJson<AnalysisSnapshot>(`/api/assistant/snapshots/${id}`),
  conversations: () => getJson<ConversationSummary[]>('/api/assistant/conversations'),
  conversation: (id:string) => getJson<Conversation>(`/api/assistant/conversations/${id}`),
  renameConversation: (id:string,title:string) => postJson<{id:string;title:string}>(`/api/assistant/conversations/${id}/rename`,{title}),
  deleteConversation: (id:string) => postJson<{id:string;deleted:boolean}>(`/api/assistant/conversations/${id}/delete`,{}),
  stream: async (id:string, after:number, signal:AbortSignal, receive:(event:SessionEvent)=>void) => {
    const response=await authFetch(`/api/assistant/conversations/${encodeURIComponent(id)}/stream?after=${after}`,
      {signal,headers:{Accept:'text/event-stream'}})
    if(!response.ok) throw new ApiError('会话事件流暂时不可用',response.status)
    if(!response.headers.get('content-type')?.includes('text/event-stream') || !response.body)
      throw new Error('会话事件流格式无效')
    await readEventStream(response.body, signal, (type,data) => {
      if(type==='ready') {
        if(JSON.parse(data).protocol_version!==1) throw new Error('会话协议版本不兼容')
        return
      }
      if(type!=='session') return
      const event=JSON.parse(data) as SessionEvent
      if(!Number.isSafeInteger(event.seq) || event.seq<1 || typeof event.type!=='string' ||
          typeof event.turn_id!=='string' || !event.data || typeof event.data!=='object')
        throw new Error('会话事件格式无效')
      receive(event)
    })
  },
}
