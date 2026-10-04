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

export interface TimeseriesPayload {
  n_times: number
  time: string[]
  /**
   * ⚠️ 全部数值列都是 `number | null`。路由对每个数过 `_finite`
   * （`dataset.py:_finite`），非有限浮点翻成 None；`allow_nan=False`
   * 不吃 NaN/Inf。某一时刻某列缺失，线上就是 null —— 不是 0。
   */
  bg_temp: (number | null)[]
  sensors: Record<string, (number | null)[]>       // key = "p1|x0.15_z0.4"
  shed_mean: Record<string, (number | null)[]>
  detrended: Record<string, (number | null)[]>
  detrended_mean: Record<string, (number | null)[]>
  /** 固定 ±3 °C，由后端给出：纵轴范围也是判断的一部分（见路由 docstring）。 */
  detrended_domain: [number, number]
  note: string
}

export interface LayerTimeHeightShed {
  labels: string[]
  z: number[]
  /** 某一层某时刻全缺失时，groupby.mean() 给 NaN，路由已翻成 null。 */
  values: (number | null)[][]
}

export interface LayerTimeHeightPayload {
  step: number
  n_times: number
  n_columns: number
  time: string[]
  x_label: string
  source: string
  sheds: Record<string, LayerTimeHeightShed>
}
