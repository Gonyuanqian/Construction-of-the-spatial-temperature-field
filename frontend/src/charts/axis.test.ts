import { describe, expect, it } from 'vitest'

import { tickLabel } from './axis'

describe('轴上的类别名：收干净了再印', () => {
  it('把浮点字符串化带出来的长尾巴收掉', () => {
    // 这三串是后端**真发来**的。`np.arange(0, 2.1, 0.05)` 出来的不是 0.05 的
    // 整数倍：第 3 个是 0.15000000000000002，`String()` 之后尾巴就跟着来了。
    // 页③ 一屏三张并排，那串尾巴会**溢出格子宽度、爬到左边那张场上**，
    // 看起来像花屏 —— 用户报的就是这个。
    expect(tickLabel('0.15000000000000002')).toBe('0.15')
    expect(tickLabel('1.2000000000000002')).toBe('1.2')
    expect(tickLabel('1.0000000000000002')).toBe('1')
  })

  it('本来就是干净的类别名，印出来一个字不变', () => {
    expect(tickLabel('0')).toBe('0')
    expect(tickLabel('1')).toBe('1')
    expect(tickLabel('2.1')).toBe('2.1')
    expect(tickLabel('0.05')).toBe('0.05')
  })

  it('两位小数够用：网格最细那档是 0.02', () => {
    // `GRID_PRESETS` 三档步长 0.10 / 0.05 / 0.02（`tfield/field/grid.py`）。
    // 收到两位小数，三档都印得出格点本来的样子，不会把 0.02 抹成 0.02 以外的数。
    expect(tickLabel('0.020000000000000004')).toBe('0.02')
    expect(tickLabel('0.13999999999999999')).toBe('0.14')
  })

  it('不是数的类别名原样放回去，不许印成 NaN', () => {
    // 轴上的类别名将来未必全是数。`Number('p1')` 是 NaN，`String(NaN)` 是
    // 「NaN」—— 那比原来那一串尾巴更难解释。
    expect(tickLabel('p1')).toBe('p1')
    expect(tickLabel('')).toBe('')
  })
})
