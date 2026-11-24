/// <reference types="node" />
// @vitest-environment node
/**
 * 实时模式左栏的四项导航。
 *
 * ⚠️ 为什么不并进 `guards.test.ts`：那一条「未开放项必带理由」只断长度，
 * 断不到**次序与数量**，而这一次裁定的内容恰恰就是数量。
 */
import { describe, expect, it } from 'vitest'

import { LIVE_NAV_ITEMS, NAV_ITEMS } from './copy'

describe('实时那一屏的左栏', () => {
  it('是四项，次序照参考图（「首页」已并入「实时监测」）', () => {
    expect(LIVE_NAV_ITEMS.map((i) => i.label)).toEqual([
      '实时监测', 'AgriSeek', '历史数据', '系统设置',
    ])
  })

  it('监测与助手已开放，历史和设置仍为占位', () => {
    // ⚠️ 2026-10-16 用户裁定：「首页就是实时监测，把这两个合在一起留一个就行」，
    // 名字取「实时监测」（「首页」在系统里已有主 —— `/` 跳的是数据导入页）。
    // 合并之后这一屏上终于**有了对象可选**，参考图上那个高亮态才落得下来。
    // 「留位并写明理由，不做成空页」（spec 2026-10-04 §二.4）对后三项仍然成立。
    expect(LIVE_NAV_ITEMS[0]!.enabled).toBe(true)
    expect(LIVE_NAV_ITEMS[0]!.to).toBe('/live')
    expect(LIVE_NAV_ITEMS[1]!.enabled).toBe(true)
    expect(LIVE_NAV_ITEMS[1]!.to).toBe('/assistant')
    expect(LIVE_NAV_ITEMS.slice(2).every((i) => !i.enabled)).toBe(true)
    expect(new Set(LIVE_NAV_ITEMS.map((i) => i.key)).size).toBe(4)
  })

  it('四项各配一枚线框图标，名字不重样', () => {
    // 名字要与 `design/icons.ts` 对得上 —— 对不上时屏上是**一处空白**，
    // 而组件不会报错（`Icon.vue` 只按名字取形状）。
    expect(LIVE_NAV_ITEMS.map((i) => i.icon)).toEqual(['pulse', 'chat', 'clock', 'gear'])
  })

  it('训练导航按流程保留四个页面入口', () => {
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      '数据导入与检查', '模型训练', '模型库', '空间温度场的构建',
    ])
  })
})
