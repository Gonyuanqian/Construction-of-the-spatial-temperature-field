/// <reference types="node" />
// @vitest-environment node
/**
 * 实时那一屏的左栏是**五项演示占位**（2026-10-12 用户裁定，照参考图补齐）。
 *
 * ⚠️ 为什么不并进 `guards.test.ts`：那一条「未开放项必带理由」只断长度，
 * 断不到**次序与数量**，而这一次裁定的内容恰恰就是数量。
 */
import { describe, expect, it } from 'vitest'

import { LIVE_NAV_ITEMS, NAV_ITEMS } from './copy'

describe('实时那一屏的左栏', () => {
  it('是五项，次序照参考图', () => {
    expect(LIVE_NAV_ITEMS.map((i) => i.label)).toEqual([
      '首页', '实时监测', '三维可视化', '历史数据', '系统设置',
    ])
  })

  it('五项一条都不开放，也一条都不是链接', () => {
    // 「留位并写明理由，不做成空页」（spec 2026-10-04 §二.4）。
    // `App.test.ts` 另有一条断「左栏里一个 <a> 都没有」——
    // 那一条按 `LIVE_NAV_ITEMS` 推导，所以这里补上数量这一轴。
    expect(LIVE_NAV_ITEMS.every((i) => !i.enabled)).toBe(true)
    expect(new Set(LIVE_NAV_ITEMS.map((i) => i.key)).size).toBe(5)
  })

  it('训练那四页的左栏一个字节都没动', () => {
    // 用户 2026-10-12 裁的是**实时这一屏**。这一条是本文件里唯一一条
    // 反面断言：把 `NAV_ITEMS` 也一起改掉是这次改动最容易犯的错。
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      '数据导入与检查', '模型训练', '空间温度场的构建', '影响分析',
    ])
  })
})
