/**
 * 一片场 → RGBA 像素。
 *
 * 与 `charts/options/*` 里那些「载荷 → 画图配置」的纯函数同一个手法：
 * 算好一个普通对象交给画的那一层。区别只在于这一层的输出是像素数组 ——
 * 而像素数组**能被断言**，画面本身不能（jsdom 没有 canvas/WebGL，规格书 §8.2）。
 */
import { valueToColor } from '../charts/scale'

export interface PlaneRaster {
  width: number
  height: number
  /** RGBA，行主序。第 0 行是 `values[0]` 那一行（z 最小的那一行）。 */
  data: Uint8ClampedArray
}

/**
 * 无测量带的下标 → 一组线性下标（`iz * width + ix`）。
 *
 * 整卷共用一份斜纹（规格书 §四.4），所以这一组**只建一次**、几十片共用 ——
 * 逐片重建的话，每片都要把那个列表再走一遍，而它对每一片都是同一份。
 */
export function stripeIndexSet(pairs: [number, number][], width: number): Set<number> {
  return new Set(pairs.map(([ix, iz]) => iz * width + ix))
}

/**
 * 把一片场画成像素。
 *
 * **两处不填色，而理由不同**：
 *  · `values` 是 `null`（拱外）—— 场在那里**没有定义**；
 *  · 下标落在 `blank` 里（无测量带）—— 值在那儿，但**没有实测支撑**。
 * 三维里两者都表现为透明，但**判定层不许把它们合成一句话**（规格书 §四.4）：
 * 悬停到拱顶下那一层要答「无测量带，不报数」，不是「拱外，无定义」。
 * 这里合起来，是因为「画」这一层只关心填不填色。
 *
 * 不翻转：第 0 行对应 `values[0]`。`Uint8ClampedArray` 初值全 0，
 * 所以没填的格子天然是 alpha = 0，**不需要额外写一遍**。
 */
export function rasterPlane(
  values: (number | null)[][], vmin: number, vmax: number, stops: string[],
  blank: ReadonlySet<number> = new Set(),
): PlaneRaster {
  const height = values.length
  const width = height > 0 ? values[0].length : 0
  const data = new Uint8ClampedArray(width * height * 4)
  for (let iz = 0; iz < height; iz++) {
    for (let ix = 0; ix < width; ix++) {
      const v = values[iz][ix]
      if (v === null || blank.has(iz * width + ix)) continue
      const o = (iz * width + ix) * 4
      const [r, g, b] = valueToColor(v, vmin, vmax, stops)
      data[o] = r
      data[o + 1] = g
      data[o + 2] = b
      data[o + 3] = 255
    }
  }
  return { width, height, data }
}
