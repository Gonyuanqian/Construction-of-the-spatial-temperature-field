/**
 * 模型库那四条接口，加上**「哪些模型能用」的唯一一处定义**。
 *
 * 为什么单出一层而不是让每个视图各调 `getJson`：
 * 页③ 与页⑤ 都要回答「现在有没有一个能用的模型」，两页各写一遍
 * `filter(r => r.compatible)` 不会报错，只会慢慢漂 —— 漂开之后一页画场、
 * 另一页说没模型，而两页读的是同一份数据，屏上没有一处提示。
 */
import { getJson, postJson } from './client'
import type { ModelDetailPayload, ModelsPayload, ModelRowPayload } from './types'

export function fetchModels(): Promise<ModelsPayload> {
  return getJson<ModelsPayload>('/api/models')
}

export function fetchModelDetail(id: number): Promise<ModelDetailPayload> {
  return getJson<ModelDetailPayload>(`/api/models/${id}`)
}

/** 只发一个名字。落库的那一份在后端手上，不走浏览器搬 794 KB。 */
export function saveModel(name: string): Promise<ModelRowPayload> {
  return postJson<ModelRowPayload>('/api/models', { name })
}

export function setCurrentModel(id: number): Promise<{ id: number }> {
  return postJson<{ id: number }>(`/api/models/${id}/current`)
}

/** 能拿来构场的那些。载荷还没回来（null）时给空数组，不抛。 */
export function usableModels(p: ModelsPayload | null): ModelRowPayload[] {
  return (p?.rows ?? []).filter((r) => r.compatible)
}
