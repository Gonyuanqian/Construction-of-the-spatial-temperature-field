/**
 * 色标的采样点，全前端的**唯一**来源。
 *
 * 为什么色标要写成字面量：canvas 的渐变要的是真颜色，而 `tokens.css` 里的
 * `--temp-scale: turbo` 是一个**色标名**，不是颜色。所以这九个（和十一个）值
 * 只能在这里出现一次 —— 别处都从这里取。
 *
 * 谁在用：`options/diurnalResidual.ts`（页②残差热图）、
 * `options/sectionField.ts`（页③ V5 切面场）、将来的 `options/volume.ts`（V7）。
 * spec §七 要求 V5 与 V7 共用同一套「场 → 纹理」的光栅化 ——
 * 共用这条色标是其中唯一会被看见的那一半。
 */

/**
 * 温度色标：**turbo**（2026-10-12 用户裁定「换 turbo，全站统一」）。
 *
 * ⚠️ 九个采样点而不是七个：`valueToColor` 在采样点之间按 **RGB 线性插值**，
 * 七档插出来的 turbo 会在中段丢掉那些拐点（绿到黄那一段拐得最急）。
 * 九档是参考图那条色带肉眼能分辨的档数。
 *
 * ⚠️ **必须正向**：低温暗紫蓝、高温暗红。反过来的坑（52 °C 画成深蓝）与底无关，
 * 照旧适用 —— 所以本文件里不许出现反向色标名，**注释里也不许**
 * （`guards.test.ts` 扫的是源码文本）。
 *
 * ⚠️ 每次调用返回**新数组**：同一个引用交给 ECharts、又交给别处，
 * 是最容易被下游改坏的一类共享状态。
 */
export function tempStops(): string[] {
  // Google turbo 那条十六档等距梯度里取九档（下标 0/2/4/6/8/10/12/14/15）：
  // 十六档两两相邻在屏上分不出来，而每多一个字面量就多一处要与守卫对齐的东西。
  return [
    '#30123B', '#4675ED', '#1BCFD4', '#61FC6C', '#D1E834',
    '#F6A12A', '#F04D02', '#B10A01', '#7A0403',
  ]
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
 * 是**同一组 stops 加同一条插值规则** —— 靠 `scale.test.ts` 里在九个采样点上
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
