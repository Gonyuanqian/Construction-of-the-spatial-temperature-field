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
        { y: 3, measured: true, shed: 'p1', values: [[1]], mean: 26.5 },
        { y: 3.5, measured: false, shed: null, values: [[1]], mean: 26.5 },
        { y: 4.5, measured: false, shed: null, values: [[1]], mean: 26.5 },
        { y: 6.5, measured: false, shed: null, values: [[1]], mean: 26.5 },
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
        { y: 3, measured: true, shed: 'p1', values: [[1]], mean: 26.5 },
        { y: 60, measured: false, shed: null, values: [[1]], mean: 26.5 },
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
        { y: 30, measured: false, shed: null, values: [[1]], mean: 26.5 },
        { y: 31, measured: false, shed: null, values: [[1]], mean: 26.5 },
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

/**
 * 拱肋摆在哪些 y 上。
 *
 * 2026-10-09 用户裁定：三维影像「不够形象和具体」。原因之一是**拱肋原先只有
 * 壳的两端各一圈**（`VolumeScene` 里就地写的 `[y − L/2, y + L/2]`），而在
 * 18 m 长的一条上，那几圈读起来是划痕，不是拱棚 —— 拱棚之所以一眼认得出，
 * 靠的正是**等距重复的肋**。
 *
 * 肋的间距是**示意**，与壳长同一个性质：表现参数，不是数据（规格书 §5.3 只
 * 把棚长定为滑块，没说肋怎么摆）。所以这一条不破任何规格，只是把「够不够像」
 * 这个模糊的判据落成一个能断言的东西。
 */
describe('拱肋摆放', () => {
  const one = () => makeVolumePayload({ sheds: [{ id: 'p1', y: 3 }] })

  it('一座棚：两端各一圈，中间等距 —— 不是只有两端那两圈', () => {
    // 棚在 y = 3、壳长 4 → 壳铺 [1, 5]；间距 0.5。
    // 写死这个数列而不是断言「长度大于 2」：只数个数的话，把间距写成 1.9
    // 照样「大于 2」，而屏上仍然没有那排肋。
    const s = buildVolumeSpec(one(), 4)
    expect(s.ribYs).toEqual([1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5])
  })

  it('拉到最短那一档：两端仍然在，中间那圈也不能没有', () => {
    // 反面：只断两个端点的话，一个「只画两端」的实现照样绿 ——
    // 而那正是要改掉的那件事。
    const s = buildVolumeSpec(one(), SHELL_LENGTH_MIN)
    expect(s.ribYs[0]).toBe(3 - SHELL_LENGTH_MIN / 2)
    expect(s.ribYs[s.ribYs.length - 1]).toBe(3 + SHELL_LENGTH_MIN / 2)
    expect(s.ribYs.length, '只剩两端那两圈了').toBeGreaterThan(2)
  })

  it('壳长不均匀时末端那圈也不丢', () => {
    // 滑块是 0.5 一档，正常走不到这里；但式子不能靠「长度一定是 0.5 的整数倍」
    // 才对 —— 那样以后谁把 step 放宽，末端就会**静默**少一圈。
    const s = buildVolumeSpec(one(), 4.2)
    expect(s.ribYs[s.ribYs.length - 1]).toBe(5.1)
  })

  it('几座棚就几组肋，次序与间距都跟着棚位走', () => {
    // 夹具的三座棚在 3 / 9 / 15。写成「每座 9 圈、共 27 圈」而不是
    // 「包含某几个数」：漏掉一座、或三座叠在同一处，前者抓得到后者抓不到。
    const s = buildVolumeSpec(makeVolumePayload(), 4)
    expect(s.ribYs).toHaveLength(27)
    expect(s.ribYs.slice(0, 9)).toEqual([1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5])
    expect(s.ribYs.slice(18, 27)).toEqual([13, 13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17])
    // 单调递增：三组肋是沿着棚长铺开的，不是各自从头数。
    for (let i = 1; i < s.ribYs.length; i++) {
      expect(s.ribYs[i], `第 ${i} 圈没有排在它前面那圈之后`).toBeGreaterThan(s.ribYs[i - 1])
    }
  })
})
