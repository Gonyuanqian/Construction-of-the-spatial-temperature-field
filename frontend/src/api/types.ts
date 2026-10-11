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

/** 预览表的一列（`GET /api/dataset/preview`）。 */
export interface PreviewColumn {
  /** **宽表里的列名**（`p1_x0.15_z0.4_temp_C`）。所以表里每一格都追得回文件那一列。 */
  key: string
  /** 屏上印的名字（`p1·B1`、`背景温度`）。后端拼好送来的 —— 前端不拼显示字符串。 */
  label: string
}

/**
 * 页① 的数据预览：**一张宽表的头部切片**，不是全量。
 *
 * `n_times` 与 `n_rows` 一起给，页面才写得出「前 500 行（共 1308 行）」。
 * 只回一个 `values` 数组的话，屏幕上看不出看到的是全部还是一段 ——
 * 那种沉默比截断本身更坏，所以这两格是契约的一部分，不是附赠。
 *
 * 时间**单列一个字段**，不混进 `values`：它是行标、在表里粘在左边，
 * 与那些数值列不是一类东西。
 */
export interface PreviewPayload {
  /** 这份数据集一共多少行。 */
  n_times: number
  /** 实际生效的上限（后端已夹到 `[0, n_times]`）。 */
  limit: number
  /** 本次真给了多少行。`values.length` 与 `time.length` 都等于它。 */
  n_rows: number
  columns: PreviewColumn[]
  time: string[]
  /** `n_rows × columns.length`。缺失格子是 `null`（见 `_finite`），不是 0。 */
  values: (number | null)[][]
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

/** 参数值。JSON 只认这三种 —— 布尔是 `cross_shed`，字符串是 `objective`。 */
export type ParamValue = string | number | boolean

/**
 * 面板上的一维（`GET /api/calibration` 的 `panel.trend` / `panel.idw`）。
 *
 * **`values` 与 `raw` 同下标**：前者是印在屏上的那一串（后端走 `fmt_value`），
 * 后者是**要发回去的那个值**。前端只做一件事：下标 → `raw[index]`。
 * 不插值、不取整、不做单位换算（规格书 硬约束 1）。
 *
 * ⚠️ 分成两列而不是只发 `values`：否则前端要把「开」解析回 `true`、
 * 把 `"0.5"` 解析回 `0.5` —— 那是把**印法**当协议。
 */
export interface PanelRow {
  /** `metric.power` / `cross_shed` / `trend.max_depth`。 */
  key: string
  /** 中文名。**从后端来** —— 它现在是控件的标签，前端不另写一份。 */
  label: string
  values: string[]
  raw: ParamValue[]
  /** 现在这一维取的是哪个。**后端保证它一定在 `raw` 里**（包若拿旧空间训的，
   *  后端会把当前值并进候选）—— 所以前端的 `indexOf` 一定找得到。 */
  current: ParamValue
}

/** 不进搜索域、但仍要在面板上露一行说明的参数（当前只有 `metric.ly`）。 */
export interface FixedRow { key: string; label: string; value: string; note: string }

/**
 * 参数面板。**一套值，两条来路**（规格书 §一）：手调与优选改的是同一套值。
 */
export interface CalibrationPanel {
  /** XGBoost 的八个，含 `objective`。 */
  trend: PanelRow[]
  /** IDW 的四个：`metric.power` / `metric.lx` / `metric.lz` / `cross_shed`。 */
  idw: PanelRow[]
  /** 只给说明、不给控件的那几个。 */
  fixed: FixedRow[]
}

/**
 * 一次标定任务的摘要。**没有结果** —— 图上那些数走
 * `GET /api/calibration/diagnostics`，轮询只回答「跑到哪一句了」。
 */
export interface JobSummary {
  id: string
  state: 'running' | 'done' | 'failed' | 'cancelled'
  /** 库里 `progress` 回调吐出来的**最近一行**人话。不给百分比（规格书 §4.3）。 */
  progress: string
  elapsed_s: number
  /** `failed` 时是异常的**原话**；其余三态是 null。 */
  error: string | null
  created_at: string
}

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
   * 这一份是从哪来的：`"library"`（库里的当前模型）/ `"unsaved"`（刚跑完、
   * 还没保存的那一份）/ `null`（都没有）。
   *
   * ⚠️ **两个分支都给这一格**（与 `mismatch` 同一条房规）：它不是「有时有、
   * 有时没有」的键。页② 据此选图章 —— 没有它，刚跑完的那一块和库里那份
   * 在屏上长得一模一样，而「这块数是不是已经留下来了」正是用户此刻唯一
   * 要判断的事。
   */
  source: 'library' | 'unsaved' | null
  /**
   * ⚠️ 可以是 null。`present === false` 时给的是「为什么没有这一份包」，
   * 页面据此说「未标定」；`present === true` 时没有这句话，是 null。
   */
  reason: string | null
  /**
   * 指纹对不上时，上一次标定对的是哪一份（规格书 §七）。`null` = 从来没有标过。
   *
   * ⚠️ **两个分支都给这一格**（有包时是 `null`）。这一格只在 `present === false`
   * 时有意义，但它不是「有时有、有时没有」的键 —— 那种键会让手写的夹具静默
   * 渲染成 `undefined`，而冒烟测试照样绿（与 `n_all_columns` 是同一个坑）。
   */
  mismatch: { dataset_sig: string; created_at: string | null; file: string } | null
  /**
   * **正在用的这一份**不是为当前这份数据标的时候，那句要说的话；对得上时是
   * **空串**（不是 null —— 前端不用判两种空，与 `ModelRow.why` 同一条房规）。
   *
   * ⚠️ 与上面那个 `mismatch` **不是一回事**：那个说的是「盘上躺着一份别人的
   * 旧包」（只在没有模型那一路），这个是「**正在用的就是**别人的那一份」。
   * 名字像，说的是两件事。
   */
  mismatch_note: string
  /**
   * ⚠️ **这一条载荷上没有 `artifact_note`**，虽然页③ 与页⑤ 的载荷有那一格。
   * 「成品读不动」是**构场那一路**的事实（`deps._artifact_note` 写在管线上，
   * 由 `routes/field.py` 发出去）；而这一条来自 `routes/calibration.py`，
   * 它不建管线，也就说不出成品读不读得动。在这里凭空加一格，就是让类型声称
   * 一个后端从不发送的字段 —— 哪天有人在页② 印它，那是一个静默的
   * `undefined`（`v-if` 恒假），而测试照样绿。要那一格，得先让那条路由
   * 真的算出它来。
   */
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
  /**
   * 参数面板。⚠️ **两条分支都给这一格** —— 它是模块常量加兜底值，
   * 不依赖盘上有没有包。只在有包时给，就是把「能调什么」藏到跑完之后。
   *
   * 它取代了原来的 `space`（待优选清单）与 `params`（最优参数表）：
   * 那两张表说的是同一件事的两面，接缝就是这里的 `values` 与 `current`。
   */
  panel: CalibrationPanel
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
  /**
   * 当前 / 最近一次标定任务，没有就是 `null`。
   *
   * ⚠️ **两个分支都给这一格**（与 `mismatch` 同一条房规）：它不是「有时有、
   * 有时没有」的键 —— 那种键会让手写的夹具静默渲染成 `undefined`，
   * 而冒烟测试照样绿。
   *
   * 它存在的理由是**刷新之后还接得上**（规格书 §4.7）：标定要几分钟，
   * 而切页与刷新都会把组件连同它手上的 job id 一起丢掉。
   */
  job: JobSummary | null
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
  /**
   * `calibrated` 为 true 时再分两档：**空串** = 这一份就是为当前数据标的；
   * 有话 = **借来的**（参数不是为这份数据标的，数照出，但不能当它的成绩）。
   * 未标定时恒为空串。与 `VolumePayload` / `CalibrationPayload` 同一个名字。
   */
  mismatch_note: string
  /**
   * 「这一条的成品读不动，已退回现训」那一句。空串表示没这回事。
   *
   * ⚠️ **是另一个字段，不是 `mismatch_note` 的第二种用法。**
   * `copy.ts` 的 `calibratedLabel` 用「`mismatch_note` 里有没有话」判
   * 「已标定（借来的）」—— 两件事共用一格，会让一份**本地**的模型在屏上
   * 自称「借来的」，把数的来历整个说反。
   */
  artifact_note: string
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
  /**
   * 这一片**拱内、且不在无测量带里**那些格子的平均温度。`null` = 这一片一个
   * 可用格子都没有（不是 0，也不是 NaN —— `allow_nan=False` 送不出 NaN）。
   *
   * ⚠️ **后端算的，前端不重算。** 三个坑（拱外是 NaN、z > 1.10 m 那一条是外推、
   * 平均必须在软单调投影之后取）少踩一个这个数就是错的，而屏上没有任何提示。
   * 口径的唯一来源是 `backend/api/routes/field.py::_mean_in_arch`。
   */
  mean: number | null
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
  /** 与 `SectionsPayload.mismatch_note` 同一个东西、同一个名字。 */
  mismatch_note: string
  /** 与那一族同名同物：成品读不动时后端给的那句话。 */
  artifact_note: string
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
  /**
   * 本载荷这些片**合起来**的拱内均温。**不是各片均值的平均** ——
   * 两者在等权时相等，而「等权」是一个会悄悄失效的前提。
   */
  mean: number | null
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

/* ------------------------------------------------------------------ *
 * 页② 第三段的精度面：`GET /api/calibration/diagnostics`
 *
 * ⚠️ 这一整块**不在标定包里**（裁定 C）：诊断是「包的函数」。
 * 所以它的出处图章是「算」（现场重算），不是「包」。
 * ------------------------------------------------------------------ */

/** 一个分箱。`at` 是横轴上的位置（小时 / 高度 / 棚长）。 */
export interface BinRow {
  /** ⚠️ 可以是 null。横轴值本身也是浮点，同样过 `_finite`。 */
  at: number | null
  /** 平均残差。整箱缺值时是 null —— 那一箱**留在表里**，不是被藏掉。 */
  mean: number | null
  /** 箱内**有限**样本数（NaN 不算样本）。 */
  n: number
  /** 平均残差的标准误，`n <= 1` 时是 null（一个点算不出标准误，报 0 是假装精确）。 */
  se: number | null
}

export interface ResidualPanel {
  key: 'diurnal' | 'height' | 'length'
  /** 后端拼好的标题，前端不拼显示字符串。 */
  label: string
  /** 纵轴永远是残差；这是横轴的名字（含单位）。 */
  axis: string
  /** ⚠️ 箱数由**这份数据的测点**决定：昼夜 24、高度 3、棚长 7。
   *  后两张不是曲线，是 3 根和 7 根柱子（规格书 §7.2）。 */
  bins: BinRow[]
}

export interface AccuracyBlock {
  /** 后端给的显示名。 */
  label: string
  /** ⚠️ 三个都是 `number | null`（`_finite` 把非有限浮点翻成 null）。 */
  mae: number | null
  rmse: number | null
  r2: number | null
  n: number
}

/**
 * 折外预测 vs 实测的二维直方图（规格书 §7.1）。
 *
 * **为什么不是散点**：两万七千对点画成散点是一团墨。计数矩阵让 y = x
 * 那条对角线看得见 —— 而那条线是这张图唯一要回答的东西。
 * 两个轴**共用 `[lo, hi]`**：它是 45 度对角线图，轴范围不同就不是了。
 */
export interface DensityPayload {
  bins: number
  /** ⚠️ 全为 null 表示**一对有限点都没有**（整段缺值）。 */
  lo: number | null
  hi: number | null
  n: number
  /** `counts[it][ip]`：实测落在第 it 格、预测落在第 ip 格的点数。行主序。 */
  counts: number[][]
}

export interface DiagnosticsPayload {
  present: boolean
  created_at: string
  groups_sig: string
  dataset_sig: string
  n_points: number
  n_sensors: number
  n_times: number
  density: DensityPayload
  /**
   * 基线与模型**永远并排**（规格书 §6.3）：单独一个 0.999 会被读成
   * 「几乎完美」，而它旁边那个基线才说明这把尺子有多粗。
   *
   * `folds` 是**基线算在哪几折上**，也就是模型 `metrics` 里 B 组那几折 ——
   * 两头必须同折、同数据段，否则两个数不可比。
   */
  accuracy: {
    folds: string[]
    baseline: AccuracyBlock
    model: AccuracyBlock
    /** `基线 MAE / 模型 MAE`。**算出来的，不是写死的**。 */
    ratio: number | null
  }
  /** 三项，次序即屏上的次序。 */
  residual: ResidualPanel[]
  /**
   * 后端**实际用的那套原始值**。不是给用户看的 —— 它是那条失效规则的凭据：
   * 屏上这套值与它不一致时，这一整块精度不作数（规格书 §四.3）。
   */
  params_used: Record<string, ParamValue>
  note: string
}

/**
 * 模型库里的一行。字段名与 `backend/api/models_store.py::ModelRow.to_dict()`
 * 逐字对应，另加两个**由后端按当前数据集算出来**的字段。
 */
export interface ModelRowPayload {
  id: number
  name: string
  /** ⚠️ 用户**点保存**的时刻。与详情里那个 `created_at`（标定跑完的时刻）
   *  不是一回事，平时只差几秒。页上写「保存于」。 */
  saved_at: string
  dataset_sig: string
  groups_sig: string
  data_file: string
  data_start: string
  data_end: string
  /** ⚠️ 三个都可以是 null（B 组一折都没算出有限值时）。null 是**后端承认的
   *  合法状态**，不是 0，也不是整行缺失 —— 与 `MetricRow` 同一条房规。 */
  mae: number | null
  rmse: number | null
  r2: number | null
  is_current: boolean
  /**
   * 能不能拿来给**当前**训练段构场 —— **只看特征组那一轴**。
   *
   * ⚠️ 它**不**表示「这一份就是为当前数据标的」（那是 `borrowed` 的事）。
   * 2026-10-10 用户裁定「模型不绑数据集」之后，数据集签名对不上**不再**
   * 拦着选：库里有就能挑。屏上因此是三档 —— 用不了 / 本地的 / 借来的。
   */
  compatible: boolean
  /**
   * 能用、但这一份的参数**不是**为当前这份数据标出来的（借来的）。
   * 用不了的行（`compatible === false`）恒为 false。
   */
  borrowed: boolean
  /** 说得出理由时那一句人话（借来的与用不了的都有）；两轴都对得上时是空串
   *  （不是 null —— 前端不用判两种空）。 */
  why: string
  /**
   * 这一行有没有**成品**（训练好的模型的字节，与包同生共死）。
   *
   * ⚠️ 有数据集时它与 `compatible` **无关** —— `compatible` 说的是特征组那一轴，
   * 成品让**参数**不再依赖数据，没让特征列不依赖。
   * **没有数据集**时它才是 `compatible` 的判据（后端 `routes/models.py`）。
   */
  has_artifact: boolean
}

export interface ModelsPayload {
  rows: ModelRowPayload[]
  /** 当前模型的行号。一行都没有、或一行都没标当前时是 null。 */
  current_id: number | null
  /** 当前数据集的文件名。列表上那两行「对不上」的理由由后端算好，
   *  这一格只是让前端有机会在页面上说清「在比的是哪一份」。
   *
   *  **没有数据集时是 null** —— 空串与「文件名恰好是空」在屏上长得一样。
   */
  dataset_file: string | null
  /** 同上：没有数据集时是 null（`is_current` 那一格不受影响）。 */
  dataset_sig: string | null
}

/**
 * 详情里那张逐折表的一行。
 *
 * ⚠️ **是别名，不是又抄一份接口**：`GET /api/models/{id}` 的 `metrics` 与
 * `/api/calibration` 的 `metrics` 是同一个 DataFrame 出来的同一组列
 * （后端 `models.py` 逐列原样转）。抄一份出来，两边就会各自漂 ——
 * 而漂的表现是某一页静默渲染 `undefined`，测试照样绿。
 */
export type ModelMetricRow = MetricRow

export interface ModelDetailPayload extends ModelRowPayload {
  /** ⚠️ **标定跑完**的时刻。`saved_at` 才是保存的时刻。 */
  created_at: string | null
  tool_version: string
  feature_groups: string[]
  trend_kind: string
  trend_params: Record<string, ParamValue>
  metric: { lx: number; ly: number; lz: number; power: number }
  cross_shed: boolean
  tuned_keys: string[]
  folds: string[]
  metrics: ModelMetricRow[]
  /** ⚠️ 整个块可以是 null；块里三个浮点也可以是 null（同 `CalibrationPayload.ab`）。 */
  ab: { mae_a: number | null; mae_b: number | null; gap: number | null } | null
  plateau: PlateauRow[]
  best: Record<string, ParamValue>
  n_trials: number
  seed: number
}
