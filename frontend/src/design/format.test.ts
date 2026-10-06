import { describe, expect, it } from 'vitest'

import { fmt1, fmtInt, fmtRange, fmtTime } from './format'

describe('读数的写法', () => {
  it('时刻把 ISO 里那个 T 换成空格，秒不给人看', () => {
    expect(fmtTime('2026-07-23T11:00:00')).toBe('2026-07-23 11:00')
  })

  it('整数原样，不补千分位 —— 这是台仪器，不是一张财报', () => {
    expect(fmtInt(1308)).toBe('1308')
  })

  it('一位小数', () => {
    expect(fmt1(43.2213)).toBe('43.2')
    // 页③ 的「无测量带」那一格用的是它，量纲是**米**不是度 ——
    // 所以这个函数的名字里不许带「温度」（见 format.ts 的说明）。
    expect(fmt1(1.1)).toBe('1.1')
  })

  it('区间用「至」，不用被禁的连接符', () => {
    const s = fmtRange(38.94, 48.82, '°C')
    expect(s).toBe('38.9 至 48.8 °C')
    for (const bad of ['——', ' · ', '→', '↳']) expect(s).not.toContain(bad)
  })

  it('区间没有单位时不硬凑一个空格', () => {
    expect(fmtRange(1.04, 1.10)).toBe('1.0 至 1.1')
  })
})
