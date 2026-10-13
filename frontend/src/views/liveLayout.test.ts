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
    expect(app, '模式开关没有两处（中央列那一处）').toMatch(/<ModeSwitch v-if="isLive"/)
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
})
