import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ParamPanel from './ParamPanel.vue'
import type { CalibrationPanel, ParamValue } from '../api/types'

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

const VALUES: Record<string, ParamValue> = {
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
    // ⚠️ 第二行不是可有可无的重复：`cross_shed` 的 `values` 是 `['开', '关']`，
    // 而 `raw` 是 `[true, false]` —— 印错一列就会印成「true / false」。
    // 这份分辨力原来落在每行末尾那个当前值上（见下一条用例），
    // 那个删掉之后，由选项这一份接住。
    expect(selects[1].findAll('option').map((o) => o.text()))
      .toEqual(PANEL.idw[1].values)
  })

  it('选了下拉的第 n 项，发出去的也是 raw[n]', async () => {
    const w = show()
    const sel = w.findAll('select')[0]
    ;(sel.element as HTMLSelectElement).value = '1'
    await sel.trigger('change')
    expect(w.emitted('pick')?.[0]).toEqual(['trend.objective', 'reg:absoluteerror'])
  })

  it('每行末尾不再重复一遍当前值；滑块的值改走 aria-valuetext', () => {
    // 走查时定的：档位由把手落在哪个刻度上表示，下拉自己就显示着当前那一项，
    // 末尾再印一个当前值是重复。而且它与刻度标签落在同一行，屏上读成
    // 「3 4 5 6 3」——「6」后面挂着一个孤零零的「3」，看着像排版出错。
    //
    // ⚠️ 删掉可见的那个之后，**值得有别的去处**：滑块的取值语义是**下标**，
    // 读屏软件念的是「2」而不是「0.08」。所以值走 `aria-valuetext` ——
    // 认的是 `values` 那一列（印法），不是 `raw`。
    const w = show()
    expect(w.findAll('.now').length, '屏上还有重复的当前值').toBe(0)
    for (const r of [...PANEL.trend, ...PANEL.idw]) {
      const label = w.findAll('label').find((l) => l.text().includes(r.key))
      const el = w.find(`#${label!.attributes('for')}`)
      if ((el.element as HTMLElement).tagName !== 'INPUT') continue   // 下拉那一行不适用
      const i = r.raw.indexOf(VALUES[r.key])
      expect(el.attributes('aria-valuetext'), `${r.key} 的值没走 aria-valuetext`)
        .toBe(r.values[i])
    }
  })

  it('当前值不在候选里时明说一句，不装作第一个候选被选中', () => {
    // 规格书 §3.1 保证后端会把「不在候选里的当前值」并进候选，所以真实数据
    // 走不到这一支（后端那半由 `test_当前值不在候选里时并进候选` 钉着）。
    // 这一条钉的是**退化的方向**：`indexOf` 得到 -1 时，滑块会被浏览器钳在
    // **最左那一档**，看上去就像「选中了第一个候选值」—— 那正是本仓那句
    // 「屏上摆一个错的数，比摆一片空白坏得多」。所以这一支要出声。
    // （滑块的落点交给浏览器对区间的钳制，不在这里钉，那是实现细节。）
    const w = show({
      trend: [{ key: 'trend.max_depth', label: '每棵树最深几层',
                values: ['3', '4', '5', '6'], raw: [3, 4, 5, 6],
                current: 7 }],
    }, { ...VALUES, 'trend.max_depth': 7 })
    const row = w.findAll('.row').find((r) => r.text().includes('trend.max_depth'))!
    expect(row.text(), '没出声，滑块看起来就像选中了 3').toContain('当前值不在候选里')
    // 也不许编一个值出来：`values[-1]` 是 `undefined`，所以无障碍那一份就没有。
    expect(row.find('input[type="range"]').attributes('aria-valuetext'))
      .toBeUndefined()
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

  it('固定值那行的键不与中文名粘成一句', () => {
    // 上一行那一句钉的是「键在屏上」，这一句钉的是**它在屏上还认得出是键**：
    // 固定值那行是 `<p class="note">`（正文），没有控件行那种 flex 把键推到边上，
    // 中间再不留东西，屏上读到的就是「IDW y 方向尺度 / mmetric.ly」——
    // 键被读成中文名的尾巴（规格书 §2.1：标签 = 中文名 + 键，是两样东西）。
    //
    // jsdom 不做排版，所以这里钉**文本**：两个字段之间得有个字符把它们分开。
    // 融合串由**夹具自己的** label 与 key 拼出来，不写死 `'mmetric.ly'` ——
    // 写死的话，夹具一改这条就变成一句永远绿的谎话（本仓最烦的那种）。
    const w = show()
    const f = PANEL.fixed[0]
    const line = w.findAll('section')[1].find('.note')
    expect(line.text()).not.toContain(`${f.label}${f.key}`)
    expect(line.text()).toContain(f.key)      // 键还在屏上（上一句那条事实不松动）
    expect(line.text()).toContain(f.note)     // 别的部分照常渲染
  })

  it('标签的 for 与控件的 id 对得上（读屏与点标签都要靠它）', () => {
    const w = show()
    for (const el of w.findAll('label')) {
      const id = el.attributes('for')!
      expect(w.find(`#${id}`).exists(), `${id} 没有对应的控件`).toBe(true)
    }
  })
})
