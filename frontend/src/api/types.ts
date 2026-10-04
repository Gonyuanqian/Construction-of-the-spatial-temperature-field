/**
 * 后端返回的形状。与 `backend/api/routes/*.py` 一一对应 ——
 * 那边改了这边没跟，TypeScript 会在编译期说出来（这是选 TS 的主要理由之一）。
 *
 * **这些类型不做任何加工**：它们描述的是线上传的东西，不是页面想要的东西。
 * 页面想要的（比如「按棚分组的测点」）在各自的 view 里派生。
 */

export interface FixPayload {
  n_rows: number
  fixed_indices: number[]
  monotonic_before: boolean
  monotonic_after: boolean
  spacing_seconds: number
  n_gaps: number
}

export interface Position {
  id: string
  x: number
  z: number
  layer: string
}

export interface TempStat {
  shed: string
  position: string
  /**
   * ⚠️ 可以是 null。后端用 `JSONResponse(allow_nan=False)` 序列化，
   * 任何非有限浮点（全缺失的列 → NaN）都会在响应体构造时抛 ValueError，
   * 所以路由把 NaN/±Inf 翻成 None 再送出来（见 `dataset.py:_finite`）。
   * 「这段没有值」在线上就是 null，不是 0，也不是最接近的那个数。
   */
  mean: number | null
  min: number | null
  max: number | null
}

export interface CheckRowPayload {
  no: number
  name: string
  what: string
  status: 'ok' | 'warn'
  evidence: string
}

export interface DatasetPayload {
  signature: string
  file: string
  n_times: number
  n_columns: number
  time_start: string
  time_end: string
  sheds: Record<string, number>
  positions: Position[]
  temperature: TempStat[]
  fix: FixPayload
  checks: CheckRowPayload[]
  checks_note: string
}

export interface ShedInfo {
  id: string
  y: number
}

export interface ArchPayload {
  x_min: number
  x_max: number
  z_max: number
  max_measured_z: number
  arch: [number, number][]
  sheds: ShedInfo[]
}
