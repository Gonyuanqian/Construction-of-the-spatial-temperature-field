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
