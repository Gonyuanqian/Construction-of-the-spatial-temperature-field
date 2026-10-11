import { describe, expect, it } from 'vitest'

import { hexToRgb, tempStops } from '../charts/scale'
import { makeVolumePayload } from '../test/fixtures'
import { rasterPlane, stripeIndexSet, type PlaneRaster } from './raster'

const alphaAt = (r: PlaneRaster, ix: number, iz: number): number =>
  r.data[(iz * r.width + ix) * 4 + 3]

const rgbAt = (r: PlaneRaster, ix: number, iz: number): [number, number, number] => {
  const o = (iz * r.width + ix) * 4
  return [r.data[o], r.data[o + 1], r.data[o + 2]]
}

const STOPS = tempStops()

describe('一片场画成像素', () => {
  it('尺寸就是场的行列数：宽度是 x，高度是 z', () => {
    const p = makeVolumePayload().planes[0]
    const r = rasterPlane(p.values, 0, 5, STOPS)
    expect(r.width).toBe(4)                 // values[0].length，即 x
    expect(r.height).toBe(4)                // values.length，即 z
    expect(r.data.length).toBe(4 * 4 * 4)
  })

  it('拱外 alpha 为 0，其余 255；颜色按值走', () => {
    const r = rasterPlane([[0, 5], [null, 2.5]], 0, 5, STOPS)
    expect(alphaAt(r, 0, 0)).toBe(255)
    expect(alphaAt(r, 1, 0)).toBe(255)
    expect(alphaAt(r, 0, 1)).toBe(0)                       // 拱外
    expect(alphaAt(r, 1, 1)).toBe(255)                     // 拱内照常
    expect(rgbAt(r, 0, 0)).toEqual(hexToRgb(STOPS[0]))     // 最低值 → 暗端
    expect(rgbAt(r, 1, 0)).toEqual(hexToRgb(STOPS[6]))     // 最高值 → 亮端
  })

  it('**拱外那格不填黑，而是完全透明**', () => {
    // 黑在这条色标上是「最冷」。填黑的后果是一片算错的场看起来像一片很冷的场 ——
    // 而 alpha 为 0 时那格是「什么都没有」，读者一眼看得出哪里没有定义。
    const r = rasterPlane([[null]], 0, 5, STOPS)
    expect(alphaAt(r, 0, 0)).toBe(0)
    expect(rgbAt(r, 0, 0)).toEqual([0, 0, 0])              // RGB 是 0，但 alpha 是 0
  })

  it('无测量带的下标不填色，**而且那一格的值确实在**', () => {
    // 这条钉的是「值在那儿，但界面上不报」：带里存的是外推值（不是 null），
    // 所以只靠 null 判定根本挡不住它 —— 必须吃后端送来的 stripes。
    const values: (number | null)[][] = [[1, 2], [3, 4]]
    const r = rasterPlane(values, 0, 5, STOPS, stripeIndexSet([[0, 1]], 2))
    expect(values[1][0]).toBe(3)                           // 值确实在（不是 null）
    expect(alphaAt(r, 0, 1)).toBe(0)                       // 但那一格没填色
    expect(alphaAt(r, 1, 1)).toBe(255)                     // 隔壁照常
  })

  it('行主序：第 0 行就是 values[0]，不翻转', () => {
    // Three 的 `DataTexture` 默认 `flipY = false`，UV 的 v=0 落在平面的下沿；
    // 而 `PlaneGeometry` 的 v=0 在本地 Y 最小处 —— 两边同向，
    // 所以场景里既不用翻数组，也不用开 `flipY`。这条钉住这个约定。
    const r = rasterPlane([[0, 0], [5, 5]], 0, 5, STOPS)
    expect(rgbAt(r, 0, 0)).toEqual(hexToRgb(STOPS[0]))
    expect(rgbAt(r, 0, 1)).toEqual(hexToRgb(STOPS[6]))
  })

  it('整卷 37 片共用一份斜纹下标时，索引对得上下标', () => {
    const set = stripeIndexSet([[2, 0], [3, 2]], 4)        // iz * width + ix
    // [2,0] → 0·4 + 2 = 2；[3,2] → 2·4 + 3 = 11。
    // （下标对是 [ix, iz]，与 `pick.ts` 的 `stripes` 同一个约定。）
    expect([...set].sort((a, b) => a - b)).toEqual([2, 11])
  })

  it('值域塌成零宽时也画得出颜色（不整片透明）', () => {
    const r = rasterPlane([[1, 1], [1, 1]], 5, 5, STOPS)
    expect(alphaAt(r, 0, 0)).toBe(255)
    expect(rgbAt(r, 0, 0).every((c) => Number.isFinite(c))).toBe(true)
  })
})
