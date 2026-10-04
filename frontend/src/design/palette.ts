/**
 * 把 tokens.css 里的颜色读成 JS 对象，喂给图表。
 *
 * **为什么要有这一层**：ECharts 的 option 里要的是真的颜色字符串，
 * 不能写 `var(--ink)`（canvas 不认）。没有这一层，每个图表组件就会
 * 就地写一个十六进制 —— 那正是「硬约束 2」要防的事。
 *
 * 读不到就**抛错**：给个默认灰是最坏的兜底 —— 图照画、颜色是错的、
 * 而且没有人知道。
 */
export interface Palette {
  paper: string
  ink: string
  inkMuted: string
  steel: string
  leaf: string
  leafSoft: string
  net: string
}

const MAP: Record<keyof Palette, string> = {
  paper: '--paper',
  ink: '--ink',
  inkMuted: '--ink-muted',
  steel: '--steel',
  leaf: '--leaf',
  leafSoft: '--leaf-soft',
  net: '--net',
}

export function readPalette(el: HTMLElement = document.documentElement): Palette {
  const cs = getComputedStyle(el)
  const out = {} as Palette
  for (const [key, token] of Object.entries(MAP) as [keyof Palette, string][]) {
    const v = cs.getPropertyValue(token).trim()
    // 破折号改成分号：这条消息会随异常冒到界面上，属 Ruling P2 的可见字符串。
    if (!v) throw new Error(`设计令牌 ${token} 读不到；tokens.css 没被加载？`)
    out[key] = v
  }
  return out
}
