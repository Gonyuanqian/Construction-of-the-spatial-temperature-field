import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import TrainView from './TrainView.vue'
import { NAV_ITEMS } from '../design/copy'

const FEATURES = {
  default_groups: ['coord', 'zbasis', 'meteo', 'interaction'],
  groups: [
    { group: 'coord', columns: ['x', 'y', 'z'], n_columns: 3, what: '场的基本骨架' },
    { group: 'zbasis', columns: ['z2', 'z3'], n_columns: 2, what: '竖直方向的结构' },
    { group: 'meteo', columns: ['bg_temp', 'bg_rh', 'bg_light', 'hour', 'frac_day'],
      n_columns: 5, what: '时刻的外部条件' },
    { group: 'interaction', columns: ['bg_temp_x_z', 'bg_light_x_z', 'bg_temp_x_light'],
      n_columns: 3, what: '坐标 × 气象' },
  ],
  all_columns: ['x', 'y', 'z', 'z2', 'z3', 'bg_temp', 'bg_rh', 'bg_light', 'hour',
                'frac_day', 'bg_temp_x_z', 'bg_light_x_z', 'bg_temp_x_light'],
  // 后端给的全列计数（= 并集长度）。四组互不重叠，3+2+5+3 = 13，
  // 与 all_columns.length 一致 —— mock 别自相矛盾。
  n_all_columns: 13,
  notes: ['不加滞后特征：本版是重建任务。', '不加测点湿度：目标点的湿度同样是未知量。'],
}

const CAL = {
  present: true,
  reason: null,
  created_at: '2026-10-03T13:22:00+00:00',
  tool_version: '0.1.0',
  groups_sig: 'd6294c09',
  dataset_sig: '6145fa9261e89f1b',
  feature_groups: ['coord', 'zbasis', 'meteo', 'interaction'],
  trend_kind: 'xgboost',
  tuned_keys: [{ key: 'metric.power', value: '0.5', space: '0.5、1、2' }],
  params: [
    { param: 'metric.power', value: '0.5', note: 'IDW 距离幂' },
    { param: 'metric.ly', value: '1', note: '固定 1.0，从未进过搜索空间' },
  ],
  plateau: [{ dim: 'power', lo: '0.5', hi: '2' }],
  lz_note: '⚠️ lz = 0.005 落在搜索下界（0.005），这不是已收敛。',
  metrics: [
    { mae: 0.1172, rmse: 0.1641, r2: 0.999, fold_kind: 'position',
      fold: 'position:x0.15_z0.4', region: '切面内', group: 'A', n: 3924, tag: 'calibration' },
    { mae: 0.1374, rmse: 0.18, r2: 0.998, fold_kind: 'position',
      fold: 'position:x0.4_z0.7', region: '切面内', group: 'A', n: 3924, tag: 'calibration' },
  ],
  per_point: [
    { sensor_id: 0, shed: 'p1', position: 'x0.15_z0.4', layer: 'z0.4',
      group: 'A', n: 1308, mae: 0.1077, rmse: 0.1666, r2: 0.9989 },
  ],
  ab: { mae_a: 0.115698, mae_b: 0.162401, gap: -0.046703 },
  fold_kind: 'position',
  n_folds: 2,
  worst_fold: { fold: 'position:x0.4_z0.7', mae: 0.1374 },
  ab_note: 'gap = A 组 MAE − B 组 MAE。负数是好消息。',
  note: '「最优」最优的对象是这一份数据集 + 这一组特征组 + 留一测点这个准则，' +
        '而且参数只在 A 组上挑出来的。没有标定包时用的是兜底参数，那不是最优。',
}

function stub(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const hit = Object.keys(routes).find((k) => String(url).includes(k))
    if (!hit) return new Response('{}', { status: 404 })
    return new Response(JSON.stringify(routes[hit]), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
}

describe('页② 模型训练', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('三段的次序就是流水线的次序', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    // 直接断言三个 <h3>：三段小标题互不相同，既无歧义又更强 ——
    // 用 `text.indexOf('模型训练')` 会被页顶 <h2>模型训练</h2> 抢先命中（索引 0），
    // 测的就不是次序了。这条同时钉住「次序」与「恰好三段」。
    const h3 = w.findAll('h3').map((e) => e.text())
    expect(h3).toEqual(['特征值的构造', '最优参数的选择', '模型训练'])
  })

  it('特征构造表逐组列出列名与列数', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    for (const g of FEATURES.groups) {
      expect(w.text()).toContain(g.group)
      for (const c of g.columns) expect(w.text()).toContain(c)
    }
  })

  it('最优参数表把「当前值」和「从哪些值里挑的」并排放', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('metric.power')
    expect(w.text()).toContain('0.5、1、2')
  })

  it('口径说明原样显示 —— 这一页最大的谎就在这句话缺位的时候', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('留一测点')
    expect(w.text()).toContain('兜底参数')
    expect(w.text()).toContain('只在 A 组上挑出来的')
  })

  it('lz 贴着搜索下界时那句警告看得见', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('不是已收敛')
  })

  it('逐折误差逐行渲染，最差的那一折标出来', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('position:x0.15_z0.4')
    expect(w.text()).toContain('最差')
  })

  it('A/B 两组都报，负的 gap 自己解释清楚', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('0.115698')
    expect(w.text()).toContain('0.162401')
    expect(w.text()).toContain('负数是好消息')
  })

  it('没有标定包时说「未标定」，并提示跑一次标定', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false,
        reason: '这一份数据集还没有标定包。',
        metrics: [], per_point: [], ab: null, worst_fold: null, lz_note: null,
        params: [{ param: 'metric.lx', value: '2', note: '' }],
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('未标定')
    expect(w.text()).toContain('还没有标定包')
    expect(w.text()).toContain('metric.lx')
  })

  it('随包数字与现场重算分得开（出处标记）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('随标定包')
  })

  it('页标题就是导航里那条的标签（房规：页标题 = 导航标签）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('h2').text())
      .toBe(NAV_ITEMS.find((i) => i.key === 'train')!.label)
  })

  it('某折的 MAE 是 null 时那行照样渲染，无值显示单个破折号「—」', async () => {
    // 后端把 NaN/Inf 翻成 null（`calibration.py:_finite`），「这一折算不出来」
    // 是合法状态。断言**渲染成功** —— 失败形态是未处理的 async rejection，
    // 只写「mount 不抛」会假绿，所以这里要求那一折的行真的出现在表里。
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL,
        metrics: [
          { ...CAL.metrics[0] },
          { ...CAL.metrics[1], mae: null, rmse: null, r2: null },
        ],
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    const rows = w.findAll('tbody tr').map((r) => r.text())
    const row = rows.find((t) => t.includes('position:x0.4_z0.7'))
    expect(row, '这一折真实存在，指标为 null 不能让它整行消失').toBeDefined()
    expect(row).toContain('—')
  })

  it('A/B 组的数也可以是 null，表格显示无值而不是崩', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': { ...CAL, ab: { mae_a: null, mae_b: 0.162401, gap: null } },
    })
    const w = mount(TrainView)
    await flushPromises()
    const rows = w.findAll('tbody tr').map((r) => r.text())
    const rowA = rows.find((t) => t.includes('挑参数用的那一组'))
    expect(rowA, 'A 组那一行要渲染出来').toBeDefined()
    expect(rowA).toContain('—')
  })

  it('上屏的文字里没有被禁的连接符与 markdown 标记', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const text = w.text()
    // 单个「—」是表格里「无值」的占位，不禁；被禁的是连接词用的成对破折号。
    expect(text).not.toContain('——')
    expect(text).not.toContain('**')            // markdown 星号不许漏成字面字符
    expect(text).not.toContain('`')             // markdown 反引号同理
    expect(text).not.toContain(' · ')           // 中点元信息串
    expect(text).not.toContain('→')
    expect(text).not.toContain('↳')
  })
})
