/**
 * 三维悬停的解算：光线命中的交点 → 场上的格点下标。
 *
 * **抽成纯函数**，因为它一次都不碰 Three、不碰 WebGL —— 而三维画面本身
 * 拿不到任何自动证据（jsdom 没有 canvas/WebGL）。这是三维里信息最密、
 * 也是唯一能被证明的一块逻辑，所以它必须住在 Three 之外。
 *
 * 画的那一半（建几何、射线、贴纹理）在 `VolumeScene.vue`，那里面
 * **不许再出现一个判断**。
 */
import type { VolumePayload } from '../api/types'

export interface HoverHit {
  planeIndex: number
  /** 命中点的**数据坐标**：x 是棚长、z 是高度。**不是** Three 的世界坐标。 */
  x: number
  z: number
  /**
   * 被剖切刀切掉了。**这一位必须由调用方算** —— `THREE.Raycaster` 不认
   * `clippingPlanes`，不自己滤的话会报一个已经切掉、根本看不见的片上的数，
   * 而用户对着空处得到了一个温度（规格书 §5.5）。
   */
  clipped: boolean
}

export interface HoverPick {
  planeIndex: number
  ix: number
  iz: number
}

/**
 * 吸收到最近的格点。**落在 `[coords[0], coords[n-1]]` 之外返回 null。**
 *
 * 从外面吸进来是不行的（Review Focus 2）：用户输 y = 100，会拿到 y = 18 那个
 * 位置的温度，而屏幕上写的还是「最近格点」—— 一个不是他问的答案，看起来
 * 却完全正常。所以范围之外**什么都不报**，由调用方说清范围是多少。
 *
 * 范围与"最近"都只读**载荷自己给的坐标数组**，不推间距 —— 间距是
 * `GridSpec.dx`，是后端的参数，在前端重抄一遍就是把它抄了第二遍。
 */
export function snapIndex(coords: number[], v: number): number | null {
  const lo = coords[0]
  const hi = coords[coords.length - 1]
  if (!(v >= lo && v <= hi)) return null      // NaN 与 ±Infinity 也走这一支
  let best = 0
  for (let i = 1; i < coords.length; i++) {
    // 严格小于：平手时取小下标 —— 同一个位置问两次，答案不该变。
    if (Math.abs(coords[i] - v) < Math.abs(coords[best] - v)) best = i
  }
  return best
}

/**
 * 命中列 → 一个格点。
 *
 * **不能按屏幕距离找最近的格点。** 相机大致朝 y 看时，前壁与后壁上的点常常
 * 只差几个像素，鼠标一动数字就在棚前棚后之间乱跳 —— 那不是灵敏，是读数不可信。
 * 所以要的是「最前面那一片上、离命中点最近的格点」（规格书 §6.1）。
 *
 * `hits` 必须**按光线走向排好（近到远）** —— Three 的 `intersectObjects`
 * 就是这个次序，调用方直接传进来即可。
 */
export function solveHover(hits: HoverHit[], xs: number[], zs: number[]): HoverPick | null {
  const front = hits.find((h) => !h.clipped)
  if (!front) return null                        // 全被剖掉了：什么也不报
  const ix = snapIndex(xs, front.x)
  const iz = snapIndex(zs, front.z)
  if (ix === null || iz === null) return null
  return { planeIndex: front.planeIndex, ix, iz }
}

/**
 * 记号画在**哪个格点**上，用**数据坐标** `[x, y, z]` 给出。
 *
 * 与读数同源（同一次 `HoverPick`）：分开算的话，记号会画在某一格、
 * 面板报的是另一格，而两边看起来都正常。
 */
export function markerPoint(
  payload: VolumePayload, pick: HoverPick,
): [number, number, number] {
  return [payload.x[pick.ix], payload.planes[pick.planeIndex].y, payload.z[pick.iz]]
}
