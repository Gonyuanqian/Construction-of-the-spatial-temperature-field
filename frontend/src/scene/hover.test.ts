import { describe, expect, it } from 'vitest'

import { makeVolumePayload } from '../test/fixtures'
import { markerPoint, snapIndex, solveHover, type HoverHit } from './hover'

const XS = [0, 0.7, 1.4, 2.1]
const ZS = [0, 0.7, 1.4, 2.1]

const hit = (o: Partial<HoverHit> = {}): HoverHit => ({
  planeIndex: 0, x: 0.7, z: 0.7, clipped: false, ...o,
})

describe('吸收到最近的格点', () => {
  it('取最近的那一个', () => {
    expect(snapIndex(XS, 0.0)).toBe(0)
    expect(snapIndex(XS, 0.34)).toBe(0)
    expect(snapIndex(XS, 0.36)).toBe(1)
    expect(snapIndex(XS, 2.1)).toBe(3)
    expect(snapIndex([0, 1, 2], 1.9)).toBe(2)
  })

  it('平手时取小下标 —— 同一个位置问两次，不该换个答案', () => {
    expect(snapIndex([0, 1, 2], 0.5)).toBe(0)
  })

  it('范围之外给 null，**不从外面吸进来**（Review Focus 2）', () => {
    // 从外面吸进来是不行的：用户输 y = 100，会拿到 y = 18 那个位置的温度，
    // 而屏幕上写的还是「最近格点」，看不出问的不是同一件事。
    expect(snapIndex(XS, -0.01)).toBeNull()
    expect(snapIndex(XS, 2.11)).toBeNull()
    expect(snapIndex(XS, Number.NaN)).toBeNull()
    expect(snapIndex(XS, Number.POSITIVE_INFINITY)).toBeNull()
    expect(snapIndex(XS, Number.NEGATIVE_INFINITY)).toBeNull()
  })

  it('坐标数组本身就是载荷给的，不推间距', () => {
    // 间距是后端的参数（`GridSpec.dx`）。前端拿 `(v - x0) / dx` 去算下标，
    // 就是把后端的一个参数抄了第二遍 —— 而抄错一个数画出来的还是一张正常的图。
    // 这条用一个**不均匀**的数组钉住：推间距的实现在它上面会给出另一个答案。
    expect(snapIndex([0, 1, 1.1, 9], 1.05)).toBe(1)
  })
})

describe('悬停取的是最前面的可见片', () => {
  it('命中列的第一片照常读', () => {
    expect(solveHover([hit({ planeIndex: 4, x: 1.45, z: 0.66 })], XS, ZS))
      .toEqual({ planeIndex: 4, ix: 2, iz: 1 })
  })

  it('**前片被剖切刀切掉时读的是后面那一片**（Review Focus 1）', () => {
    // 规格书 §5.5：`THREE.Raycaster` 不认 `clippingPlanes` —— 交点列表里会带着
    // 已经切掉、屏幕上根本看不见的那一片。不自己滤的话，用户对着空处悬停，
    // 会得到一个温度，而那个温度来自一个不存在的面。
    // **这是这一版最容易出、又最难发现的一个错**：它不报错，只有错数。
    const hits = [
      hit({ planeIndex: 0, x: 0.0, z: 0.0, clipped: true }),
      hit({ planeIndex: 1, x: 1.4, z: 1.4, clipped: false }),
    ]
    expect(solveHover(hits, XS, ZS)).toEqual({ planeIndex: 1, ix: 2, iz: 2 })
  })

  it('命中点全被剖掉时什么也不报 —— 不给一个看不见的片的数', () => {
    expect(solveHover([hit({ clipped: true }), hit({ clipped: true })], XS, ZS)).toBeNull()
  })

  it('一片都没命中时返回 null（鼠标在棚外）', () => {
    expect(solveHover([], XS, ZS)).toBeNull()
  })

  it('命中点落在网格之外时返回 null，不吸到边上', () => {
    expect(solveHover([hit({ x: 9 })], XS, ZS)).toBeNull()
    expect(solveHover([hit({ z: -9 })], XS, ZS)).toBeNull()
  })

  it('x 与 z 各吸各的，不串位', () => {
    // 命中点 (1.4, 0.7)：x 吸到下标 2，z 吸到下标 1。
    // 若把两个轴接反，这条立刻红 —— 而画面上的记号还是照常画在某个格点上。
    expect(solveHover([hit({ x: 1.4, z: 0.7 })], XS, ZS)).toEqual({ planeIndex: 0, ix: 2, iz: 1 })
  })
})

describe('标记与读数同源', () => {
  it('画在那个格点上，坐标就是读数里报的那三个', () => {
    // 标记位置由**同一份** (planeIndex, ix, iz) 推出来 —— 分开算的话，
    // 记号会画在某一格，读数报的是另一格，而两边看起来都正常。
    const p = makeVolumePayload()
    expect(markerPoint(p, { planeIndex: 1, ix: 2, iz: 3 })).toEqual([1.4, 3.5, 2.1])
    expect(markerPoint(p, { planeIndex: 0, ix: 0, iz: 0 })).toEqual([0, 3, 0])
  })
})
