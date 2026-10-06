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
  LiveFramePayload, LiveStatus, SectionShed, SectionsPayload, VolumePayload,
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
    y_step: 0.5, y_min: 0, y_max: 18,
    x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 2,
    vmin: 0, vmax: 5,
    x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
    arch: [[0, 0], [2.1, 0]],
    sheds: [{ id: 'p1', y: 3 }, { id: 'p2', y: 9 }, { id: 'p3', y: 15 }],
    sensors: [{ id: 'x0.7_z0.7', x: 0.7, z: 0.7, layer: 'z0.7' }],
    available_sheds: ['p1', 'p2', 'p3'],
    stripes: STRIPES,
    planes: [
      { y: 3, measured: true, shed: 'p1', values: makeValues() },
      { y: 3.5, measured: false, shed: null, values: makeValues() },
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
    groups_sig: null, dataset_sig: 's', feature_groups: [], trend_kind: 'xgboost',
    tuned_keys: [], params: [], plateau: [], lz_note: null,
    metrics: [], per_point: [], ab: null, fold_kind: null, n_folds: 0,
    worst_fold: null, ab_note: '', note: '兜底参数不是最优',
  },
  // 实时那一屏（`/live` 不进 NAV_ITEMS，逐页循环扫不到它）。**两条都给**：
  // 只给 status 的话，状态条一准备好页面就去取帧、拿到 404，帧那一块
  // （气象、24 路读数、分级那几句）根本渲染不出来。
  '/api/live/status': makeLiveStatus({ state: 'ready', running: false, cursor: 3, total: 144 }),
  '/api/live/frame/': makeLiveFramePayload(),
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
