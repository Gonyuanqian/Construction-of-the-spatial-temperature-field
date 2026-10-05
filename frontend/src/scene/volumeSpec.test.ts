import { describe, expect, it } from 'vitest'

import { makeVolumePayload } from '../test/fixtures'
import {
  SHELL_LENGTH_DEFAULT, SHELL_LENGTH_MAX, SHELL_LENGTH_MIN, SHELL_NOTE,
  buildVolumeSpec,
} from './volumeView'

describe('场景描述：哪一片多透', () => {
  it('实测断面是实心的', () => {
    const s = buildVolumeSpec(makeVolumePayload(), SHELL_LENGTH_DEFAULT)
    expect(s.planes[0].measured).toBe(true)
    expect(s.planes[0].opacity).toBe(1)
  })

  it('离实测断面越远越透（同一卷里单调）', () => {
    const p = makeVolumePayload({
      planes: [
        { y: 3, measured: true, shed: 'p1', values: [[1]] },
        { y: 3.5, measured: false, shed: null, values: [[1]] },
        { y: 4.5, measured: false, shed: null, values: [[1]] },
        { y: 6.5, measured: false, shed: null, values: [[1]] },
      ],
    })
    const s = buildVolumeSpec(p, SHELL_LENGTH_DEFAULT)
    expect(s.planes[0].opacity).toBe(1)
    expect(s.planes[1].opacity).toBeGreaterThan(s.planes[2].opacity)
    expect(s.planes[2].opacity).toBeGreaterThan(s.planes[3].opacity)
  })

  it('**混合片淡，但不会淡到看不见**', () => {
    // 规格书 §5.3：上界不能让混合片淡到看不见 —— 那样「有一片场」就变成
    // 「没有场」，是另一种谎，和把混合画成实测一样坏。
    const p = makeVolumePayload({
      planes: [
        { y: 3, measured: true, shed: 'p1', values: [[1]] },
        { y: 60, measured: false, shed: null, values: [[1]] },
      ],
    })
    const s = buildVolumeSpec(p, SHELL_LENGTH_DEFAULT)
    expect(s.planes[1].opacity).toBeGreaterThanOrEqual(0.1)
    expect(s.planes[1].opacity).toBeLessThan(1)
  })

  it('一卷里一片实测都没有时，每一片都拿到下界，**不是 NaN**', () => {
    // `Math.min()` 对空数组给 `Infinity` —— 于是 `1 - 0.22 · Infinity` 是
    // `-Infinity`，被下界接住。而 `Infinity` 与 `NaN` 只差一步，
    // 一个 NaN 透明度会让**整片场静默消失**（Three 会把它当 0 或者干脆不画）。
    const p = makeVolumePayload({
      planes: [
        { y: 30, measured: false, shed: null, values: [[1]] },
        { y: 31, measured: false, shed: null, values: [[1]] },
      ],
    })
    const s = buildVolumeSpec(p, SHELL_LENGTH_DEFAULT)
    for (const pl of s.planes) {
      expect(Number.isFinite(pl.opacity)).toBe(true)
      expect(pl.opacity).toBeGreaterThan(0)
    }
  })

  it('每一片的透明度都落在 (0, 1]', () => {
    const s = buildVolumeSpec(makeVolumePayload(), SHELL_LENGTH_DEFAULT)
    for (const pl of s.planes) {
      expect(pl.opacity).toBeGreaterThan(0)
      expect(pl.opacity).toBeLessThanOrEqual(1)
    }
  })
})

describe('场景描述：画什么', () => {
  it('棚壳立在载荷给的那几个 y 上，长度是滑块的值', () => {
    const p = makeVolumePayload()
    const s = buildVolumeSpec(p, 5.5)
    expect(s.shellYs).toEqual([3, 9, 15])
    expect(s.shellLength).toBe(5.5)
    expect(s.arch).toEqual(p.arch)          // 拱线**来自载荷**，不在前端重算
  })

  it('每座棚的 y 上一个壳：壳数就是载荷给的棚数，与换折无关', () => {
    const p = makeVolumePayload()
    expect(buildVolumeSpec(p, 4).shellYs).toHaveLength(p.sheds.length)
  })

  it('测点只画在 available_sheds 上', () => {
    // 测点是二维里就已经成立的语言（那里是「实测过的位置」）。三维里不画它们，
    // 整个体看起来就像「处处都测过了」。
    //
    // ⚠️ 规格书 §5.2 写的是「十二个测点」—— **那个数是错的**，
    // `C.SENSOR_LAYOUT` 是 8 条，8 × 3 座棚 = 24 个。所以这条测试
    // 一个数字都不写死：数与布局都从载荷来（见「本计划对规格书的三处修正」1）。
    const p = makeVolumePayload({ available_sheds: ['p1', 'p3'] })
    const s = buildVolumeSpec(p, SHELL_LENGTH_DEFAULT)
    expect(s.sensorSheds.map((x) => x.shed)).toEqual(['p1', 'p3'])
    expect(s.sensorSheds[0].y).toBe(3)
    expect(s.sensorSheds[1].y).toBe(15)
    expect(s.sensorSheds[0].points).toEqual(p.sensors.map((sn) => ({ x: sn.x, z: sn.z })))
  })

  it('一座棚都没有样本时测点列表是空的，不是「全都画」', () => {
    const p = makeVolumePayload({ available_sheds: [] })
    expect(buildVolumeSpec(p, SHELL_LENGTH_DEFAULT).sensorSheds).toEqual([])
  })

  it('空腔就是载荷给的那份斜纹，全片共用同一份引用', () => {
    const p = makeVolumePayload()
    expect(buildVolumeSpec(p, 4).cavity).toBe(p.stripes)
  })

  it('色标范围原样带过来，不在前端各算各的', () => {
    const p = makeVolumePayload({ vmin: 42.1, vmax: 52.8 })
    const s = buildVolumeSpec(p, 4)
    expect(s.vmin).toBe(42.1)
    expect(s.vmax).toBe(52.8)
  })

  it('壳长的默认值与上下界', () => {
    expect(SHELL_LENGTH_DEFAULT).toBe(4)
    expect(SHELL_LENGTH_MIN).toBe(1)
    expect(SHELL_LENGTH_MAX).toBe(6)
    expect(SHELL_LENGTH_MIN).toBeLessThan(SHELL_LENGTH_DEFAULT)
    expect(SHELL_LENGTH_DEFAULT).toBeLessThan(SHELL_LENGTH_MAX)
  })

  it('壳长那句说明写明了「示意」，且数据集没给实际长度', () => {
    // 规格书 §5.3：图上必须标明「棚体示意」—— 不允许读成「测了这么长」。
    expect(SHELL_NOTE).toContain('示意')
    expect(SHELL_NOTE).toContain('没有给出')
  })
})
