/**
 * 测试用的载荷夹具。**只有测试 import 它** —— 应用代码一行都不引，
 * 所以它不会进任何构建产物。
 *
 * 值这一块是 4×4、四种格子各占一角（拱外 / 拱外 / 斜纹 / 值），
 * 与 `charts/pick.test.ts` 的那个同一套形状。**它的不对称是承重的**：
 * 4×4 是方阵，若四行四列的数也对称，把 `values[iz][ix]` 写成 `values[ix][iz]`
 * 照样会全绿 —— 而图会整个转置。
 */
import type {
  LiveFramePayload, LiveStatus, ModelDetailPayload, ModelsPayload,
  SectionShed, SectionsPayload, VolumePayload,
} from '../api/types'

export function makeValues(): (number | null)[][] {
  return [
    [1, 2, 3, 4],          // iz = 0
    [1, 2, 3, 4],          // iz = 1
    [null, 2, 3, 4],       // iz = 2
    [null, null, 3, 4],    // iz = 3
  ]
}

/** 斜纹格：[ix, iz]。 */
export const STRIPES: [number, number][] = [[2, 0], [2, 1], [2, 2], [2, 3], [3, 2], [3, 3]]

/** 两片的一小卷：第 0 片是实测断面，第 1 片是混合出来的。 */
export function makeVolumePayload(over: Partial<VolumePayload> = {}): VolumePayload {
  return {
    t_index: 12, time: '2026-07-23T12:00:00', n_times: 1308,
    preset: 'standard', monotonic: true, calibrated: true,
    // 空串 = 这一份包就是为当前训练段标的。夹具里**默认是「本地的」** ——
    // 「借来的」那一句由各页自己的用例按需换上去（`calibratedLabel` 读的
    // 正是这个字段在不在）。
    mismatch_note: '',
    // 成品读不动那一句。**常态是空串**（成品都在、都读得动）；那一条由
    // 各页自己的用例按需换上去。
    artifact_note: '',
    y_step: 0.5, y_min: 0, y_max: 18,
    x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 2,
    vmin: 0, vmax: 5,
    // ⚠️ 26.5 而不是 `bg_temp` 那个 28.4：拱内均温本来就低于棚顶气温
    // （拱外是 NaN、顶部那条外推带又不算）。两个数相等会让「拿气温冒充均温」
    // 这条错法在测试里消失 —— 而它正是页⑤ 指标卡上最可能犯的错。
    mean: 26.5,
    x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
    arch: [[0, 0], [2.1, 0]],
    sheds: [{ id: 'p1', y: 3 }, { id: 'p2', y: 9 }, { id: 'p3', y: 15 }],
    sensors: [{ id: 'x0.7_z0.7', x: 0.7, z: 0.7, layer: 'z0.7' }],
    available_sheds: ['p1', 'p2', 'p3'],
    stripes: STRIPES,
    planes: [
      { y: 3, measured: true, shed: 'p1', values: makeValues(), mean: 26.5 },
      { y: 3.5, measured: false, shed: null, values: makeValues(), mean: 26.5 },
    ],
    elapsed_ms: 1250, note: '',
    ...over,
  }
}

/** **默认是「还没准备」** —— 替身不能一上来就是 ready，见 `LiveView.test.ts` 那段。 */
export function makeLiveStatus(over: Partial<LiveStatus> = {}): LiveStatus {
  return { state: 'idle', running: false, cursor: 0, total: 144, interval_s: 300, ...over }
}

/**
 * 断面载荷的夹具。
 *
 * ⚠️ **仓里原本没有这个导出** —— 断面载荷的工厂是 `sectionField.test.ts` 与
 * `pick.test.ts` 里**各自私有**的 `makePayload()`。这里往共享夹具里补一个，
 * 而不是把那两个私有的搬出来（那会牵动两个既有测试文件）。
 * 形状照 `api/types.ts` 的 `SectionsPayload` 与 `routes/field.py` 的实际键名
 * （`shed` / `y` / `values` / `stripes`）。
 */
export function makeSectionsPayload(over: Partial<SectionsPayload> = {}): SectionsPayload {
  const one = (shed: string, y: number): SectionShed =>
    ({ shed, y, values: makeValues(), stripes: STRIPES })
  return {
    t_index: 0, time: '2026-07-27T12:00:00', n_times: 1164,
    preset: 'standard', monotonic: true, calibrated: true,
    // 与 `makeVolumePayload` 同：空串 = 本地的。见那里的注释。
    mismatch_note: '',
    artifact_note: '',
    vmin: 0, vmax: 5, max_measured_z: 2,
    x_min: 0, x_max: 2.1, z_max: 1.3017,
    x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
    arch: [[0, 0], [2.1, 0]],
    sensors: [{ id: 'x0.7_z0.7', x: 0.7, z: 0.7, layer: 'z0.7' }],
    sheds: [one('p1', 3), one('p2', 9), one('p3', 15)],
    note: '',
    ...over,
  }
}

export function makeLiveFramePayload(over: Partial<LiveFramePayload> = {}): LiveFramePayload {
  const base = makeSectionsPayload()
  return {
    ...base,
    frame: {
      n: 0, time: '2026-07-27T12:00:00',
      bg_temp: 28.4, bg_rh: 61.0, bg_light: 780.0,
      sensor_temps: Array.from({ length: 24 }, () => 26.5),
    },
    live: { cursor: 0, running: true, interval_s: 300, total: 144 },
    ...over,
  }
}


/**
 * 每个接口的**最小可用载荷**，按路径前缀索引。
 *
 * **为什么是共享的**：`routes.smoke.test.ts` 与 `App.test.ts` 都要把整个外壳
 * （进而把某一页）挂起来，而挂起来就会取数。两份各写一遍的话，后写的那份
 * 一定会少一两个字段 —— 而缺字段的表现是**某页在渲染中途抛**，报错离「少了一个
 * mock 字段」这件事很远（`DataView.test.ts` 顶部记过同一个坑）。
 *
 * 取值的原则是「**能让每一页不抛就算数**」，不是「像真的」：这一组要测的是
 * 外壳与路由，不是任何一页的内容。
 *
 * ⚠️ `/api/dataset` 在这张表里是 **200**（「在用一份数据集」）。空态那几条用例
 * 由 `App.test.ts` 自己覆盖成 409/500 —— 它要的正是这个开关。
 */
/**
 * 模型库列表的载荷。**三行，正好是屏上那三档**（2026-10-10 用户裁定
 * 「模型不绑数据集」之后的一档新的）：
 *
 *   1. 本地的 —— 两轴都对得上，就是它；
 *   2. 借来的 —— 特征组对得上、数据集签名不是这一份。**能用**（`compatible`
 *      **只看特征组那一轴**），只是要标出来：它的误差数不是这份数据的成绩；
 *   3. 用不了的 —— 特征组都对不上，是**输入类型**不对，`disabled`。
 *
 * ⚠️ **第一行必须是 `compatible: true` 且 `current_id: 1`。** 它是**全站默认**
 * 的「有一个能用的模型」—— 页③ 与页⑤ 现有的那一批用例都靠它才继续走到
 * 「画场」那条路。想测「一个能用的模型都没有」的，在用例里自己换一份
 * （`vi.stubGlobal('fetch', ...)`），别改这里。
 *
 * ⚠️ **第三行不能删。** 有了它「哪些能用」这件事在默认载荷里才有一行反例可看
 * （`usableModels` 正是靠它才不是恒等式）。第二行原先兼着这个角色 —— 改档之后
 * 它自己能用了，这个角色必须换一行来当，否则 `filter(r => r.compatible)` 写成
 * `(p.rows ?? [])` 也照样全绿。
 *
 * 两条 `why` 都逐字取自后端 `api/deps.py` 的 `_GROUPS_WHY` 与那句话的模板：
 * 夹具里自己编一句，就等于前端测试钉的是一句后端永远不产出的话。
 *
 *   `has_artifact` 与 `compatible` 是**两轴**：第三行用不了是因为特征组，
 *   不是因为没有成品。所以三行都是 true —— 要让「没有成品」这一档可测，
 *   由用例自己 push 一行，不要改这三行（它们被多处用例当基线用）。
 */
export function makeModelsPayload(): ModelsPayload {
  return {
    current_id: 1,
    dataset_file: '人参棚_原始.xlsx',
    dataset_sig: '0066856dc40a8bbc-h20260727T1200',
    rows: [
      {
        id: 1, name: '七月下旬那套',
        saved_at: '2026-10-08T09:12:33',
        dataset_sig: '0066856dc40a8bbc-h20260727T1200',
        groups_sig: 'd6294c09',
        data_file: '人参棚_原始.xlsx',
        data_start: '2026-07-23T11:00:00', data_end: '2026-07-27T11:55:00',
        mae: 0.1685, rmse: 0.2537, r2: 0.9987,
        is_current: true, compatible: true, borrowed: false, why: '',
        has_artifact: true,
      },
      {
        id: 2, name: '上一份数据训的',
        saved_at: '2026-10-07T18:40:02',
        dataset_sig: 'ffffffffffffffff-h20260727T1200',
        groups_sig: 'd6294c09',
        data_file: '别人家的棚.xlsx',
        data_start: '2026-07-23T11:00:00', data_end: '2026-07-27T11:55:00',
        mae: 0.2210, rmse: 0.3104, r2: 0.9971,
        is_current: false, compatible: true, borrowed: true,
        why: '数据来源不同：别人家的棚.xlsx',
        has_artifact: true,
      },
      {
        id: 3, name: '另一个特征组标的',
        saved_at: '2026-10-06T11:02:47',
        dataset_sig: '0066856dc40a8bbc-h20260727T1200',
        groups_sig: '0badc0de',
        data_file: '人参棚_原始.xlsx',
        data_start: '2026-07-23T11:00:00', data_end: '2026-07-27T11:55:00',
        mae: 0.4402, rmse: 0.6019, r2: 0.9931,
        is_current: false, compatible: false, borrowed: false,
        why: '这一份是用别的特征组标出来的',
        has_artifact: true,
      },
    ],
  }
}

export function makeModelDetailPayload(): ModelDetailPayload {
  const row = makeModelsPayload().rows[0]
  return {
    ...row,
    created_at: '2026-10-08T09:12:28',
    tool_version: '0.1.0',
    feature_groups: ['coord', 'zbasis', 'meteo', 'interaction'],
    trend_kind: 'xgboost',
    trend_params: { max_depth: 5, learning_rate: 0.05, n_estimators: 300 },
    metric: { lx: 1, ly: 1, lz: 1, power: 2 },
    cross_shed: true,
    tuned_keys: ['metric.power', 'metric.lx', 'metric.lz', 'cross_shed',
      'trend.max_depth', 'trend.learning_rate', 'trend.n_estimators'],
    folds: ['position:x0.15_z0.4', 'position:x0.4_z0.7'],
    metrics: [
      { fold: 'position:x0.15_z0.4', fold_kind: 'position', region: '切面内',
        group: 'A', tag: '调参组', n: 1308, mae: 0.0812, rmse: 0.1103, r2: 0.9996 },
      { fold: 'position:x1.05_z0.7', fold_kind: 'position', region: '切面内',
        group: 'B', tag: '报告组', n: 1308, mae: 0.1376, rmse: 0.1809, r2: 0.9993 },
    ],
    ab: { mae_a: 0.0812, mae_b: 0.1685, gap: -0.0873 },
    plateau: [{ dim: 'metric.power', lo: '1.5', hi: '2.5' }],
    best: { 'metric.power': 2, 'trend.max_depth': 5 },
    n_trials: 40,
    seed: 0,
  }
}

export const PAGE_PAYLOADS: Record<string, unknown> = {
  '/api/health': { status: 'ok', version: '0.1.0' },
  '/api/dataset': {
    signature: 's', file: 'f.xlsx', n_times: 1, n_columns: 1,
    time_start: 't', time_end: 't',
    sheds: { p1: 3 }, positions: [], point_codes: {}, temperature: [],
    fix: { n_rows: 1, fixed_indices: [], monotonic_before: true,
           monotonic_after: true, spacing_seconds: 300, n_gaps: 0 },
    checks: [], checks_note: '',
  },
  '/api/field/arch': {
    x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 1.1,
    arch: [[0, 0.4535]], sheds: [{ id: 'p1', y: 3 }],
  },
  '/api/dataset/timeseries': {
    n_times: 0, time: [], bg_temp: [], sensors: {}, shed_mean: {},
    detrended: {}, detrended_mean: {}, detrended_domain: [-3, 3], note: '',
  },
  '/api/dataset/layer-timeheight': {
    step: 1, n_times: 0, n_columns: 0, time: [], x_label: '', source: '', sheds: {},
  },
  '/api/features': {
    default_groups: [], groups: [], all_columns: [],
    // 后端给的全列计数。前端不许用 `all_columns.length` 自己数，
    // 所以 mock 里也必须给 —— 缺了它页面会静默渲染 `undefined`，
    // 而测试照样绿。这里与 `all_columns: []` 自洽：并集长度 0。
    n_all_columns: 0,
    notes: [],
  },
  '/api/calibration': {
    present: false, reason: '还没有标定包', created_at: null, tool_version: null,
    // 与上面 `n_all_columns` 同一个坑：这一格后端**两个分支都给**，
    // 缺了它页② 会静默渲染 `undefined`，而冒烟测试照样绿。
    mismatch: null,
    // 这一份是空态（`present: false`），所以来路是 null。
    // ⚠️ 同样是「两个分支都给」的那一格：缺了它页② 那排图章会静默
    // 渲染成 `undefined`，而冒烟测试照样绿。
    source: null,
    // 没标过 → 就没有「借来的」这回事。⚠️ 这一格与上面的 `mismatch`
    // **不是一回事**（见 `types.ts` 那段）。
    mismatch_note: '',
    artifact_note: '',
    groups_sig: null, dataset_sig: 's', feature_groups: [], trend_kind: 'xgboost',
    // 真实后端在空态下也发 8 + 4 行（`_panel` 与盘上有没有包无关）；
    // 这里给空数组，是为了让冒烟测试不依赖那十二个值 —— 面板的行怎么渲染
    // 由 `ParamPanel.test.ts` 与 `TrainView.test.ts` 兜着，不是这里。
    panel: { trend: [], idw: [], fixed: [] },
    plateau: [], lz_note: null,
    metrics: [], per_point: [], ab: null, fold_kind: null, n_folds: 0,
    worst_fold: null, ab_note: '', note: '兜底参数不是最优',
  },
  // 实时那一屏（`/live` 不进 NAV_ITEMS，逐页循环扫不到它）。**两条都给**：
  // 只给 status 的话，状态条一准备好页面就去取帧、拿到 404，帧那一块
  // （气象、24 路读数、分级那几句）根本渲染不出来。
  '/api/live/status': makeLiveStatus({ state: 'ready', running: false, cursor: 3, total: 144 }),
  '/api/live/frame/': makeLiveFramePayload(),
  // 次序无所谓：`matchPayload` 按前缀**长度从长到短**匹配，`/api/models/1`
  // 会赢过 `/api/models`（这个文件头那段注释说的就是这件事）。
  '/api/models': makeModelsPayload(),
  '/api/models/1': makeModelDetailPayload(),
}

/**
 * 按**最长前缀**匹配回答的路径表查找。
 *
 * ⚠️ 用 `find` 而不用最长匹配的话，`/api/dataset` 会把
 * `/api/dataset/timeseries` 与 `/api/dataset/layer-timeheight` 一起吃掉 ——
 * 图表构造器里再报错，离现场很远。
 */
export function matchPayload(url: string,
                             table: Record<string, unknown> = PAGE_PAYLOADS): unknown | undefined {
  const key = Object.keys(table)
    .filter((k) => url.includes(k))
    .sort((a, b) => b.length - a.length)[0]
  return key ? table[key] : undefined
}
