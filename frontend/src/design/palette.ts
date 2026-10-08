/**
 * 把 tokens.css 里的**颜色与图表字号**读成 JS 对象，喂给图表。
 *
 * **为什么要有这一层**：ECharts 的 option 里要的是真的颜色字符串与真的数字，
 * 不能写 `var(--ink)`、也不能写 `var(--size-chart-axis)`（canvas 不认，`fontSize`
 * 更不吃 `'12px'`）。没有这一层，每个图表组件就会就地写一个十六进制、写一个
 * 写死的字号 —— 那正是「硬约束 2」要防的事。
 *
 * 字号是 2026-10-06 收进来的：原先五个 option 文件里散着 26 处写死的 10/11/12，
 * 而且**同一个角色 10 与 11 混用**（画坐标轴标签，`constraintDelta` 用 10、
 * `diurnalResidual` 用 11）。界面字号一放大，图里的字不跟着动，就露馅了。
 *
 * 读不到就**抛错**：给个默认灰（或字号 0）是最坏的兜底 —— 图照画、颜色或
 * 字号是错的、而且没有人知道。
 */
export interface Palette {
  paper: string
  ink: string
  inkMuted: string
  steel: string
  leaf: string
  leafSoft: string
  net: string
  /** 切面图的测点分层色（页①）：顶层 / 中层 / 底层。 */
  layerTop: string
  layerMid: string
  layerLow: string
  /**
   * 残差诊断那三张图的柱子（页②）。**不是界面色**，只活在图表里 ——
   * 之所以不能拿 `steel` 顶替，见 `tokens.css` 里 `--bar` 那一节。
   */
  bar: string
  /** 图表文字的字号。**是数，不是颜色** —— 见下面的 `NUMERIC`。 */
  chartAxis: number
  chartTitle: number
}

/**
 * **颜色**令牌的键。`Palette` 上还挂着两个数（`chartAxis` / `chartTitle`），
 * 而「按 `keyof Palette` 取一个颜色」这件事必须仍然只可能取到颜色 ——
 * 不然 `p[k]` 的类型就变成 `string | number`，每个按层号取色的地方都得加断言
 * （`sensorLayout.ts` 的 `LAYER_SLOTS` 就是那个地方）。
 * 用 `Omit` 而不是把颜色名重列一遍：以后加了新颜色会自动进来，不会漏。
 */
export type ColorKey = keyof Omit<Palette, 'chartAxis' | 'chartTitle'>

const MAP: Record<keyof Palette, string> = {
  paper: '--paper',
  ink: '--ink',
  inkMuted: '--ink-muted',
  steel: '--steel',
  leaf: '--leaf',
  leafSoft: '--leaf-soft',
  net: '--net',
  layerTop: '--layer-top',
  layerMid: '--layer-mid',
  layerLow: '--layer-low',
  bar: '--bar',
  chartAxis: '--size-chart-axis',
  chartTitle: '--size-chart-title',
}

/** 这几个读出来是**数**：`getComputedStyle` 给的是 `'12px'`，而 ECharts 的
 *  `fontSize` 要的是 `12`。写错一个就悄悄退回默认字号，所以列在这里，由
 *  下面那道 `Number.isFinite` 盯着。 */
const NUMERIC = new Set<keyof Palette>(['chartAxis', 'chartTitle'])

export function readPalette(el: HTMLElement = document.documentElement): Palette {
  const cs = getComputedStyle(el)
  // 累加器写成 `Record`（宽），不是 `Palette`：`out[key] = v` 里 `key` 是整个
  // 键的联合类型，而 `Palette` 上既有 `string` 又有 `number`，TS 把「能赋给它的
  // 类型」算成 `never`，两种写法都报错。末尾那一次断言由 `palette.test.ts` 的
  // `toEqual` 盯着 —— 键少一个、多一个都会红，所以这里不是「随便断言一下」。
  const out: Record<string, string | number> = {}
  for (const [key, token] of Object.entries(MAP) as [keyof Palette, string][]) {
    const v = cs.getPropertyValue(token).trim()
    // 破折号改成分号：这条消息会随异常冒到界面上，属 Ruling P2 的可见字符串。
    if (!v) throw new Error(`设计令牌 ${token} 读不到；tokens.css 没被加载？`)
    if (NUMERIC.has(key)) {
      const n = Number.parseFloat(v)
      if (!Number.isFinite(n)) throw new Error(`设计令牌 ${token} 不是数：${v}`)
      out[key] = n
    } else {
      out[key] = v
    }
  }
  return out as unknown as Palette
}

/**
 * 只要颜色那一半。**字号不是颜色** —— 把整个 `Palette` 当一袋色去比对
 * （`Object.values(palette)`）会把 12 和 14 也喂给 `toUpperCase()`。
 * 「哪些键是数」只有 `NUMERIC` 一个地方说了算，这里不再列第二份名单。
 * 图表测试用它来算「调色板里到底有哪些色」，那条断言靠的就是这个集合是**全**的。
 */
export function paletteColors(p: Palette): string[] {
  return Object.entries(p)
    .filter(([k]) => !NUMERIC.has(k as keyof Palette))
    .map(([, v]) => String(v))
}
