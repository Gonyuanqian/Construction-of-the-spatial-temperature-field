/**
 * 「哪些模型能用」**只有这一处定义**。
 *
 * 页③ 与页⑤ 都要用它，两页各写一遍 `filter(r => r.compatible)` 不会报错，
 * 只会慢慢漂 —— 漂开之后一页画场、另一页说没模型，而两页读的是同一份数据。
 */
import { describe, expect, it } from 'vitest'

import { usableModels } from './models'
import type { ModelsPayload, ModelRowPayload } from './types'

function row(over: Partial<ModelRowPayload> = {}): ModelRowPayload {
  return {
    id: 1, name: 'x', saved_at: '2026-10-08T10:00:00',
    dataset_sig: 'a', groups_sig: 'b', data_file: 'f.xlsx',
    data_start: '2026-07-23T11:00:00', data_end: '2026-07-27T11:55:00',
    mae: 0.1, rmse: 0.2, r2: 0.99, is_current: true,
    compatible: true, why: '', ...over,
  }
}

function payload(rows: ModelRowPayload[]): ModelsPayload {
  return { rows, current_id: 1, dataset_file: 'f.xlsx', dataset_sig: 'a' }
}

describe('可用的模型', () => {
  it('只留 compatible 的那些', () => {
    const p = payload([row(), row({ id: 2, compatible: false, why: '数据来源不同：别人家的棚.xlsx' })])
    expect(usableModels(p).map((r) => r.id)).toEqual([1])
  })

  it('载荷还没回来（null）时给空数组，不抛', () => {
    // 页③ 的模板在取数回来之前就渲染一次 —— 抛在那里会白屏，
    // 而白屏比空态难查得多（它没有一句话）。
    expect(usableModels(null)).toEqual([])
  })

  it('一行都没有时给空数组', () => {
    expect(usableModels(payload([]))).toEqual([])
  })
})
