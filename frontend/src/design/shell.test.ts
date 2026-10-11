/// <reference types="node" />
// 这一条读源码文本（jsdom 不做布局，见文件头）。与 `design/guards.test.ts`、
// `design/prose.test.ts`、`charts/options/oofDensity.test.ts` 同一个头：
// jsdom 下 `import.meta.url` 不是 file: 协议，`fileURLToPath` 会抛
// 「The URL must be of scheme file」。
// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * 外壳是一张**闭合的框**（规格书 2026-10-04 §1.2、2026-10-06 §5.2 画的那两张）：
 * 标题条、模式开关、左栏都钉在框里，**只有右侧内容区自己滚**。
 *
 * 破的时候是这么破的：`html`/`body` 不限高，于是滚的是**整个文档**，
 * 左栏那四张卡跟着页面一起滑上去；而它的浅蓝色面是
 * `align-self: stretch` 撑出来的，仍然铺满整页 —— 于是屏幕上留下一条
 * 空色带。实测（1280×800，页面高 3882px）：`scrollingElement.scrollTop = 800`
 * 之后 `nav.rail` 的 `top` 从 131 变成 −669，正好 −800。
 *
 * ⚠️ **为什么是读源码的守卫，不是一条渲染测试**：jsdom 不做布局 ——
 * `height: 100%`、`overflow`、「谁滚动谁不滚动」，它一律看不见
 * （`DataPreviewTable.test.ts` 顶上记着同一件事，那条用例也因此只测窗口的
 * DOM 形状）。而这条不变式**没有第二处看得见的地方**：破了就是「往下滚时
 * 左栏跟着走了」，没有任何断言会红，而它会一路活到演示现场。
 * 所以这里钉的是**让它成立的那几行**，与 `guards.test.ts` 钉 `.stats`
 * 那两条正则同一个做法。
 *
 * 代价写在明面上：钉的是**写法**，不是效果。谁把 `#app` 换成
 * `100dvh` 或换成 grid，这条会红而界面其实是对的 —— 那时改这条测试就行，
 * 别改回去。
 */
function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')
}

/** `<style>` 那一段。Vue 文件里 `<script>` 与 `<template>` 也含 `{}`，
 *  不先切出来的话下面的 `rule()` 会跨段去找花括号。 */
function styleBlock(src: string): string {
  const m = src.match(/<style[^>]*>([\s\S]*?)<\/style>/)
  return m ? m[1] : ''
}

/**
 * 取 `选择器 { … }` 里的那一块。
 *
 * 「选择器与 `{` 之间只许有空白」这一步是必须的：`indexOf('.rail')` 会先撞上
 * `.rail-extra`，`indexOf('.body')` 会撞上 `body` 之类的更长名字。
 * 撞了就往后挪一格再找，而不是就此认输。
 */
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

const base = read('./base.css')
const app = styleBlock(read('../App.vue'))
const rail = styleBlock(read('../components/NavRail.vue'))

describe('外壳：一张闭合的框', () => {
  it('html/body 与 #app 都是一屏高，#app 是竖排的框', () => {
    // 少了这一步，`#app` 就是「内容多高就多高」，`.body` 的 `flex: 1 1 auto`
    // 无从谈起 —— 框就不存在，又从文档滚回去了。
    expect(rule(base, 'html, body'), 'html/body 没有限高').toContain('height: 100%')
    const a = rule(base, '#app')
    expect(a, '#app 没有限高').toContain('height: 100%')
    expect(a, '#app 不是竖排的框').toContain('flex-direction: column')
  })

  it('滚的是内容区，不是文档：`.page` 自己滚，`.body` 不滚', () => {
    const b = rule(app, '.body')
    // `min-height: 0` 是 flex 子项能缩到内容以下的前提 —— 没有它，
    // `.page` 的 `overflow-y: auto` 永远不生效（高度由内容撑开，何来溢出）。
    expect(b, '.body 缩不下去，`.page` 就不会滚').toContain('min-height: 0')
    expect(b, '没有把溢出挡在框里').toContain('overflow: hidden')
    expect(rule(app, '.page'), '内容区没有自己滚').toContain('overflow-y: auto')
  })

  it('左栏有自己的滚动 —— 页③ 往 #rail-extra 里投的东西顶不破外壳', () => {
    // 框闭合之后，左栏不再能靠文档滚到底部。页③ 会把视图切换与时刻游标
    // 投进 `#rail-extra`；窗口矮的时候那一列会比框还高，不自己滚就是
    // 「底下那半截永远够不着」。
    expect(rule(rail, '.rail'), '左栏没有自己的滚动').toContain('overflow-y: auto')
  })
})
