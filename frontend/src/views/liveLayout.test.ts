/// <reference types="node" />
// @vitest-environment node
/**
 * 页⑤ 那一屏的版面钩子。扫的是**源码文本**，与 `guards.test.ts` 同一个手法。
 *
 * 为什么值得单独一条：这一轮把中央那一列拆开重排、又给外壳开了第三列，
 * 而这两件事都**不是**单元测试量得到的（jsdom 不做布局）。能钉住的只有
 * 「那些钩子还在不在源码里、还在不在该在的那一层」。
 *
 * ⚠️ 它够不着什么，说清楚：1280 / 1512 / 2560 下到底破不破版、
 * 右栏在 1100 下有没有落到下方、有没有横向滚动条 —— **一条都不在这里**，
 * 全是规格书 §八「必须人眼看的」那几条。
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))
  .replaceAll('\\', '/').replace(/\/+$/, '')

const read = (rel: string): string => readFileSync(join(SRC, rel), 'utf8')

describe('页⑤ 的版面钩子', () => {
  it('外壳在 /live 上开第三列，且落点由外壳自己渲染', () => {
    const app = read('App.vue')
    expect(app).toContain('id="shell-side"')
    expect(app, '落点没有只在实时那一档上').toMatch(/v-if="isLive"\s+id="shell-side"/)
    expect(app, '实时模式开关没有移到左侧导航区').toMatch(/class="live-nav-stack"[^>]*>[\s\S]*?<ModeSwitch v-model="mode"\s*\/>/)
    // 三列是栅格，不是 flex —— 后者的第三列会跟着内容漂。
    expect(app).toMatch(/\.body\.live\s*\{[^}]*display:\s*grid/)
  })

  it('三条断点都在，且窄屏是「落到下方」不是「挤在一起」', () => {
    const app = read('App.vue')
    expect(app, '缺 1200–1440 那一条').toMatch(/max-width:\s*1439px/)
    expect(app, '缺 < 1200 那一条').toMatch(/max-width:\s*1199px/)
    // 中列不许写成 `1fr`：格子的下限会变成内容宽度，画布把页宽撑破。
    expect(app, '中列没写 minmax(0, …)').toMatch(/grid-template-columns:[^;]*minmax\(0,\s*1fr\)/)
  })

  it('页⑤ 只渲染中栏，侧栏由 Teleport 投出去', () => {
    const live = read('views/LiveView.vue')
    expect(live, '三维那块没有传 panels="shell"').toContain('panels="shell"')
    // ⚠️ 同一组按钮不许在两个摆法上同时出现。
    expect(live, '画布角上那组按钮还开着').not.toContain('show-view-controls')
    const vv = read('scene/VolumeView.vue')
    expect(vv, '实时弹性列继承了 align-items: start，画布会按内容缩窄')
      .toMatch(/\.vol-grid\.stretch\s*\{[^}]*align-items:\s*stretch/)
    expect(vv).toContain('to="#shell-side"')
    expect(vv, '侧栏那两块没有按 panels 分档').toMatch(/panels === 'all'/)
  })

  it('棚顶气象这一轮撤干净了，它的数据不许在页⑤ 上再被读一次', () => {
    const live = read('views/LiveView.vue')
    expect(live, '棚顶气象还印在屏上').not.toContain('棚顶气象')
    expect(live, '`bg_temp` 还在被读').not.toContain('bg_temp')
    expect(live, '`bg_rh` 还在被读').not.toContain('bg_rh')
    expect(live, '`bg_light` 还在被读').not.toContain('bg_light')
  })

  it('几何两格读的是后端那两个键，不在前端相减', () => {
    const live = read('views/LiveView.vue')
    expect(live).toContain('shed_width')
    expect(live).toContain('shed_height')
    // 反面：`x_max - x_min` 这个减法一旦出现，就是硬约束 1 破在了屏上。
    expect(live, '前端自己在相减').not.toMatch(/x_max\s*-\s*x_min/)
  })

  it('圆环的比例与颜色都来自载荷，色标也只有一处', () => {
    const live = read('views/LiveView.vue')
    expect(live, '环的颜色没用 valueToColor（那就是第二套色标）').toContain('valueToColor')
    expect(live).toContain('tempStops')
  })

  it('中央那一屏是一条竖排的弹性列，三维是唯一会长会缩的那一块', () => {
    // 2026-10-16 用户裁定：棚体三维温度场 / 环境参数 / 沿栅均温这三块
    // **要同屏，不要下滑**。做法是把高度交给窗口分配，不是在这一页里编一个
    // 「窗口高减多少」的常数 —— 那个数在有人往这一屏加一块时会**悄悄**过期，
    // 而屏上只表现为「三维矮了」，不报错也不红。
    //
    // ⚠️ 这条守的是**挂钩点在不在**，不是效果。1280 / 1512 / 2560 下到底
    // 同不同屏、三维缩到多矮，一条都不在这里 —— 与文件头说的一样，
    // 那些必须人眼看。
    const app = read('App.vue')
    expect(app, '实时那一档的中栏没有摆成竖排的列')
      .toMatch(/\.body\.live\s*>\s*\.page\s*\{[^}]*display:\s*flex/)
    // ⚠️ 反面：滚动那条**不许跟着撤** —— 窗口不够高时它是唯一的退路。
    expect(app, '中栏不再自己滚了').toContain('overflow-y: auto')

    const live = read('views/LiveView.vue')
    expect(live, '根那一层没有摆成弹性列').toMatch(/\.live\s*\{[^}]*flex-direction:\s*column/)
    expect(live, '`.stage` 不在').toMatch(/\.stage\s*\{[^}]*flex:\s*1 1 auto/)
    expect(live, '三维那一块没有把高度让出去').toContain('stretch')
    // ⚠️ 画布的下限**只许写一处**（在 `VolumeScene` 那一条里）。这里再写一个数，
    // 两个数迟早对不上，而屏上只是「三维的高度看着不对」。
    expect(live, '`.stage` 自己又写了一个下限').not.toMatch(/\.stage\s*\{[^}]*min-height:\s*\d+px/)

    const vv = read('scene/VolumeView.vue')
    // 三层挂钩点：这一块的根、`.vol-grid`、`.vol-stage`，外加透传给画布那一层。
    // 少哪一层，画布就退回自己写死的 460px —— 不报错，只是不跟着缩。
    expect(vv, '根容器没有接收 stretch').toMatch(/<div class="block" :class="\{ stretch \}"/)
    expect(vv, '画布卡片没有接收 stretch').toMatch(/<Card class="vol-stage" :class="\{ stretch,/)
    expect(vv, '画布组件没有接收 stretch').toMatch(/<VolumeScene\s[^>]*:class="\{ stretch \}"/)
    expect(vv, '`.vol-grid` 那一处没挂').toMatch(/'stage-only': panels === 'shell', stretch/)
    expect(vv, '`.vol-grid` 没有能缩的时候').toMatch(/\.vol-grid\.stretch/)
    expect(vv, '中栏卡片没有能缩的时候').toMatch(/\.vol-stage\.stretch/)
    expect(vv, '三维那一块的根没有能缩的时候').toMatch(/\.block\.stretch/)

    const vs = read('scene/VolumeScene.vue')
    expect(vs, '画布那一层没接收 stretch').toMatch(/\.scene-wrap\.stretch/)
    // 下限保画面不是一条缝；上限就是**改动前那一档**（今天的高度是天花板，
    // 不是地板 —— `fit.test.ts` 那几条比例是照 460 定的）。
    expect(vs, '画布没有有界下限，会缩成一条缝').toMatch(/\.scene-wrap\.stretch\s*>\s*\.scene\s*\{[^}]*min-height:\s*(?:200px|clamp\(120px,\s*[^;]+,\s*200px\))/)
    expect(vs, '画布没有上限，会拉得比改动前更大').toMatch(/\.scene-wrap\.stretch\s*>\s*\.scene\s*\{[^}]*max-height:\s*460px/)
    // ⚠️ 页③ 那一条**一个字符都不许动**：写死的 460px 仍在原处。
    expect(vs, '页③ 那一档写死的高度被改掉了')
      .toMatch(/\.scene\s*\{\s*width:\s*100%;\s*height:\s*460px/)
  })
})
