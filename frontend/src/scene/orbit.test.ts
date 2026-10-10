/**
 * 视角微调的算术。**这一层只做算术，不碰 Three** —— 与 `fit.ts` 同一条分工：
 * jsdom 里没有 canvas/WebGL，画面本身拿不到任何自动证据，所以能被断言的
 * 判断都搬到这里来。
 */
import { describe, expect, it } from 'vitest'

import { MAX_DIST, MIN_DIST, PAN_FRAC, YAW_STEP_DEG, panBy, yawAround, zoomBy,
         type Vec3 } from './orbit'

const len = (v: Vec3) => Math.hypot(v[0], v[1], v[2])
const near = (a: number, b: number) => Math.abs(a - b) < 1e-9

describe('视角微调', () => {
  it('旋转：轴心不动，到轴心的距离不变，高度不变', () => {
    const t: Vec3 = [1, 0.6, 9]
    const p: Vec3 = [5, 4, 14]
    const q = yawAround(t, p, YAW_STEP_DEG)
    expect(q[1], '高度被转了').toBeCloseTo(p[1], 12)
    expect(len([q[0] - t[0], q[1] - t[1], q[2] - t[2]])).toBeCloseTo(len([p[0] - t[0], p[1] - t[1], p[2] - t[2]]), 9)
    expect(near(q[0], p[0]) && near(q[2], p[2]), '转了 15 度却一个坐标都没动').toBe(false)
  })

  it('旋转：转一整圈回到原处', () => {
    const t: Vec3 = [0, 0, 0]
    const p: Vec3 = [3, 2, 4]
    let q = p
    for (let i = 0; i < 24; i++) q = yawAround(t, q, 15)
    for (const i of [0, 1, 2] as const) expect(q[i]).toBeCloseTo(p[i], 9)
  })

  it('缩放：拉近就是更近，推远就是更远，方向不变', () => {
    const t: Vec3 = [0, 0, 0]
    const p: Vec3 = [0, 0, 20]
    const inAt = zoomBy(t, p, 0.8)
    expect(len(inAt)).toBeCloseTo(16, 9)
    expect(len(zoomBy(t, p, 1 / 0.8))).toBeCloseTo(25, 9)
    // 方向不变：三个分量同比。
    expect(inAt[2] / p[2]).toBeCloseTo(len(inAt) / len(p), 12)
  })

  it('缩放：距离夹在上下限里，推到头也不会穿过棚体或飞走', () => {
    // 棚是 18 m 长、1.3 m 高的一根针。不夹的话「拉近」按几下就进到拱壳里面，
    // 屏幕上是一片糊住的近裁剪面；「推远」几下就剩一个点。
    const t: Vec3 = [0, 0, 0]
    let p: Vec3 = [0, 0, 20]
    for (let i = 0; i < 60; i++) p = zoomBy(t, p, 0.8)
    expect(len(p)).toBeCloseTo(MIN_DIST, 9)
    for (let i = 0; i < 120; i++) p = zoomBy(t, p, 1.25)
    expect(len(p)).toBeCloseTo(MAX_DIST, 9)
  })

  it('平移：目标与相机一起动，两者的相对关系不变', () => {
    const t: Vec3 = [0, 0, 9]
    const p: Vec3 = [0, 0, 20]
    const r = panBy(t, p, PAN_FRAC, 0)
    // ⚠️ 计划这里是 `const moved = […]` —— 推断出来是 `number[]`，而 `len` 要
    // `Vec3`，`vue-tsc` 当场 TS2345（`npx vitest run` 不做类型检查，看不出来）。
    const moved: Vec3 = [r.target[0] - t[0], r.target[1] - t[1], r.target[2] - t[2]]
    expect(len(moved), '一步都没走').toBeGreaterThan(0)
    // 一起动：两点之间的距离与方向都不变（平移就是平移，不是绕圈）。
    expect(len([r.position[0] - r.target[0], r.position[1] - r.target[1], r.position[2] - r.target[2]]))
      .toBeCloseTo(len([p[0] - t[0], p[1] - t[1], p[2] - t[2]]), 9)
    // 相机在 +Z 上朝 −Z 看，屏幕的「右」是世界 +X。
    expect(moved[0]).toBeGreaterThan(0)
    expect(Math.abs(moved[1])).toBeLessThan(1e-9)
    expect(Math.abs(moved[2])).toBeLessThan(1e-9)
  })

  it('平移：相机在正上方俯视时不许出 NaN', () => {
    // ⚠️ Review Focus 第 4 条。视线与竖直轴**平行**时叉乘的模长是 0，
    // 归一化除出 NaN —— 相机坐标变成 NaN 之后整个画面变白，**不报错**。
    // 这一档的「屏幕右」没有唯一解，取世界 X 轴（相机在正上方时它本来就是右）。
    const r = panBy([0, 0, 0], [0, 60, 0], PAN_FRAC, 0)
    for (const v of [...r.target, ...r.position]) expect(Number.isFinite(v)).toBe(true)
    expect(r.target[0], '正上方时一步都没走').not.toBe(0)
  })

  it('三个退化输入都不炸：相机压在目标上、距离为 0', () => {
    const t: Vec3 = [1, 2, 3]
    // ⚠️ 计划这里直接把 `yawAround` 本身放进数组、然后 `f(t, t)` 调它 —— 少给一个
    // 角度，`deg` 是 `undefined`，`(undefined * π) / 180` 是 NaN，三个分量全是
    // NaN，这条测试会以「退化输入不炸」为名红在一个**非退化**的理由上
    // （而且两种函数签名混在一个数组里，`vue-tsc` 也会当场报 TS2554）。
    // 两个都包一层箭头函数，签名齐了、角度也给了。
    for (const f of [(a: Vec3, b: Vec3) => yawAround(a, b, YAW_STEP_DEG),
                     (a: Vec3, b: Vec3) => zoomBy(a, b, 0.8)]) {
      for (const v of f(t, t)) expect(Number.isFinite(v)).toBe(true)
    }
    const r = panBy(t, t, PAN_FRAC, 0)
    for (const v of [...r.target, ...r.position]) expect(Number.isFinite(v)).toBe(true)
  })
})
