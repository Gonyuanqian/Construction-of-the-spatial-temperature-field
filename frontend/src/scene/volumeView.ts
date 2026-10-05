/**
 * 三维场景的**描述对象**：哪一片什么透明度、空腔在哪、棚壳多长、测点画在哪几座棚上。
 *
 * 与页③ 把 ECharts option 做成纯函数同一个手法 —— `VolumeScene.vue` 那一层
 * 只负责照着它建几何，**不做任何判断**。这样「混合片确实在变透」「空腔确实
 * 没填色」「测点只画在有样本的棚上」这三条**能被断言**，而画面本身不能
 * （jsdom 没有 canvas/WebGL，规格书 §8.2）。
 */
import type { VolumePayload } from '../api/types'

/** 拱壳沿 y 的示意长度 / m。数据集没给棚的实际长度，这个数只影响几何。 */
export const SHELL_LENGTH_DEFAULT = 4.0
export const SHELL_LENGTH_MIN = 1.0
export const SHELL_LENGTH_MAX = 6.0

export const SHELL_NOTE =
  '拱壳按拱形截面示意，长度由滑块给出：数据集没有给出棚的实际长度，' +
  '不能读成「测了这么长」。'

/** 每远离实测断面一米，混合片多透这么多。 */
const OPACITY_DROP = 0.22
/**
 * 透明度**下界**。没有它，离实测断面最远的那些片会淡到看不见 ——
 * 那是另一种谎：把「有一片场」变成「没有场」，和把混合画成实测一样坏（规格书 §5.3）。
 */
const OPACITY_FLOOR = 0.15

export interface PlaneSpec {
  planeIndex: number
  y: number
  /** 实测断面（**后端判定**）；混合出来的逐层变透。 */
  measured: boolean
  shed: string | null
  /** 实测片 1.0（实心）；混合片按到最近实测片的距离变透，有下界。 */
  opacity: number
}

export interface SensorShedSpec {
  shed: string
  /** 这一座棚在 y 上的位置。 */
  y: number
  /** 棚截面内的测点（x, z）。每座棚一套，布局相同。 */
  points: { x: number; z: number }[]
}

export interface VolumeSpec {
  planes: PlaneSpec[]
  /** 拱壳沿 y 的示意长度（滑块当前值）。**只改几何、不改场。** */
  shellLength: number
  /** 拱截面折线，**来自载荷** —— 前端不重算 z(x) = √(R² − (x − Xc)²) + K。 */
  arch: [number, number][]
  /** 哪几个 y 上立拱壳。载荷给的几座棚各一个，与换折无关。 */
  shellYs: number[]
  /** 测点只画在 `available_sheds` 里那几座棚上。 */
  sensorSheds: SensorShedSpec[]
  /** 无测量带的格子下标，全片共用。三维里**不填色**（拱顶下留一层看得见的空）。 */
  cavity: [number, number][]
  vmin: number
  vmax: number
  shellNote: string
}

export function buildVolumeSpec(payload: VolumePayload, shellLength: number): VolumeSpec {
  const measuredYs = payload.planes.filter((p) => p.measured).map((p) => p.y)

  /**
   * 到最近实测片的距离。
   *
   * **一片实测都没有时 `Math.min()` 给 `Infinity`** —— 于是下面那条式子自然
   * 落到下界，不是特判，而是同一个式子的退化端点。这一点很重要：`Infinity`
   * 与 `NaN` 只差一步，而一个 `NaN` 透明度会让整片场静默消失。
   */
  const nearestMeasured = (y: number): number =>
    Math.min(...measuredYs.map((m) => Math.abs(y - m)))

  const opacityOf = (y: number): number =>
    Math.min(1, Math.max(OPACITY_FLOOR, 1 - OPACITY_DROP * nearestMeasured(y)))

  const avail = new Set(payload.available_sheds)

  return {
    planes: payload.planes.map((p, i) => ({
      planeIndex: i,
      y: p.y,
      measured: p.measured,
      shed: p.shed,
      opacity: opacityOf(p.y),
    })),
    shellLength,
    arch: payload.arch,
    shellYs: payload.sheds.map((s) => s.y),
    sensorSheds: payload.sheds
      .filter((s) => avail.has(s.id))
      .map((s) => ({
        shed: s.id,
        y: s.y,
        points: payload.sensors.map((sn) => ({ x: sn.x, z: sn.z })),
      })),
    cavity: payload.stripes,
    vmin: payload.vmin,
    vmax: payload.vmax,
    shellNote: SHELL_NOTE,
  }
}
