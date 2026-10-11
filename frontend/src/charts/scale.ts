/**
 * 色标的采样点，全前端的**唯一**来源。
 *
 * 为什么色标要写成字面量：canvas 的渐变要的是真颜色，而 `tokens.css` 里的
 * `--temp-scale: cividis` 是一个**色标名**，不是颜色。所以这七个（和十一个）值
 * 只能在这里出现一次 —— 别处都从这里取。
 *
 * 谁在用：`options/diurnalResidual.ts`（页②残差热图）、
 * `options/sectionField.ts`（页③ V5 切面场）、将来的 `options/volume.ts`（V7）。
 * spec §七 要求 V5 与 V7 共用同一套「场 → 纹理」的光栅化 ——
 * 共用这条色标是其中唯一会被看见的那一半。
 */

/**
 * 温度：正向 cividis，七段。
 *
 * ⚠️ **必须正向**。反过来的话 52 °C 是深蓝、42 °C 是亮黄，每个人都会读反，
 * 而图上不会报任何错（spec §8.1 记着这个坑：整张图读反了，屏上一切正常）。
 * 这里不能写出反向色标的名字：`guards.test.ts` 全仓扫那个字符串，注释也算。
 *
 * 每次调用返回**新数组**：这个数组要交给 ECharts，共享一个引用迟早被改坏。
 */
export function tempStops(): string[] {
  return ['#00224E', '#12456F', '#4C6C7F', '#7C7B78', '#BE8353', '#EB9A31', '#FFE945']
}

/**
 * 差异 / 误差：发散色标，十一端。
 *
 * 发散色标的**中点必须是中性色**，而且要配一个对称的值域
 * （`visualMap: { min: -m, max: +m }`）—— 否则「没变」会被画成一个有颜色的格子，
 * 而那正是这张图要说的第一件事。
 *
 * 蓝端 = 负（约束前 < 约束后，被抬高了），红端 = 正（被压低了）。
 */
export function deltaStops(): string[] {
  return [
    '#053061', '#2166AC', '#4393C3', '#92C5DE', '#D1E5F0', '#F7F7F7',
    '#FDDBC7', '#F4A582', '#D6604D', '#B2182B', '#67001F',
  ]
}

/**
 * 十六进制 → `[r, g, b]`（0 至 255）。`#RGB` 与 `#RRGGBB` 都认。
 *
 * 这个函数住在这里，是因为**全前端只有 `scale.ts` 与 `tokens.css` 允许出现
 * 十六进制字面量**（`design/guards.test.ts` 扫全仓盯着）。摆在别处，
 * 那条守卫就得开第二个口子。
 */
export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.trim().replace(/^#/, '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const n = Number.parseInt(full, 16)
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff]
}

/**
 * 值 → 颜色。**「场 → 纹理」这条路上唯一的插值处。**
 *
 * 规则与 ECharts 的 continuous `visualMap` 同一条：采样点之间**在 RGB 空间线性**。
 * 二维那边的插值碰不到（见 `tempStops` 的说明），所以这里不是「同一个函数」，
 * 是**同一组 stops 加同一条插值规则** —— 靠 `scale.test.ts` 里在七个采样点上
 * 逐点对拍来守。
 *
 * 三处退化都写死了，因为它们的后果都是**静默的**：
 *  · 值域塌成零宽（`vmin === vmax`）→ 取最低端，不是 `(v - vmin) / 0` 的 NaN；
 *  · `v` 是 NaN → 取最低端；
 *  · 一个 NaN 通道会被 `Uint8ClampedArray` 悄悄写成 0（黑），而黑在这条色标上
 *    是「最冷」—— 于是一片算错的场看起来像一片很冷的场。
 *
 * 范围外的值**夹到两端**，与 ECharts `inRange` 的行为一致（`outOfRange` 那套
 * 压暗是二维色标条的事，三维不用）。
 */
export function valueToColor(
  v: number, vmin: number, vmax: number, stops: string[],
): [number, number, number] {
  const lo = hexToRgb(stops[0])
  if (stops.length < 2) return lo
  const span = vmax - vmin
  const t = span > 0 ? Math.min(1, Math.max(0, (v - vmin) / span)) : 0
  if (!Number.isFinite(t)) return lo
  // 分段插值：先定位到哪两个采样点之间，再在这一段里取局部位置。
  // 写成 `(n - 1) · t` 直接当全局位置会在段边界上差一个采样点。
  const pos = t * (stops.length - 1)
  const seg = Math.min(stops.length - 2, Math.floor(pos))
  const local = pos - seg
  const a = hexToRgb(stops[seg])
  const b = hexToRgb(stops[seg + 1])
  return [
    Math.round(a[0] + (b[0] - a[0]) * local),
    Math.round(a[1] + (b[1] - a[1]) * local),
    Math.round(a[2] + (b[2] - a[2]) * local),
  ]
}
