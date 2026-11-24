import type { VolumePayload } from '../api/types'
import { isVisibleTemperatureHeight, type TemperatureLayers } from './volumeView'

export type Point3 = [number, number, number]

/** 只处理几何与有效掩膜，读数由后端同一网格插值。纹理顺序为 x,z,y。 */
export function packVolume(p: VolumePayload): Float32Array {
  const nx = p.x.length, nz = p.z.length
  const blocked = new Set(p.stripes.map(([x, z]) => z * nx + x))
  const out = new Float32Array(nx * nz * p.planes.length * 2)
  p.planes.forEach((plane, y) => plane.values.forEach((row, z) => row.forEach((v, x) => {
    const i = ((y * nz + z) * nx + x) * 2
    if (v !== null && Number.isFinite(v) && !blocked.has(z * nx + x)) {
      out[i] = v; out[i + 1] = 1
    }
  })))
  return out
}

function support(axis: number[], v: number): number[] {
  if (!Number.isFinite(v) || v < axis[0] - 1e-8 || v > axis[axis.length - 1] + 1e-8) return []
  const exact = axis.findIndex(x => Math.abs(x - v) <= 1e-8)
  if (exact >= 0) return [exact]
  const hi = axis.findIndex(x => x > v)
  return hi > 0 ? [hi - 1, hi] : []
}

/** 拾取与体绘制都不跨越缺失角点或无测量带。 */
export function definedAt(p: VolumePayload, point: Point3, packed: Float32Array): boolean {
  const [x, y, z] = point, nx = p.x.length, nz = p.z.length
  const xs = support(p.x, x), ys = support(p.planes.map(pl => pl.y), y), zs = support(p.z, z)
  return !!(xs.length && ys.length && zs.length) && ys.every(iy => zs.every(iz =>
    xs.every(ix => packed[((iy * nz + iz) * nx + ix) * 2 + 1] === 1)))
}

/** 数据坐标射线，定位第一个可查询位置；cutY 把剖切面作为真实入口。 */
export function traceVolume(p: VolumePayload, origin: Point3, direction: Point3,
                            cutY: number, packed = packVolume(p), layers?: TemperatureLayers): Point3 | null {
  const bottom = p.z[0], top = p.z[p.z.length - 1]
  if (!layers || layers.visible.every(Boolean)) return traceBand(p, origin, direction, cutY, packed, bottom, top)
  if (Math.abs(direction[2]) < 1e-12) {
    return isVisibleTemperatureHeight(origin[2], layers) ? traceBand(p, origin, direction, cutY, packed, bottom, top) : null
  }
  const edges = [bottom, ...layers.cuts, top]
  const order = direction[2] > 0 ? [0, 1, 2] : [2, 1, 0]
  for (const index of order) {
    if (!layers.visible[index]) continue
    const low = Math.max(bottom, edges[index])
    const high = Math.min(top, edges[index + 1])
    if (high <= low) continue
    const hit = traceBand(p, origin, direction, cutY, packed, low, high)
    if (hit) return hit
  }
  return null
}

function traceBand(p: VolumePayload, origin: Point3, direction: Point3,
                   cutY: number, packed: Float32Array, bottom: number, top: number): Point3 | null {
  const lo: Point3 = [p.x[0], p.planes[0].y, bottom]
  const hi: Point3 = [p.x[p.x.length - 1], Math.min(cutY, p.planes[p.planes.length - 1].y), top]
  let enter = 0, leave = Infinity
  for (let a = 0; a < 3; a++) {
    if (hi[a] < lo[a]) return null
    if (Math.abs(direction[a]) < 1e-12) {
      if (origin[a] < lo[a] || origin[a] > hi[a]) return null
    } else {
      const t0 = (lo[a] - origin[a]) / direction[a], t1 = (hi[a] - origin[a]) / direction[a]
      enter = Math.max(enter, Math.min(t0, t1)); leave = Math.min(leave, Math.max(t0, t1))
    }
  }
  if (!Number.isFinite(leave) || leave <= enter) return null
  const at = (t: number): Point3 => origin.map((v, a) => Math.min(hi[a], Math.max(lo[a], v + direction[a] * t))) as Point3
  const axes = [p.x, p.z, p.planes.map(pl => pl.y)]
  const spacings = axes.flatMap(axis => axis.slice(1).map((v, i) => v - axis[i])).filter(v => v > 0)
  const step = Math.min(...spacings) * 0.5
  if (!Number.isFinite(step) || step <= 0) return null
  let previous = enter
  for (let t = enter; t <= leave + step; t += step) {
    const current = Math.min(t, leave)
    // 单独有效的零厚度边界不构成可绘制体，向射线内侧探一点再判断。
    if (current < leave && definedAt(p, at(current), packed)
        && definedAt(p, at(Math.min(leave, current + 1e-6)), packed)) {
      let a = previous, b = current
      for (let i = 0; i < 20; i++) {
        const mid = (a + b) / 2
        if (definedAt(p, at(mid), packed)) b = mid
        else a = mid
      }
      return at(Math.min(leave, b + 1e-7))
    }
    previous = current
    if (current === leave) break
  }
  return null
}
