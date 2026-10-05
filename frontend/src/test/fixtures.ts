/**
 * 测试用的载荷夹具。**只有测试 import 它** —— 应用代码一行都不引，
 * 所以它不会进任何构建产物。
 *
 * 值这一块是 4×4、四种格子各占一角（拱外 / 拱外 / 斜纹 / 值），
 * 与 `charts/pick.test.ts` 的那个同一套形状。**它的不对称是承重的**：
 * 4×4 是方阵，若四行四列的数也对称，把 `values[iz][ix]` 写成 `values[ix][iz]`
 * 照样会全绿 —— 而图会整个转置。
 */
import type { VolumePayload } from '../api/types'

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
