/**
 * 相机的手动微调：旋转 / 缩放 / 平移。
 *
 * **这一层只做算术，不碰 Three**（`VolumeScene.vue` 那一层照着结果摆相机）——
 * 与 `fit.ts` 同一条分工。jsdom 里没有 canvas/WebGL，画面本身拿不到任何自动
 * 证据（规格书 §8.2），所以能被断言的判断都搬到这里来：
 * 「转一圈回到原处」「推到头停在上下限」「正上方不许出 NaN」都在这里钉住。
 *
 * 坐标用**普通数组**而不是 `THREE.Vector3`：这一层因此可以在没有 WebGL 的
 * 进程里跑完（也正是它存在的前提）。数组的次序与 `fit.ts` 一致，是
 * `[x, y, z]` 的**世界**坐标。
 */
import { FIT_FOV_DEG } from './fit'

export type Vec3 = [number, number, number]

/** 一次「左转 / 右转」多少度。15 度是六个刻度转半圈 —— 手点得动，也看得出来。 */
export const YAW_STEP_DEG = 15
/** 一次「拉近」的倍率；推远是它的倒数。 */
export const ZOOM_STEP = 0.8
/** 一次平移走多少**画面高度**。0.12 大约是七八下走完一屏。 */
export const PAN_FRAC = 0.12
/**
 * 相机的距离上下限（米）。
 *
 * 棚是 18 m 长、2.1 × 1.3 m 粗的一根针。下限 0.5 m 是「贴着拱壳外面看」——
 * 再近就进到壳里，屏幕上是一片糊住的近裁剪面。上限 300 m 是「整根针缩成一个点」。
 */
export const MIN_DIST = 0.5
export const MAX_DIST = 300

const sub = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const add = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
const mul = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k]
const len = (a: Vec3): number => Math.hypot(a[0], a[1], a[2])
const clamp = (v: number, lo: number, hi: number): number =>
  Math.min(hi, Math.max(lo, v))

/** 绕世界竖直轴、以 `target` 为轴心把相机转 `deg` 度。`target` 不动。 */
export function yawAround(target: Vec3, position: Vec3, deg: number): Vec3 {
  const o = sub(position, target)
  const r = (deg * Math.PI) / 180
  const c = Math.cos(r)
  const s = Math.sin(r)
  return add(target, [o[0] * c - o[2] * s, o[1], o[0] * s + o[2] * c])
}

/**
 * 沿视线方向把相机挪到 `factor` 倍的距离上（`factor < 1` 是拉近）。
 * 距离夹在 `[MIN_DIST, MAX_DIST]` 之间 —— 推到头就停住，不会穿过棚体或者飞走。
 */
export function zoomBy(target: Vec3, position: Vec3, factor: number): Vec3 {
  const o = sub(position, target)
  const d = len(o)
  // 相机正好压在目标上时没有「视线的方向」可言。返回原处 —— 不是取巧：
  // 这一档下任何方向都一样错，而不动至少是个能画出来的画面。
  if (d < 1e-9) return position
  return add(target, mul(o, clamp(d * factor, MIN_DIST, MAX_DIST) / d))
}

/**
 * 在相机自己的右 / 上平面里平移。`dxFrac` / `dyFrac` 是**画面高度的比例**
 * （正值 = 向右 / 向上），两个方向同一把尺子 —— 于是屏幕上「走一样远」
 * 在两个方向上就是一样远，宽画布上不必再乘宽高比。
 *
 * 返回**两个**点：平移要让 `target` 与 `position` 一起动，只动相机就变成
 * 绕着看，那是旋转不是平移。
 */
export function panBy(
  target: Vec3, position: Vec3, dxFrac: number, dyFrac: number,
): { target: Vec3; position: Vec3 } {
  const o = sub(position, target)
  const d = len(o)
  if (d < 1e-9) return { target, position }

  // 视线方向取「相机 → 目标」，与 `fit.ts` 的 `f` 同一个约定。
  const f = mul(o, -1 / d)
  const flat = Math.hypot(f[0], f[2])
  // ⚠️ 右手系里屏幕的「右」是 `cross(f, 世界上)` —— 展开就是 `(−f.z, 0, f.x)`。
  // 计划给的是 `(f.z, 0, −f.x)`，**正好差一个负号**：那一个式子与它自己上面那句
  // 注释、与 `fit.ts:73` 的 `unit(cross(f, [0, 1, 0]))`、以及与它自己的测试
  // （「相机在 +Z 上朝 −Z 看，屏幕的右是世界 +X」）三处都对不上 ——
  // 正前方的相机按「右」按钮会往左走，按「上」也会往下走（`up` 跟着一起翻）。
  // 2026-10-09 实测：按计划原样写，测试 `moved[0]).toBeGreaterThan(0)` 当场红。
  const right: Vec3 = flat < 1e-6
    // ⚠️ **这一支不能省。** 视线与竖直轴平行时叉乘的模长趋零，归一化除出 NaN，
    // 整个画面变白而且不报错。相机在正上方俯视时屏幕的「右」本来就是世界 X。
    ? [1, 0, 0]
    : [-f[2] / flat, 0, f[0] / flat]
  const up: Vec3 = [
    right[1] * f[2] - right[2] * f[1],
    right[2] * f[0] - right[0] * f[2],
    right[0] * f[1] - right[1] * f[0],
  ]

  // 目标那一处，画面高度对应的世界长度。
  //
  // ⚠️ 视场角**从 `fit.ts` 拿**，不在这里再写一遍 38。计划给的是就地一个
  // `const FOV_DEG = 38`，并注明「与 `fit.ts` 的 `FIT_FOV_DEG`、`VolumeScene`
  // 建相机时用的是同一个数」—— 既然必须是同一个数，就只该有一处写着它。
  // 抄一份出来，改视场角那天平移会**静默**变快变慢（幅度不对，方向还对，
  // 屏上什么提示都没有）。`FIT_FOV_DEG` 已经是 `export` 的。
  const h = 2 * d * Math.tan((FIT_FOV_DEG * Math.PI) / 360)
  const shift = add(mul(right, dxFrac * h), mul(up, dyFrac * h))
  return { target: add(target, shift), position: add(position, shift) }
}
