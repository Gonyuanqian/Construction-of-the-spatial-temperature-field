/**
 * 数据预览表的渲染。
 *
 * **滚不滚得动不在这个文件里。** 用户对这一块的原话是「做成上下左右滑动的
 * 窗口形式」，而 jsdom **不做布局** —— `overflow` 与 `position: sticky` 在这边
 * 量不出任何效果。那几条在 `design/guards.test.ts`，与 `StatRow` 那两条同源：
 * 量的是**源码里的规则本身**。
 *
 * 这里只管画出来的东西：列标题照后端给的印、时刻走 `fmtTime`、数值走 `fmt1`、
 * 缺失印「—」而不是 0。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DataPreviewTable from './DataPreviewTable.vue'

const COLUMNS = [
  { key: 'bg_temp_C', label: '背景温度' },
  { key: 'p1_x0.15_z0.4_temp_C', label: 'p1·B6' },
  { key: 'p1_x0.8_zH(0.80)-0.20_temp_C', label: 'p1·B1' },
]

const TIME = ['2026-07-23T11:00:00', '2026-07-23T11:05:00']
const VALUES = [
  [31.44, 34.26, null],
  [31.1, 34.0, 35.06],
]

function mountTable(over: Partial<Record<'columns' | 'time' | 'values', unknown>> = {}) {
  return mount(DataPreviewTable, {
    props: {
      columns: COLUMNS, time: TIME, values: VALUES,
      ...over,
    } as never,
  })
}

describe('渲染', () => {
  it('第一格是「时刻」，然后照后端给的次序印列标题', () => {
    const w = mountTable()
    expect(w.findAll('thead th').map((h) => h.text()))
      .toEqual(['时刻', '背景温度', 'p1·B6', 'p1·B1'])
  })

  it('时刻走 fmtTime：不带 T、不带秒', () => {
    const w = mountTable()
    expect(w.findAll('tbody tr')[0].find('td').text()).toBe('2026-07-23 11:00')
  })

  it('数值走 fmt1 —— 一位小数，与全站同一个写法', () => {
    const w = mountTable()
    const cells = w.findAll('tbody tr')[0].findAll('td')
    expect(cells[1].text()).toBe('31.4')
    expect(cells[2].text()).toBe('34.3')
  })

  it('缺失印「—」，不印 0，也不印 NaN', () => {
    // 后端把 NaN 翻成 null（`_finite`），线上「这段没有值」就是 null。
    // 印成 0 就是凭空造了一个读数 —— 而 0 °C 在温棚里是个有意义的数。
    const w = mountTable()
    const cell = w.findAll('tbody tr')[0].findAll('td')[3]
    expect(cell.text()).toBe('—')
    expect(cell.find('.nil').exists(), '「无值」没有自己的标记').toBe(true)
  })

  it('行数 = 给的行数，一格不多一格不少', () => {
    const w = mountTable()
    expect(w.findAll('tbody tr').length).toBe(2)
    expect(w.findAll('tbody tr')[1].findAll('td').length).toBe(COLUMNS.length + 1)
  })

  it('一行都没有时不塌（`limit=0` 是合法请求）', () => {
    const w = mountTable({ values: [], time: [] })
    expect(w.findAll('tbody tr').length).toBe(0)
    expect(w.findAll('thead th').length).toBe(COLUMNS.length + 1)
  })
})
