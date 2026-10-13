import { describe, expect, it } from 'vitest'

import type { SectionsPayload, SectionShed, VolumePayload } from '../api/types'
import { formatTemp, interpretPick, interpretVolumePick, pickText } from './pick'

/**
 * 一个 4×4 的小场，四种格子各占一角，好让每一种回答都能被指到。
 *
 * 行号就是 `iz`（`values[iz]`），而 `z = [0, 0.7, 1.4, 2.1]`：
 *
 *   iz=3 (z=2.1)   拱外    拱外    斜纹    斜纹
 *   iz=2 (z=1.4)   拱外    值 2    斜纹    斜纹
 *   iz=1 (z=0.7)   值 1    值 2    斜纹    值 4
 *   iz=0 (z=0)     值 1    值 2    斜纹    值 4
 *
 * `stripes` 列的是斜纹格（`[ix, iz]`）：ix=2 那一整列，外加 iz=2、3 的 ix=3。
 * `max_measured_z = 2` —— 但判定**不看它**，判定只读 `stripes`（后端送来的那份事实）。
 * 拱外（null）在左上一角。
 *
 * **这个夹具的「不对称」是承重的**：4×4 是方阵，若四行四列的数也对称，
 * 把 `values[iz][ix]` 写成 `values[ix][iz]` 照样会全绿 —— 而图会整个转置。
 * 别为了「整齐」把它改成对称的。
 */
function makeValues(): (number | null)[][] {
  return [
    [1, 2, 3, 4],          // iz = 0
    [1, 2, 3, 4],          // iz = 1
    [null, 2, 3, 4],       // iz = 2
    [null, null, 3, 4],    // iz = 3
  ]
}

const STRIPES: [number, number][] = [[2, 0], [2, 1], [2, 2], [2, 3], [3, 2], [3, 3]]

function makeShed(): SectionShed {
  return { shed: 'p1', y: 3, values: makeValues(), stripes: STRIPES }
}

function makePayload(): SectionsPayload {
  return {
    t_index: 0, time: '2026-07-23T11:00:00', n_times: 1,
    preset: 'standard', monotonic: true, calibrated: true,
    mismatch_note: '',
    artifact_note: '',
    vmin: 0, vmax: 5, max_measured_z: 2,
    x_min: 0, x_max: 2.1, z_max: 1.3017,
    x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
    arch: [[0, 0], [2.1, 0]], sensors: [],
    sheds: [makeShed()],
    note: '',
  }
}

/** 两片的一小卷：第 0 片是实测断面，第 1 片是混合出来的。 */
function makeVolume(): VolumePayload {
  return {
    t_index: 12, time: '2026-07-23T12:00:00', n_times: 1308,
    preset: 'standard', monotonic: true, calibrated: true,
    mismatch_note: '',
    artifact_note: '',
    y_step: 0.5, y_min: 0, y_max: 18,
    x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 2,
    // 与 `x_max - x_min` 自洽的几何两格 —— 后端算好发下来的形状。
    shed_width: 2.1, shed_height: 1.3017,
    vmin: 0, vmax: 5,
    mean: 26.5,
    x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
    arch: [[0, 0], [2.1, 0]],
    sheds: [{ id: 'p1', y: 3 }, { id: 'p2', y: 9 }, { id: 'p3', y: 15 }],
    sensors: [],
    available_sheds: ['p1', 'p2', 'p3'],
    stripes: STRIPES,
    planes: [
      { y: 3, measured: true, shed: 'p1', values: makeValues(), mean: 26.5 },
      { y: 3.5, measured: false, shed: null, values: makeValues(), mean: 26.5 },
    ],
    elapsed_ms: 1250, note: '',
  }
}

describe('点选只有三种回答', () => {
  it('三种回答穷尽且互斥（Review Focus 5）', () => {
    const payload = makePayload()
    const shed = payload.sheds[0]
    const seen = new Set<string>()
    for (let iz = 0; iz < shed.values.length; iz++) {
      for (let ix = 0; ix < shed.values[iz].length; ix++) {
        const r = interpretPick(payload, 'p1', ix, iz)
        seen.add(r.kind)
        // 每格恰好落在一种回答里，且判据只能是这两条。
        const cell = shed.values[iz][ix]
        const striped = shed.stripes.some(([a, b]) => a === ix && b === iz)
        if (cell === null) expect(r.kind, `(${ix},${iz}) 是 null，该判拱外`).toBe('outside')
        else if (striped) expect(r.kind, `(${ix},${iz}) 在斜纹里，该判无测量带`).toBe('unmeasured')
        else expect(r.kind, `(${ix},${iz}) 有实测值`).toBe('value')
      }
    }
    expect([...seen].sort()).toEqual(['outside', 'unmeasured', 'value'])
  })

  it('报出来的数就是格子里那个数，一位不差', () => {
    // 判定里做任何四舍五入，界面上就会出现「图上是 43.2161、面板说 43.22」。
    // 显示层要怎么舍是显示层的事，判定层不许动这个数。
    const payload = makePayload()
    payload.sheds[0].values[1][1] = 43.216137
    const r = interpretPick(payload, 'p1', 1, 1)
    expect(r.kind).toBe('value')
    expect(r.kind === 'value' && r.value).toBe(43.216137)
  })

  it('斜纹格即便存着牌面值也不报数', () => {
    const payload = makePayload()
    // 斜纹格里是**外推值**：数在那儿，但没有实测支撑。
    const r = interpretPick(payload, 'p1', 2, 0)
    expect(payload.sheds[0].values[0][2]).toBe(3)   // 值确实在
    expect(r.kind).toBe('unmeasured')
    expect(pickText(r, payload.max_measured_z)).toContain('不报数')
  })

  it('拱外压过斜纹（两种标记撞上时拱外优先）', () => {
    // 正常情况下这两个集合不相交（斜纹是「拱内 & 无测量」）。
    // 但一旦相交，宁可说「无定义」也不要说「不报数」—— 前者更保守，
    // 且不会让人以为那里还有个数只是没显示。
    const payload = makePayload()
    payload.sheds[0].stripes.push([0, 3])            // 同时是拱外
    expect(interpretPick(payload, 'p1', 0, 3).kind).toBe('outside')
  })

  it('索引越界是编程错误，抛错而不是给出第四种回答', () => {
    const payload = makePayload()
    expect(() => interpretPick(payload, 'p1', 9, 0)).toThrow()
    expect(() => interpretPick(payload, 'p1', 0, 9)).toThrow()
    expect(() => interpretPick(payload, 'p9', 0, 0)).toThrow()
  })
})

describe('三维那一侧走的是同一套判定', () => {
  it('三种回答一个不少，且各自落在同一批格子上', () => {
    const p = makeVolume()
    expect(interpretVolumePick(p, 0, 1, 1)).toEqual({ kind: 'value', value: 2 })
    // 拱外那一格是 (0, 2)：`values[2] = [null, 2, 3, 4]`，只有第 0 列是 null。
    expect(interpretVolumePick(p, 0, 0, 2).kind).toBe('outside')
    expect(interpretVolumePick(p, 0, 2, 0)).toEqual({ kind: 'unmeasured', z: 0 })
  })

  it('**拱外与无测量带不合并**：拱顶下那层答「无测量带」，不是「拱外」', () => {
    // 规格书 §四.4 的警告。三维里这两样**都不填色**，所以最容易被顺手合成一支 ——
    // 而它们的回答不是同一句话：拱外是「场在那里没有定义」，
    // 无测量带是「值在那儿，但没有实测支撑」。合成之后，悬停到拱顶下那一层
    // 会答「拱外，无定义」，把「不敢说」说成了「不存在」。
    const p = makeVolume()
    // (2, 0) 是斜纹格，值确实是 3，但不在拱外。
    expect(p.planes[0].values[0][2]).toBe(3)
    expect(interpretVolumePick(p, 0, 2, 0)).toEqual({ kind: 'unmeasured', z: 0 })
    expect(interpretVolumePick(p, 0, 0, 3).kind).toBe('outside')
  })

  it('片号越界是编程错误，抛错而不是给出第四种回答', () => {
    expect(() => interpretVolumePick(makeVolume(), 9, 0, 0)).toThrow()
    expect(() => interpretVolumePick(makeVolume(), -1, 0, 0)).toThrow()
  })

  it('两片给的答案按各自的值走（不是都读了第一片）', () => {
    const p = makeVolume()
    p.planes[1].values[1][1] = 43.216137
    expect(interpretVolumePick(p, 1, 1, 1)).toEqual({ kind: 'value', value: 43.216137 })
    expect(interpretVolumePick(p, 0, 1, 1)).toEqual({ kind: 'value', value: 2 })
  })
})

describe('三种回答的文案', () => {
  it('无测量带那句写明了阈值，且阈值来自参数', () => {
    const text = pickText({ kind: 'unmeasured', z: 1.4 }, 0.83)
    expect(text).toContain('0.83')
    expect(text).toContain('不报数')
    // 上面两条挡不住「把阈值写死进文案」—— 写死一个数，它照样能对上。
    // 换一个阈值再问一次：真正从参数读的文案会跟着变，写死的不会。
    expect(pickText({ kind: 'unmeasured', z: 1.4 }, 1.1)).not.toBe(text)
  })

  it('拱外那句说清是「无定义」而不是某个数', () => {
    expect(pickText({ kind: 'outside' }, 2)).toContain('无定义')
  })

  it('数值那句带上数值本身与出处', () => {
    const t = pickText({ kind: 'value', value: 43.216137 }, 2)
    expect(t).toContain('43.22')
    expect(t).toContain('现场重算')     // 与 Provenance 的说法一致
  })

  it('formatTemp 固定两位小数', () => {
    expect(formatTemp(43.216137)).toBe('43.22')
    expect(formatTemp(-0.001)).toBe('-0.00')
  })
})
