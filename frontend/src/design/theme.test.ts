/// <reference types="node" />
// @vitest-environment node
/**
 * 深色那一档（`:root.theme-live`）的守卫。扫的是**源码文本**，不渲染任何东西。
 *
 * ⚠️ 2026-10-12 起 `tokens.css` 里有**两块** `:root.theme-live`：① 颜色、
 * ② 版式。原先那个正则只取**第一个**块 —— 写成两块会让第②块**悄悄逃过守卫**，
 * 所以这个文件必须收全部块、钉两份名单。这不是顺手，是那条改动的前提。
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))
  .replaceAll('\\', '/').replace(/\/+$/, '')

const strip = (s: string): string => s.replace(/\/\*[\s\S]*?\*\//g, '')

/** `:root.theme-live` 的**全部**块，按出现次序。 */
function darkBlocks(): string[] {
  const css = strip(readFileSync(join(SRC, 'design', 'tokens.css'), 'utf8'))
  const out: string[] = []
  for (const m of css.matchAll(/:root\.theme-live\s*\{([\s\S]*?)\n\}/g)) {
    out.push(m[1] ?? '')
  }
  expect(out, 'tokens.css 里没有 `:root.theme-live` 那一块').not.toHaveLength(0)
  return out
}

/**
 * `:root` 那一块（浅色档）。
 * ⚠️ 正则要求 `:root` 后面**直接跟着** `{` —— `:root.theme-live` 因此不会被它
 * 误当成浅色档。写成 `/:root[^{]*\{/` 就会把两块混成一块，
 * 而下面那条「浅色档取等值」的断言会拿着深色档的数字去比。
 */
function lightBlock(): string {
  const css = strip(readFileSync(join(SRC, 'design', 'tokens.css'), 'utf8'))
  const m = /:root\s*\{([\s\S]*?)\n\}/.exec(css)
  expect(m, 'tokens.css 里没有浅色那一档的 `:root`').not.toBeNull()
  return m![1] ?? ''
}

/**
 * 块里声明的令牌名，排序后返回 —— 排序是因为次序在这条判据里不是信息。
 *
 * ⚠️ 字符类里**必须带数字**：`--card-2` 那个名字以数字收尾，写成 `[a-z-]*`
 * 的话它一个都匹配不上 —— 于是它从这份名单里**凭空消失**，而断言的期望值里
 * 还写着它，红的是「少一个令牌」，指的方向却是 CSS 那边。
 */
const tokensOf = (block: string): string[] =>
  [...block.matchAll(/(--[a-z][a-z0-9-]*)\s*:/g)].map((m) => m[1] ?? '').sort()

const hexOf = (block: string, token: string): string => {
  const m = new RegExp(`${token}\\s*:\\s*#([0-9A-Fa-f]{6})`).exec(block)
  expect(m, `深色那一档没有给 ${token} 一个六位色值`).not.toBeNull()
  return m![1]!
}

const luminance = (hex: string): number => {
  const n = Number.parseInt(hex, 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
}

/** 颜色那一块要覆盖的令牌。**多一个少一个都要在这里改**。 */
const DARK_COLOR_TOKENS = [
  '--card', '--card-2', '--face-dim', '--header', '--ink', '--ink-muted',
  '--interact', '--leaf', '--leaf-soft', '--nav-blue', '--nav-tint', '--net',
  '--ok', '--on-face', '--paper', '--shadow', '--steel', '--unknown-stripe',
  // 页⑤ 精修（2026-10-16）：一条只描边的青、一个标题字色、两档发光、一条淡青线。
  '--edge', '--glow-edge', '--glow-lift', '--title-ink', '--edge-line',
].sort()

/** 版式那一块。深浅不是字号的事，也不是栏宽的事 —— 所以两块分开守。 */
const DARK_LAYOUT_TOKENS = ['--side-w', '--sidebar-w', '--titlebar-h'].sort()

describe('实时那一档的令牌', () => {
  it('一共就两块：颜色一块、版式一块', () => {
    // 少了这一条，下面两条「块①钉这 18 个、块②钉这 3 个」可以被
    // 「把版式也塞进颜色那一块」满足 —— 而那正是这一轮要拆开的东西。
    expect(darkBlocks()).toHaveLength(2)
  })

  it('第①块管颜色，名单不多不少', () => {
    expect(tokensOf(darkBlocks()[0]!)).toEqual(DARK_COLOR_TOKENS)
  })

  it('第②块管版式，名单不多不少', () => {
    expect(tokensOf(darkBlocks()[1]!)).toEqual(DARK_LAYOUT_TOKENS)
  })

  it('`color-scheme: dark` 写在颜色那一块，且只有一处', () => {
    // 原生控件（滑块、滚动条、数字框的上下箭头）是**浏览器自己画的**，
    // 读的是这一行而不是任何一个 `var()` —— 不翻它，页面整片暗下来而这几件
    // 小东西还亮着，控制台一个错都没有。
    const blocks = darkBlocks()
    expect(blocks[0]).toMatch(/color-scheme\s*:\s*dark/)
    expect(blocks[1]).not.toMatch(/color-scheme/)
  })

  it('卡片底比页面底亮 —— 卡片才浮得起来', () => {
    const b = darkBlocks()[0]!
    expect(luminance(hexOf(b, '--card'))).toBeGreaterThan(luminance(hexOf(b, '--paper')))
  })

  it('类名与 `App.vue` 里切的那一个一致', () => {
    // 两边各写一个字符串，写歪了不报错：整屏**根本不进深色**，
    // 而所有令牌都在，只是没人用。
    const cls = /:root\.(theme-[a-z-]+)\s*\{/.exec(
      readFileSync(join(SRC, 'design', 'tokens.css'), 'utf8'))?.[1]
    expect(cls, 'tokens.css 里找不到 theme-* 那个类').toBeTruthy()
    const app = readFileSync(join(SRC, 'App.vue'), 'utf8')
    expect(app, `App.vue 没有切 ${cls}`).toContain(`classList.toggle('${cls}'`)
  })

  it('实时那一档的主色仍是青 —— 规格书 §四.3 那条字面要求被有意推翻', () => {
    // 数过：`var(--leaf)` 在**六个页面**上有**十处**当强调色用
    // （`.alert` 的左边线、`.tag` 的字、`.unset`、模型库那个「当前」图章、
    // 滑块上的 `accent-color`、按钮与分段控件的激活底…）。
    // 按 §四.3 的字面把它压成 `#041A35`，屏上就是**深蓝压深蓝** ——
    // 而两边都不会报错。用户给的分工写的是「青色负责轮廓与强调」，
    // 所以这一条断的是「青还在」，而标题条的**面**另走了 `--header`。
    const b = darkBlocks()[0]!
    expect(hexOf(b, '--leaf')).toBe('34D3C4')
    expect(luminance(hexOf(b, '--header')))
      .toBeLessThan(luminance(hexOf(b, '--leaf')))
  })

  it('浅色那一档的六个新令牌全是**等值** —— 页①②③④ 一个像素都不动', () => {
    // ⚠️ 这一条比它看上去重要：把新令牌在浅色档写成**一套新值**是最容易犯的错
    // （「反正实时那一档才是重点」），而那会把页①②③④ 的标题条高度、
    // 按钮激活色、焦点环一起改掉 —— 用户裁的是「只需要改动实时模式的页面」。
    // 「等值」= 写成另一个**已有令牌的 `var()`**，不是一个新色号。
    const light = lightBlock()
    expect(light).toMatch(/--header:\s*var\(--leaf\)\s*;/)
    expect(light).toMatch(/--on-face:\s*var\(--paper\)\s*;/)
    expect(light).toMatch(/--face-dim:\s*var\(--steel\)\s*;/)
    expect(light).toMatch(/--interact:\s*var\(--leaf\)\s*;/)
    expect(light).toMatch(/--ok:\s*var\(--leaf\)\s*;/)
    expect(light).toMatch(/--card-2:\s*var\(--card\)\s*;/)
    // 版式那两个：浅色档的标题条高度是「由内容撑」（`auto`），
    // 右栏宽度是 0（这一屏在浅色档上根本没有右栏）。
    expect(light).toMatch(/--titlebar-h:\s*auto\s*;/)
    expect(light).toMatch(/--side-w:\s*0\s*;/)
    // 反面：这六个令牌在浅色档里**一个六位色值都不许有** —— 有即为「新写了一套」。
    const fresh = [...light.matchAll(
      /--(header|on-face|face-dim|interact|ok|card-2)\s*:\s*#/g)].map((m) => m[1])
    expect(fresh, '浅色档给新令牌写了新色号').toEqual([])
  })

  it('页⑤ 精修那四个新令牌，浅色档也全部取等值', () => {
    // 与上一条同一个理由、同一份纪律：这一轮的令牌只给实时那一屏用，
    // 而「只给实时用」这件事**在浅色档里要看得见** —— 取等值就是那个证据。
    // 写成一套新值不会让任何一条断言变红（页①②③④ 根本不引这四个名字），
    // 也就没人会发现「只改实时屏」这条规矩已经破了。
    const light = lightBlock()
    expect(light).toMatch(/--edge:\s*var\(--leaf\)\s*;/)
    expect(light).toMatch(/--title-ink:\s*var\(--on-face\)\s*;/)
    expect(light).toMatch(/--glow-edge:\s*var\(--shadow\)\s*;/)
    expect(light).toMatch(/--glow-lift:\s*var\(--shadow\)\s*;/)
    // 左栏右缘那条线：浅色档的左栏没有它，取的是 `transparent`。
    expect(light).toMatch(/--edge-line:\s*transparent\s*;/)
    // 反面：这几个名字在浅色档里一个六位色值都不许有。
    const fresh = [...light.matchAll(
      /--(edge|title-ink|glow-edge|glow-lift|edge-line)\s*:\s*#/g)].map((m) => m[1])
    expect(fresh, '浅色档给精修令牌写了新色号').toEqual([])
  })

  it('实时那一档的 `--edge` 是一条**只描边**的青，与 `--leaf` 不是同一个值', () => {
    // 两个都叫青、都在同一屏上：`--leaf` #34D3C4 是「强调」（左边线、图章、
    // 激活底），`--edge` 更电一点、**只用来描边与发光，从不当任何一块面**。
    // 写成同一个值屏上也能看，但那条分工就没了 —— 而这一轮要的正是分工。
    const b = darkBlocks()[0]!
    expect(hexOf(b, '--edge')).toBe('00CFFF')
    expect(hexOf(b, '--edge')).not.toBe(hexOf(b, '--leaf'))
  })
})
