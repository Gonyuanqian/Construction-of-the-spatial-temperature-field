/// <reference types="node" />
// 这一条读源码文本（jsdom 不做样式计算，见文件头）。与 `design/guards.test.ts`、
// `design/shell.test.ts`、`design/prose.test.ts` 同一个头：jsdom 下
// `import.meta.url` 不是 file: 协议，`fileURLToPath` 会抛
// 「The URL must be of scheme file」。
// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * 页⑤ 精修（2026-10-16）：标题条与左栏那几件**看不见的**东西。
 *
 * ⚠️ **为什么是读源码的守卫，不是一条渲染测试**：jsdom 不做布局、也不算样式 ——
 * 「底部那条线是不是发光」「选中项左缘那道条有多宽」「行还吃着卡片投影吗」，
 * 它一律看不见（`shell.test.ts` 顶上记着同一件事）。而这几件东西破了之后
 * **没有第二处看得见**：屏上是「看着不太对」，没有一条断言会红。
 * 所以这里钉的是**让它成立的那几行**，与 `shell.test.ts` 钉 `.stats` 同一个做法。
 *
 * 代价写在明面上：钉的是**写法**，不是效果。谁换一种写法画同一条线
 * （比如把 `::after` 换成 `border-image`），这条会红而界面其实是对的 ——
 * 那时改这条测试就行，别改回去。
 */
function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
}

/** `<style>` 那一段（`<script>` 与 `<template>` 里也有 `{}`，不先切出来会跨段找）。 */
function styleBlock(src: string): string {
  const m = src.match(/<style[^>]*>([\s\S]*?)<\/style>/)
  return m ? m[1] : ''
}

/** 取 `选择器 { … }` 里那一块。选择器与 `{` 之间只许有空白（见 `shell.test.ts`）。 */
function rule(src: string, selector: string): string {
  let from = 0
  for (;;) {
    const i = src.indexOf(selector, from)
    if (i < 0) return ''
    const open = src.indexOf('{', i + selector.length)
    if (open >= 0 && src.slice(i + selector.length, open).trim() === '') {
      const close = src.indexOf('}', open)
      return close < 0 ? '' : src.slice(open + 1, close)
    }
    from = i + 1
  }
}

const title = styleBlock(read('../components/TitleBar.vue'))
const rail = styleBlock(read('../components/NavRail.vue'))

describe('页⑤ 精修：标题条那几件看不见的', () => {
  it('底部那条细青线：走 `--edge`，并且**带着光**', () => {
    // 用户第一部分要的原话是「底部添加一条细青色发光分隔线」。
    // 少了 `--glow-edge` 就只是一条青线 —— 屏上仍然「有」，但读起来是边框，
    // 不是一道亮着的边；而没有任何断言会红。
    const line = rule(title, '.titlebar.live::after')
    expect(line, '标题条底部那条青线没了').not.toBe('')
    expect(line, '那条线没走 --edge').toContain('background: var(--edge)')
    expect(line, '那条线不发光了').toContain('box-shadow: var(--glow-edge)')
    expect(line, '那条线不是 1px').toContain('height: 1px')
  })

  it('实时那一档是两列，且右格**挪回了第 2 列**', () => {
    // ⚠️ 这一条比它看上去重要：浅色档是三列（`1fr auto 1fr`，标题居中），
    // 而 `.right` 写的是 `grid-column: 3`。实时档只留两列时不把它挪回来，
    // 浏览器会**另开一个隐式列** —— 右上角那一簇被顶到栏外，而一条都不会红。
    const live = rule(title, '.titlebar.live')
    expect(live, '实时那一档不是两列').toContain('grid-template-columns: 1fr auto')
    expect(rule(title, '.titlebar.live .right'), '右上角那一簇没挪回第 2 列')
      .toContain('grid-column: 2')
  })

  it('浅色档的标题条一个像素都没动', () => {
    // 用户裁的是「只需要改动实时模式的页面」，而标题条是**全站共享**的。
    // 这条是反面：把新样式挂到裸 `.titlebar` 上（而不是 `.titlebar.live`），
    // 页①②③④ 就跟着变了 —— 上面那条也照样绿。
    const plain = rule(title, '.titlebar')
    expect(plain, '浅色档的标题条不是三列中置了')
      .toContain('grid-template-columns: 1fr auto 1fr')
    expect(plain, '相对定位挂到裸 `.titlebar` 上了（那是四页一起改）')
      .not.toContain('position: relative')
    expect(rule(title, '.titlebar::after'), '底部那条青线挂到裸 `.titlebar` 上了').toBe('')
    expect(rule(title, '.brand'), '标题那一格没占回中间那一格').toContain('grid-column: 2')
  })
})

describe('页⑤ 精修：左栏那几件看不见的', () => {
  it('实时那一档的行高落在用户给的 52–58 px 里', () => {
    const item = rule(rail, '.rail.live .item')
    expect(item, '实时那一档没有行高').not.toBe('')
    const m = /min-height:\s*(\d+)px/.exec(item)
    expect(m, '行高不是 px 写死的（用 min-height 才不会被窄屏切字）').not.toBeNull()
    const px = Number(m![1])
    expect(px, `行高 ${px}px 不在用户给的 52–58px 里`).toBeGreaterThanOrEqual(52)
    expect(px, `行高 ${px}px 不在用户给的 52–58px 里`).toBeLessThanOrEqual(58)
  })

  it('实时那一档的行**不吃卡片的投影** —— 卡片那一套只对训练侧那四页成立', () => {
    // 最容易犯的漏改：新样式写上了，卡片那几条没撤 —— 屏上是一行行**发着光的卡**，
    // 而「阴影只有一份名单」那条守卫管的是**取值合不合法**，不是「谁配吃」。
    const card = rule(rail, '.rail:not(.live) .item')
    expect(card, '卡片那一套没挂到 `:not(.live)` 上').toContain('box-shadow: var(--shadow)')
    expect(card, '卡片那一套没挂到 `:not(.live)` 上').toContain('border-radius: var(--radius)')
    const live = rule(rail, '.rail.live .item')
    expect(live, '实时那一档的行仍然吃着卡片的投影').not.toContain('box-shadow')
    expect(live, '实时那一档的行仍然有圆角').not.toContain('border-radius: var(--radius)')
  })

  it('选中项左缘那道青条：3–4 px，走 `--edge`', () => {
    // 用户第二部分的原话：「左边缘显示 3–4 px 的青色高亮线」。
    const bar = rule(rail, '.rail.live .item.router-link-active::before')
    expect(bar, '选中项左缘那道青条没了').not.toBe('')
    expect(bar, '那道条没走 --edge').toContain('background: var(--edge)')
    const m = /width:\s*(\d+)px/.exec(bar)
    expect(m, '那道条的宽度不是 px 写死的').not.toBeNull()
    const px = Number(m![1])
    expect(px, `那条 ${px}px 不在用户给的 3–4px 里`).toBeGreaterThanOrEqual(3)
    expect(px, `那条 ${px}px 不在用户给的 3–4px 里`).toBeLessThanOrEqual(4)
  })

  it('选中项带着外发光，悬停有过渡', () => {
    // 用户第二部分的原话：「边框和局部外发光适度增强」「鼠标悬停时提供平滑过渡」。
    expect(rule(rail, '.rail.live .item.router-link-active'), '选中项没有外发光')
      .toContain('box-shadow: var(--glow-lift)')
    expect(rule(rail, '.rail.live .item'), '悬停没有过渡').toContain('transition:')
  })

  it('右边缘那条低透明度青线，是**栏的边框**，不是一条会跟着滚的伪元素', () => {
    // 用户第二部分的原话：「右边缘添加一条低透明度青色分隔线」。
    // ⚠️ 走 `border-right` 而不是绝对定位的伪元素：`.rail` 是 `overflow-y: auto`，
    // 伪元素会跟着内容滚走，边框不会。
    expect(rule(rail, '.rail.live'), '左栏右缘那条青线没了')
      .toContain('border-right: 1px solid var(--edge-line)')
  })
})
