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
  // 页① 那排卡片的两格。两个都由后端算（spec §六 硬约束 1）：
  // `n_missing` 是缺失的**格子**数，`n_dup_times` 是**原始文件**里重复的
  // 时刻数 —— 修完的轴严格递增，拿它算恒为 0，所以那一格必须来自修复前。
  n_missing: number
  n_dup_times: number
  time_start: string
  time_end: string
  sheds: Record<string, number>
  positions: Position[]
  // 测点编号（B1、B2……），**单独一格**：`positions` 是几何，编号是展示。
  // 混在一起的话，每个读 `positions` 的地方都要重新想一遍「多出来的是不是几何」
  // （后端有 `test_测点的几何形状没有被这次改动动到` 守着同一件事）。
  // 次序由后端 `api/routes/dataset.py::_point_codes` 定：层从高到低，同层 x 从左到右。
  point_codes: Record<string, string>
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

/** 页③ 用到的三个载荷。字段名与后端 `api/routes/field.py` 逐字对应。 */

export interface SensorPoint {
  id: string
  x: number
  z: number
  layer: string
}

/** 一个断面的场。`values` 是行主序：`values[iz][ix]`，与 `z` / `x` 同序。 */
export interface SectionShed {
  shed: string
  y: number
  /** 拱外是 `null`（后端送不了 NaN —— `allow_nan=False` 会变成 500）。 */
  values: (number | null)[][]
  /** 无测量带的格子下标 `[ix, iz]`。带里**有**外推值，但界面上不报数。 */
  stripes: [number, number][]
}

export interface SectionsPayload {
  t_index: number
  time: string
  n_times: number
  preset: string
  monotonic: boolean
  /** 配置来自标定包（true）还是 `FALLBACK_*` 兜底（false）。两者不可直接比大小。 */
  calibrated: boolean
  /** 三格**共享**的色标范围。前端不许各算各的。 */
  vmin: number
  vmax: number
  max_measured_z: number
  x_min: number
  x_max: number
  z_max: number
  x: number[]
  z: number[]
  arch: [number, number][]
  sensors: SensorPoint[]
  sheds: SectionShed[]
  note: string
}

export interface CurvePayload {
  shed: string
  x: number
  y: number
  z: number
  label: string
  n_times: number
  time: string[]
  /** 拱外或落在无测量带里时，整条都是 `null`（`defined` 为 false）。 */
  values: (number | null)[]
  defined: boolean
  /** 包含「没有施加竖直软单调投影」这句口径 —— 界面上要显示的就是它。 */
  note: string
}

export interface ComparePayload {
  shed: string
  y: number
  t_index: number
  time: string
  n_times: number
  preset: string
  x: number[]
  z: number[]
  arch: [number, number][]
  sensors: SensorPoint[]
  max_measured_z: number
  before: (number | null)[][]
  after: (number | null)[][]
  /** `约束前 − 约束后`。正值 = 这一格被约束压低了。 */
  delta: (number | null)[][]
  /**
   * 无测量带的格子下标 `[ix, iz]`，与 `SectionsPayload` 的同一份事实。
   * **前端不许自己从 `x` / `z` / `max_measured_z` 推** —— 那是把后端的一条规则
   * 实现了第二遍（硬约束 1），两条路径漂了不报错。
   */
  stripes: [number, number][]
  /** `before` / `after` 共用。 */
  vmin: number
  vmax: number
  /** `delta` 的**对称**范围半径：色标是 `[-delta_vmax, +delta_vmax]`。 */
  delta_vmax: number
  light: number
  gate_open: boolean
  gate_label: string
  /** 门禁关闭（夜里无光照）时两张图**逐位相同**。 */
  identical: boolean
  note: string
}

/* ------------------------------------------------------------------ *
 * 页③ 三维视图（V7 棚体）：`GET /api/field/volume`
 * ------------------------------------------------------------------ */

/** 一整卷里的一片。`values` 同样是行主序 `values[iz][ix]`。 */
export interface VolumePlane {
  y: number
  /**
   * 这一片是不是**实测断面**。**由后端判定，不由前端猜。**
   * 判据是 `available_sheds`，不是 `y ∈ {3, 9, 15}` —— 留一断面时
   * `field_at(y = 9)` 会去混合 p1 与 p3，那时 y = 9 是算出来的。
   */
  measured: boolean
  /** `measured` 为 true 时是被测的那座棚，否则是 null。 */
  shed: string | null
  /** 拱外是 `null`（后端送不了 NaN —— `allow_nan=False` 会变成 500）。 */
  values: (number | null)[][]
}

/* ------------------------------------------------------------------ *
 * 实时模式：`/api/live/*`（七条接口）
 * ------------------------------------------------------------------ */

/**
 * `GET /api/live/status` 与 `start` / `pause` / `next` 三条动作接口共用的形状。
 *
 * ⚠️ **`prepare` 不在其中** —— 它回的是 `PrepareResult`，不是这份状态。
 * 这条注释原来写的是「动作接口回的就是这份状态，点完不用再补一次查询」，
 * 于是 `LiveView` 把四个动作的回执一律当状态用；`prepare` 那一支因此悄悄坏掉
 * （状态条上空的帧号、`frame/undefined` 422），而替身恰好也回错了形状，
 * 一路绿到终审。
 */
export interface LiveStatus {
  state: 'idle' | 'ready'
  running: boolean
  /** 现在停在第几帧（留出段的下标，0..total-1）。 */
  cursor: number
  /** 留出段一共多少帧。 */
  total: number
  /** 多久一帧。**由后端给**：时钟在服务端，前端不自己定这个数。 */
  interval_s: number
}

/**
 * `POST /api/live/prepare` 的回执。规格书 §五 只给 `{state, seconds}` ——
 * 建管线要几十秒，把这个耗时报出来是它唯一的额外内容。
 *
 * 把它当 `LiveStatus` 用会安静地坏：状态条渲染成「第  帧，共  帧」，
 * `frame/{cursor}` 拼出 `/frame/undefined`（真后端 422）。所以四个动作的
 * 回执一律**不直接当状态用**，见 `LiveView.act`。
 */
export interface PrepareResult {
  state: 'ready'
  seconds: number
}

/** 这一帧的如实记录：棚顶气象 + 24 路实测读数。 */
export interface LiveFrameBlock {
  /** 留出段的帧号 `n`。**不是** `t_index`（那是管线时间轴上的下标）。 */
  n: number
  time: string
  bg_temp: number | null
  bg_rh: number | null
  bg_light: number | null
  /** 次序：p1 的 8 个位置，然后 p2、p3。 */
  sensor_temps: (number | null)[]
}

/**
 * 一帧的断面载荷。**与页③ 的 `SectionsPayload` 同源** ——
 * 后端把装配抽成同一个函数（`routes/field.py::sections_payload`），
 * 这边因此能复用同一套纯函数与同一个组件，不新写一份判定。
 */
export interface LiveFramePayload extends SectionsPayload {
  frame: LiveFrameBlock
  /** 这一段是 `LiveStatus` 去掉 `state`：状态由 `/api/live/status` 单独回答，
   *  帧载荷不重复它。 */
  live: Omit<LiveStatus, 'state'>
}

export interface VolumePayload {
  t_index: number
  /** 时刻字符串，**后端给**，前端不自己算。每一条读数都要带上它。 */
  time: string
  n_times: number
  preset: string
  monotonic: boolean
  calibrated: boolean
  y_step: number
  y_min: number
  y_max: number
  x_min: number
  x_max: number
  z_max: number
  max_measured_z: number
  /** 整卷**共用**的色标范围，与页③ 的切面图同一个口径。前端不许各算各的。 */
  vmin: number
  vmax: number
  x: number[]
  z: number[]
  arch: [number, number][]
  /** 与 `/field/arch` 同形（`ShedInfo`）。 */
  sheds: ShedInfo[]
  sensors: SensorPoint[]
  /**
   * 本帧**真正有训练样本**的断面。`measured` 按它算，
   * 代码不许假设它总是三座棚 —— 留一折时它就只有两座。
   */
  available_sheds: string[]
  /**
   * 无测量带的格子下标 `[ix, iz]`，**全片共用一份**（规格书 §四.4）。
   * 与 `SectionsPayload` 的同一份事实、同一个名字：前端不许自己从
   * `x` / `z` / `max_measured_z` 推 —— 那是把后端的一条规则实现了第二遍。
   */
  stripes: [number, number][]
  planes: VolumePlane[]
  elapsed_ms: number
  note: string
}

/** 导入成功后后端给的那一份摘要（规格书 §4.3）。**不是** `GET /api/dataset` 的整份载荷。 */
export interface UploadResult {
  signature: string
  file: string
  n_times: number
  n_columns: number
  time_start: string
  time_end: string
}
