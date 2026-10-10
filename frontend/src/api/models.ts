/**
 * 模型库那四条接口，加上**「哪些模型能用」的唯一一处定义**。
 *
 * 为什么单出一层而不是让每个视图各调 `getJson`：
 * 页③ 与页⑤ 都要回答「现在有没有一个能用的模型」，两页各写一遍
 * `filter(r => r.compatible)` 不会报错，只会慢慢漂 —— 漂开之后一页画场、
 * 另一页说没模型，而两页读的是同一份数据，屏上没有一处提示。
 *
 * ⚠️ `compatible` 的**含义**在 2026-10-10 改过（用户裁定「模型不绑数据集」）：
 * 它从「两轴都对得上」变成「**特征组**对得上」（＝能不能拿来构场）。数据集那
 * 一轴不再拦着选，只由 `borrowed` 标出来。所以 `usableModels` 这个名字今天的
 * 意思是「**能用**的那些」，不是「完全对得上的那些」—— 借来的也算能用。
 * 判据本身在后端一处（`deps.model_fit`），这里只读结果，不许自己比签名。
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

/**
 * 能拿来构场的那些（**借来的也算**）。载荷还没回来（null）时给空数组，不抛。
 *
 * 是页③/页⑤ 那两张空态的闸门：后端会拒绝的模型（特征组对不上）不该让屏上
 * 读成「有模型」—— 那时它其实会用兜底参数算，而屏上就会是一张没有模型参与
 * 的场。
 */
export function usableModels(p: ModelsPayload | null): ModelRowPayload[] {
  return (p?.rows ?? []).filter((r) => r.compatible)
}
