import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ParamPanel from './ParamPanel.vue'
import type { CalibrationPanel } from '../api/types'

/** 一份最小的面板载荷：XGBoost 二维、IDW 二维、一个固定值。 */
const PANEL: CalibrationPanel = {
  trend: [
    { key: 'trend.max_depth', label: '每棵树最深几层',
      values: ['3', '4', '5', '6'], raw: [3, 4, 5, 6], current: 4 },
    { key: 'trend.objective', label: '目标函数',
      values: ['reg:squarederror', 'reg:absoluteerror'],
      raw: ['reg:squarederror', 'reg:absoluteerror'], current: 'reg:squarederror' },
  ],
  idw: [
    { key: 'metric.power', label: 'IDW 距离幂',
      values: ['0.5', '1', '2'], raw: [0.5, 1, 2], current: 0.5 },
    { key: 'cross_shed', label: '跨棚邻居是否参与',
      values: ['开', '关'], raw: [true, false], current: true },
  ],
  fixed: [{ key: 'metric.ly', label: 'IDW y 方向尺度 / m', value: '1',
            note: '固定 1.0，从未进过搜索空间' }],
}

const VALUES = {
  'trend.max_depth': 4, 'trend.objective': 'reg:squarederror',
  'metric.power': 0.5, 'cross_shed': true,
}

function show(over: Partial<CalibrationPanel> = {}, values = VALUES) {
  return mount(ParamPanel, { props: { panel: { ...PANEL, ...over }, values } })
}

describe('ParamPanel', () => {
  it('分成两个区块，各带一个小标题', () => {
    const w = show()
    expect(w.findAll('h4').map((e) => e.text())).toEqual(['XGBoost', 'IDW'])
  })

  it('每一维占一行，标签与键都在屏上', () => {
    const w = show()
    for (const r of [...PANEL.trend, ...PANEL.idw]) {
      expect(w.text()).toContain(r.label)
      expect(w.text()).toContain(r.key)
    }
  })

  it('每一维的全部候选值都印在屏上 —— 不是只印当前那一档', () => {
    // 规格书 §2.2。这一条是页② 第一版那个「先」字的延续：
    // 点之前就知道要搜什么；控件化之后仍然要知道。
    const w = show()
    for (const r of [...PANEL.trend, ...PANEL.idw]) {
      for (const v of r.values) expect(w.text()).toContain(v)
    }
  })

  it('拖到第 n 档，发出去的是 raw[n]，不是下标', () => {
    // 硬约束 1：前端不换算。它是**取值**，不是**算值**。
    const w = show()
    const sliders = w.findAll('input[type="range"]')
    expect(sliders.length).toBe(2)            // max_depth 与 power；另两维是下拉
    const depth = sliders[0]
    expect((depth.element as HTMLInputElement).max).toBe('3')   // 4 档 → 上界 3
    ;(depth.element as HTMLInputElement).value = '2'
    depth.trigger('input')
    expect(w.emitted('pick')?.[0]).toEqual(['trend.max_depth', 5])
  })

  it('下拉把每一档印成选项，值为下标', () => {
    const w = show()
    const selects = w.findAll('select')
    expect(selects.length).toBe(2)            // objective 与 cross_shed
    const opts = selects[0].findAll('option')
    expect(opts.map((o) => o.text())).toEqual(PANEL.trend[1].values)
    expect(opts.map((o) => o.attributes('value'))).toEqual(['0', '1'])
  })

  it('选了下拉的第 n 项，发出去的也是 raw[n]', async () => {
    const w = show()
    const sel = w.findAll('select')[0]
    ;(sel.element as HTMLSelectElement).value = '1'
    await sel.trigger('change')
    expect(w.emitted('pick')?.[0]).toEqual(['trend.objective', 'reg:absoluteerror'])
  })

  it('当前值印在旁边，取的是 values 那一列', () => {
    // 印的是「印法」那一串，不是 `raw` 里那个值的另一种写法 ——
    // 同一页不许两个口径（规格书 §2.2）。
    //
    // ⚠️ 单看 `max_depth` 是**钉不住**这件事的：`values[1]` 是 `'4'`、
    // `raw[1]` 是 `4`，两种写法 `text()` 出来一模一样。真正能分辨的只有
    // `cross_shed` —— 它的值是布尔 `true`，`values` 那一列写的是 `'开'`；
    // 误从 `raw` 取值就会印成 `true`。所以这里把四行一次断言完，
    // 分辨力落在最后那一格上。
    const w = show()
    expect(w.findAll('.now').map((e) => e.text()))
      .toEqual(['4', 'reg:squarederror', '0.5', '开'])
  })

  it('找不到对应档位时印空白，而不是编一个数出来', () => {
    // 规格书 §3.1 保证后端会把「不在候选里的当前值」并进候选，所以真实数据
    // 走不到这一支（后端那半由 `test_当前值不在候选里时并进候选` 钉着）。
    // 这一条钉的是**退化的方向**：`indexOf` 得到 -1 时，`.now` 是空的
    // （用户看得见不对劲），而不是 `values[-1]` 那样**环回**过来一个错的数
    // —— 屏上摆一个错的数，比摆一片空白坏得多。
    // （滑块的落点交给浏览器对区间的钳制，不在这里钉，那是实现细节。）
    const w = show({
      trend: [{ key: 'trend.max_depth', label: '每棵树最深几层',
                values: ['3', '4', '5', '6'], raw: [3, 4, 5, 6],
                current: 7 }],
    }, { ...VALUES, 'trend.max_depth': 7 })
    expect(w.find('.now').text()).toBe('')
    expect(w.text()).toContain('每棵树最深几层')   // 别的部分照常渲染，没崩
  })

  it('metric.ly 不做控件，只有一行说明', () => {
    // 规格书 §2.3：一个拖不动的滑块比一句话更容易让人以为是没点对。
    const w = show()
    const idw = w.findAll('section')[1]
    expect(idw.findAll('input[type="range"]').length).toBe(1)   // 只有 power
    expect(idw.findAll('select').length).toBe(1)                // 只有 cross_shed
    expect(idw.text()).toContain('metric.ly')
    expect(idw.text()).toContain('从未进过搜索空间')
  })

  it('标签的 for 与控件的 id 对得上（读屏与点标签都要靠它）', () => {
    const w = show()
    for (const el of w.findAll('label')) {
      const id = el.attributes('for')!
      expect(w.find(`#${id}`).exists(), `${id} 没有对应的控件`).toBe(true)
    }
  })
})
