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

/* ------------------------------------------------------------------ *
 * 页② 模型训练：特征构造表（Task 9 `/api/features`）
 * ------------------------------------------------------------------ */

export interface FeatureGroupRow {
  group: string
  columns: string[]
  n_columns: number
  what: string
}

export interface FeaturesPayload {
  default_groups: string[]
  groups: FeatureGroupRow[]
  all_columns: string[]
  /**
   * 全列清单的列数，**由后端给**（= `all_columns` 并集长度）。
   * 不由前端 `all_columns.length` 数：「各组 n_columns 之和」与「并集长度」
   * 组分一旦重叠就会静默不一致 —— 这是「前端不做任何数值计算」要防的事。
   */
  n_all_columns: number
  notes: string[]
}

/* ------------------------------------------------------------------ *
 * 页② 模型训练：标定包（Task 9 `/api/calibration`）
 *
 * 这里每一个量都是**随标定包**的（Provenance kind="pack"）——
 * 标定当时算好、写在包里；页面只负责原样摆出来，不重算。
 * ------------------------------------------------------------------ */

export interface TunedKeyRow { key: string; value: string; space: string }
export interface ParamRow { param: string; value: string; note: string }
export interface PlateauRow { dim: string; lo: string; hi: string }
export interface MetricRow {
  /**
   * ⚠️ mae / rmse / r2 都是 `number | null`。后端 `calibration.py:_jsonable`
   * 对浮点再过一道 `_finite`，把 NaN / ±Inf 翻成 None（`allow_nan=False` 的
   * JSONResponse 不吃 NaN）。「这一折的指标算不出来」在线上就是 null ——
   * 不是 0，也不是整行缺失。后端为此专门写了测试（单折 MAE=NaN 记为 null），
   * 所以这是**后端承认的合法状态**，前端必须容。
   */
  mae: number | null; rmse: number | null; r2: number | null
  fold_kind: string; fold: string; region: string; group: string; n: number; tag: string
}
export interface PerPointRow {
  sensor_id: number; shed: string; position: string; layer: string
  group: string; n: number
  /** ⚠️ 同 MetricRow：`_finite` 把非有限浮点翻成 null（逐点的 MAE/RMSE/R² 也一样）。 */
  mae: number | null; rmse: number | null; r2: number | null
}

export interface CalibrationPayload {
  present: boolean
  /**
   * ⚠️ 可以是 null。`present === false` 时给的是「为什么没有这一份包」，
   * 页面据此说「未标定」；`present === true` 时没有这句话，是 null。
   */
  reason: string | null
  /**
   * ⚠️ 三个都是 `string | null`。它们来自标定包自身（生成时刻、工具版本、
   * 分组签名）；**没有包时整组都不存在**，线上就是 null，不是空串 ——
   * 空串会被读成「有包但字段是空的」。
   */
  created_at: string | null
  tool_version: string | null
  groups_sig: string | null
  /** 数据集指纹总是有（就是当前数据集的身份），与有没有标定包无关。 */
  dataset_sig: string
  feature_groups: string[]
  trend_kind: string
  tuned_keys: TunedKeyRow[]
  params: ParamRow[]
  plateau: PlateauRow[]
  /**
   * ⚠️ 可以是 null。只有 lz 贴着搜索下界时后端才给这句警告；没有触发就是 null ——
   * 页面不用「空字符串」也就不用判断「空 vs 没这句」。
   */
  lz_note: string | null
  metrics: MetricRow[]
  per_point: PerPointRow[]
  /**
   * ⚠️ 整个 ab 块可以是 null（没有标定包时没有 A/B 对照这一组数）。
   * 块内三个浮点也都可以是 null —— 它们同样过 `_finite`，非有限翻成 null
   * （见 MetricRow 的说明）。
   */
  ab: { mae_a: number | null; mae_b: number | null; gap: number | null } | null
  /** ⚠️ 可以是 null：没有包时没有折的种类。 */
  fold_kind: string | null
  n_folds: number
  /**
   * ⚠️ 可以是 null。正常情况下是 MAE 最差的那一折；
   * 但当所有折的 MAE 都非有限（全 NaN）时，后端**报 null 而不是硬指一折**
   * （见 `backend/api/routes/calibration.py`）—— 没有最差，就没有最差。
   */
  worst_fold: { fold: string; mae: number } | null
  ab_note: string
  note: string
}
