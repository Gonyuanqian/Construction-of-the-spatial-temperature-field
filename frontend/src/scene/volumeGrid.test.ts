import { describe, expect, it } from 'vitest'
import { makeVolumePayload } from '../test/fixtures'
import { packVolume, definedAt, traceVolume } from './volumeGrid'

function cube() {
  const p = makeVolumePayload()
  p.x = [0, 1]; p.z = [0, 1]; p.stripes = []
  p.planes = [0, 1].map(y => ({ ...p.planes[0], y, values: [[10 + y, 20 + y], [30 + y, 40 + y]] }))
  return p
}
describe('体数据与连续拾取', () => {
  it('纹理按 x,z,y 打包，掩膜与有效温度分开保存', () => {
    const p = cube(), packed = packVolume(p)
    expect([...packed]).toEqual([10,1,20,1,30,1,40,1,11,1,21,1,31,1,41,1])
    p.stripes = [[1, 0]]
    expect(packVolume(p)[3]).toBe(0)
    p.planes[0].values[0][0] = null
    expect(packVolume(p)[1]).toBe(0)
  })
  it('有效空间在切面之间可以拾取，不吸附 y 或 x,z', () => {
    const p = cube()
    const hit = traceVolume(p, [-1, .4, .6], [1, 0, 0], 1)!
    expect(hit[0]).toBeCloseTo(0, 5)
    expect(hit[1]).toBe(.4); expect(hit[2]).toBe(.6)
  })
  it('刀口落在切片之间时拾取刀面，不返回背后已经切掉的点', () => {
    const p = cube()
    const hit = traceVolume(p, [.4, 2, .6], [0, -1, 0], .37)!
    expect(hit[1]).toBeCloseTo(.37, 5)
    expect(traceVolume(p, [.4, .6, .6], [1, 0, 0], .37)).toBeNull()
  })
  it('缺失角点不参与连续填充；精确有效节点不依赖零权重角点', () => {
    const p = cube()
    p.planes[1].values[1][1] = null
    const packed = packVolume(p)
    expect(definedAt(p, [.5, .5, .5], packed)).toBe(false)
    expect(definedAt(p, [0, 0, 0], packed)).toBe(true)
    expect(traceVolume(p, [-1, .5, .5], [1, 0, 0], 1)).toBeNull()
  })
  it('无测量带没有连续填充', () => {
    const p = cube(); p.stripes = [[0,1],[1,1]]
    expect(traceVolume(p, [-1, .5, .5], [1, 0, 0], 1)).toBeNull()
  })
  it('表面拾取穿过已隐藏的层，沿分界线的射线按可见层判定', () => {
    const p = cube()
    const layers = { cuts: [0.3, 0.7], visible: [false, true, false] } as const
    const hit = traceVolume(p, [.5, .5, 2], [0, 0, -1], 1, undefined, layers)
    expect(hit?.[2]).toBeCloseTo(0.7, 5)
    expect(traceVolume(p, [-1, .5, .7], [1, 0, 0], 1, undefined, layers)).toBeNull()
    expect(traceVolume(p, [-1, .5, .3], [1, 0, 0], 1, undefined, layers)?.[2]).toBeCloseTo(0.3, 5)
  })
})
