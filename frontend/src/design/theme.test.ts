/// <reference types="node" />
// @vitest-environment node
/**
 * 实时模式那一屏的深色。**这一组不渲染任何东西** —— 它扫的是源码文本，
 * 与 `guards.test.ts` 同一条路子（那一条最便宜：例外是慢慢长出来的，
 * 先是有人多翻一个令牌，然后是两个）。
 *
 * 两条各自钉一件屏上看不出来的事：
 *   · 那一档覆盖了**哪 12 个**令牌。少一个，就有东西停在浅色上 ——
 *     而页面照常渲染、控制台一个错都没有；多一个，就是动了页①② 的东西
 *     （`--layer-*` 与 `--bar` 只在那边用，实时这一屏一张切面图都没有）。
 *   · 卡片底必须比页面底**亮**。深浅接反了，屏上「看起来也还行」，
 *     而卡片会陷进页面里 —— 浅色那一档靠同一个方向的关系才立得住。
 *
 * 还有一条钉规格书 §四.2 要求的那行 `color-scheme`：它管的全是**浏览器自己画的**
 * 东西（滑块、滚动条、数字框的箭头），读的是原生控件那一套，一个 `var()` 都读不到。
 * 2026-10-09 终审补上（计划把它漏了，而它是屏上唯一一处「深色只做了一半」的活证据）。
 *
 * 第三条钉的是**两边对齐**：类名在 `tokens.css` 里是选择器、在 `App.vue` 里是
 * `classList.toggle` 的第一个实参。它等 `App.vue` 挂上那个类之后才可能绿，
 * 所以 Task 1 落这一组时**刻意没写它**（一条任务不能红着收尾），Task 2 补进来。
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

// Windows 上 import.meta.url 会把中文目录名百分号编码（%E7%A9%BA…），
// 而 `pathname` 不解码 —— `fileURLToPath` 负责解码。
// 与 `guards.test.ts` 顶上那条注释同一个理由，这里照抄。
const src = (rel: string): string => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

/** 这一档**故意**覆盖的全部令牌。多一个少一个都要有人说话。 */
const DARK_TOKENS = [
  '--card',
  '--ink',
  '--ink-muted',
  '--leaf',
  '--leaf-soft',
  '--nav-blue',
  '--nav-tint',
  '--net',
  '--paper',
  '--shadow',
  '--steel',
  '--unknown-stripe',
]

/**
 * 取出 `:root.theme-live { … }` 那一段，**并先抹掉注释**。
 *
 * 抹注释不是洁癖：那一段的注释里逐条写着令牌名（「只覆盖这 12 个」下面那张
 * 名单、以及「故意不动」的那几条），而 `--temp-scale` 那类名字后面跟的是
 * 反引号与顿号。若照着原文扫 `(--[a-z-]+)\s*:`，注释里只要有人写成
 * 「`--foo:` 这个词」就会凭空多出一个「令牌」—— 于是名单对不上，
 * 而红的是功能，指错方向。抹掉之后扫的是**声明**。
 */
function darkBlock(): string {
  const css = src('./tokens.css')
  const m = /:root\.theme-live\s*\{([\s\S]*?)\n\}/.exec(css)
  expect(m, 'tokens.css 里没有 `:root.theme-live` 那一块').not.toBeNull()
  return m![1].replace(/\/\*[\s\S]*?\*\//g, '')
}

/** 某档里那个令牌的 6 位十六进制值。 */
function hexOf(block: string, token: string): string {
  const m = new RegExp(`${token}\\s*:\\s*#([0-9A-Fa-f]{6})`).exec(block)
  expect(m, `${token} 在那一块里不是一个 6 位十六进制`).not.toBeNull()
  return m![1]
}

/** 相对亮度（WCAG 那个公式）。深色下两个底差几个点，靠眼睛是分不出来的。 */
function luminance(hex: string): number {
  const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

describe('实时模式那一屏的深色', () => {
  it('只覆盖那 12 个令牌', () => {
    const names = [...darkBlock().matchAll(/(--[a-z][a-z-]*)\s*:/g)].map((m) => m[1])
    expect(names.sort()).toEqual([...DARK_TOKENS].sort())
  })

  it('深色那一档把 color-scheme 也翻过去：原生控件不许停在浅色上', () => {
    // 规格书 §四.2 明写这一行。它现场最容易被放过：滑块、滚动条、`<input
    // type=number>` 的上下箭头都是**浏览器自己画的**，一个 `var()` 都读不到 ——
    // 页面整片暗下来，只有那几件小东西还亮着，而控制台一个错都没有。
    // 扫的是抹掉注释之后的那一段，注释里提一句 `color-scheme` 不算数。
    // （2026-10-09 终审 Important 1：计划把规格书这一行漏了。）
    expect(darkBlock(), '深色那一档没有 color-scheme: dark').toMatch(/color-scheme\s*:\s*dark/)
  })

  it('卡片底比页面底亮：深浅关系不许接反', () => {
    const block = darkBlock()
    expect(
      luminance(hexOf(block, '--card')),
      '卡片底没有比页面底亮 —— 卡片会陷进页面里',
    ).toBeGreaterThan(luminance(hexOf(block, '--paper')))
  })

  it('类名在 tokens.css 与 App.vue 里是同一个字符串', () => {
    // 深色那一档要生效，两处必须对齐：CSS 那边是选择器，JS 那边是 toggle 的
    // 第一个实参。各写各的 —— 比如选择器 `.theme-live` 配 `toggle('theme-dark')`
    // —— 页面照常渲染、控制台一个错都没有，只是**深色永远不出现**
    // （或者出现之后摘不掉，训练模式那四页再也回不来）。
    // 类名不写死在断言里：从 `tokens.css` 取出来，再去 `App.vue` 里找同一个。
    const m = /:root\.(theme-[a-z-]+)\s*\{/.exec(src('./tokens.css'))
    expect(m, 'tokens.css 里没有 `:root.theme-*` 那一块').not.toBeNull()
    const cls = m![1]
    expect(src('../App.vue'), `App.vue 没有把 ${cls} 挂上去`)
      .toContain(`classList.toggle('${cls}'`)
  })
})
