import { describe, it, expect } from 'vitest'
import { makeVolumePayload } from '../test/fixtures'
import { solidSurface } from './solidSurface'

function sample() {
  const payload = makeVolumePayload()
  payload.x = [0,1]; payload.z = [0,1]
  payload.planes = [0,1,2].map(y => ({ ...payload.planes[0], y, values: [[20+y,20+y],[20+y,20+y]] }))
  return payload
}
describe('连续温度外表面', () => {
  it('相邻单元只生成外表面，不保留内部公共切面', () => {
    const result = solidSurface(sample(), new Set())
    expect(result.temperatures).toHaveLength(60)
    expect(result.positions).toHaveLength(180)
    expect(Math.min(...result.temperatures)).toBe(20)
    expect(Math.max(...result.temperatures)).toBe(22)
  })
  it('不跨越缺失温度连接', () => {
    const payload = sample()
    payload.planes[1].values[0][0] = null
    expect(solidSurface(payload,new Set()).positions).toHaveLength(0)
  })
  it('无测量带不生成填充面', () => {
    expect(solidSurface(sample(),new Set([0])).positions).toHaveLength(0)
  })
})
