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
  space: {
    trend: [
      { key: 'trend.max_depth', values: ['3', '4', '5', '6'] },
      { key: 'trend.objective', values: ['reg:squarederror', 'reg:absoluteerror'] },
    ],
    idw: [
      { key: 'metric.power', values: ['0.5', '1', '2'] },
      { key: 'cross_shed', values: ['开', '关'] },
    ],
  },
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
  job: null,
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

const DIAG = {
  present: true,
  created_at: '2026-10-05T13:52:09+00:00',
  groups_sig: 'd6294c09',
  dataset_sig: '6145fa9261e89f1b',
  n_points: 27936,
  n_sensors: 24,
  n_times: 1164,
  density: {
    bins: 60, lo: 5, hi: 45, n: 27936,
    counts: Array.from({ length: 60 }, () => Array.from({ length: 60 }, () => 0)),
  },
  accuracy: {
    folds: ['position:x0.4_z0.7', 'position:x1.05_z0.4'],
    baseline: { label: '拿背景温度当棚温（不作任何建模）',
                mae: 0.4712, rmse: 0.612, r2: 0.8896, n: 2352 },
    model: { label: '本模型（B 组，未参与选参）',
             mae: 0.168553, rmse: 0.221, r2: 0.999, n: 2352 },
    ratio: 2.7955,
  },
  residual: [
    { key: 'diurnal', label: '残差 vs 昼夜', axis: '时刻 / 时',
      bins: [{ at: 0, mean: 0.01, n: 1164, se: 0.002 },
             { at: 1, mean: -0.02, n: 1164, se: 0.003 }] },
    { key: 'height', label: '残差 vs 高度', axis: '高度 z / m',
      bins: [{ at: 0.4, mean: 0.03, n: 9000, se: 0.001 },
             { at: 0.7, mean: -0.01, n: 9000, se: 0.001 },
             { at: 1.1, mean: 0.05, n: 9936, se: 0.002 }] },
    { key: 'length', label: '残差 vs 棚长', axis: '棚长 x / m',
      bins: [{ at: 0.15, mean: 0.02, n: 4000, se: 0.002 }] },
  ],
  note: '折外预测：每一折都用不含该测点的数据重新训练。',
}

/** 挂上页②、点一次「开始训练」，把带诊断的屏交出来。 */
async function mountWithDiag(diag: unknown = DIAG) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url)
    const body = u.includes('/diagnostics') ? diag
      : u.includes('/api/calibration') ? CAL : FEATURES
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
  const w = mount(TrainView)
  await flushPromises()
  await w.findAll('button').find((b) => b.text() === '开始训练')!.trigger('click')
  await flushPromises()
  return w
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

  it('随包数字与现场重算分得开（出处图章）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const stamps = w.findAll('.prov')
    expect(stamps.length, '这一页一个出处图章都没有').toBeGreaterThan(0)
    expect(stamps.map((s) => s.text())).toContain('包')
    // 这一条要的是**两种来源都说得清自己的来历**，不是「包」恰好排在第一枚。
    // 页顶那一排指标卡插进来之后，第一枚图章是「特征列」那格的「算」
    // （它取自 /api/features，是现算的），所以按次序取 [0] 就不对了。
    const titles = stamps.map((s) => s.attributes('title') ?? '')
    expect(titles.some((t) => t.includes('随标定包'))).toBe(true)
    expect(titles.some((t) => t.includes('现场重算'))).toBe(true)
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

  it('一排指标卡，五格，其中一格不是数字（spec §6.2 页②、§十 的判据）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const cards = w.findAll('.stat')
    expect(cards.map((c) => c.find('.label').text()))
      .toEqual(['特征列', '折数', 'MAE', 'gap', '最差折'])
    // 第五格是折名，不是数 —— 通用的大数字栅格不会有这样一格
    expect(Number.isNaN(Number(cards[4].find('.value').text()))).toBe(true)
  })

  it('MAE 那一格报的是 B 组，不是挑参数用的 A 组', async () => {
    // 这是本页最贵的口径：`ab` 的 A 组 MAE（0.115698）比 B 组（0.162401）好看，
    // 而 A 组正是**拿来挑参数的那一组**。印 A 组 = 用调过参的那组自夸。
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const mae = w.findAll('.stat').find((c) => c.find('.label').text() === 'MAE')!
    expect(mae.find('.value').text()).toBe('0.162')
  })

  it('五格全挂在标定包上，图章只有一个字「包」（spec §七）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const cards = w.findAll('.stat')
    expect(cards.map((c) => c.find('.prov').text())).toEqual(['算', '包', '包', '包', '包'])
  })

  it('指标卡不改三段标题的数量与次序（spec §十三.1）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.findAll('h3').map((e) => e.text()))
      .toEqual(['特征值的构造', '最优参数的选择', '模型训练'])
    expect(w.findAll('.stat').length).toBeGreaterThan(0)
  })

  it('未标定时标定那四格一张都不渲染 —— 包里没有的数不许凑（spec §6.2）', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, reason: '还没有标定包',
        metrics: [], params: [], plateau: [], tuned_keys: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    const labels = w.findAll('.stat').map((c) => c.find('.label').text())
    expect(labels).toEqual(['特征列'])
  })

  it('散文折进唯一一处「口径与出处」', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why.length).toBe(1)
    expect(why[0].text()).toContain('留一测点')
  })

  it('换数据集之后说清「参数与当前数据集不匹配」，并给出该跑哪条命令', async () => {
    // 规格书 §七。这一句与「还没标定」是**两件事**：
    // 后者是系统的正常起点，前者说明屏上这些数背后是另一份数据。
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL,
        present: false,
        reason: '这一份数据集还没有标定包。',
        mismatch: { dataset_sig: '别的签名', created_at: '2026-07-27T20:00:00',
                    file: 'bundle_x-h20260727T1200_abc.json' },
        metrics: [], params: [], plateau: [], tuned_keys: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('参数与当前数据集不匹配')
    expect(w.text()).toContain('2026-07-27T20:00:00')
    expect(w.text()).toContain('scripts/calibrate.py')
  })

  it('没有 mismatch 时不说那句话 —— 「从来没标过」是另一件事', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, reason: '这一份数据集还没有标定包。', mismatch: null,
        metrics: [], params: [], plateau: [], tuned_keys: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).not.toContain('参数与当前数据集不匹配')
  })

  it('第二段在点之前就列出十二个待优选参数', async () => {
    // T15：§三 的关键在「先」字。这份清单必须在点之前就在屏上，
    // 否则它就是「跑完才知道要搜什么」。
    // ⚠️ 用 present:false 的载荷 —— 空态是唯一能证明「清单与包无关」的地方。
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, reason: '还没有标定包',
        metrics: [], params: [], plateau: [], tuned_keys: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    const text = w.text()
    expect(text).toContain('trend.max_depth')
    expect(text).toContain('trend.objective')
    expect(text).toContain('metric.power')
    expect(text).toContain('cross_shed')
    // 候选值也上屏 —— 只列参数名是「要搜什么」缺了一半
    expect(text).toContain('reg:absoluteerror')
    expect(text).toContain('开')
  })

  it('刷新之后自发改去轮询载荷里那个正在跑的 job', async () => {
    // T19 与 §4.7：切页与刷新都会把组件连同它手上的 job id 一起丢掉，
    // 所以「还有没有一次在跑」只能从每次进页都要读的那张载荷上问。
    const urls: string[] = []
    const RUN = { id: 'j7', state: 'running', progress: '阶段 1 扫描',
                  elapsed_s: 2.5, error: null, created_at: '2026-10-07T10:00:00+00:00' }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      urls.push(String(url))
      if (String(url).includes('/api/calibration/jobs/j7')) {
        return new Response(JSON.stringify(RUN), { status: 200,
          headers: { 'Content-Type': 'application/json' } })
      }
      if (String(url).includes('/api/calibration')) {
        return new Response(JSON.stringify({ ...CAL, job: RUN }), { status: 200,
          headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify(FEATURES), { status: 200,
        headers: { 'Content-Type': 'application/json' } })
    }))
    const w = mount(TrainView)
    await flushPromises()
    expect(urls.some((u) => u.includes('/api/calibration/jobs/j7')),
      '刷新之后没有接上那个正在跑的 job').toBe(true)
    expect(w.text()).toContain('阶段 1 扫描')
    // 卸载时必须停表，否则离开这一页之后它还在每秒发请求
    w.unmount()
  })

  it('三段标题一个字没变（T13）', async () => {
    // 上面那两条已经在别的用例里钉着，这一条把「加了按钮之后」再说一遍。
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.findAll('h3').map((e) => e.text()))
      .toEqual(['特征值的构造', '最优参数的选择', '模型训练'])
  })

  // ⚠️ 下面两条是从 Task 7 挪过来的：它们在计划的 Task 7 里，
  // 而「开始训练」那个按钮由本任务（第三段）产出 —— 写在 Task 7 里不可能绿。
  // 见台账 Task 7 那条 Ruling。

  it('两个按钮都在，且没包时「开始训练」是禁用的', async () => {
    // T14：房规 —— 不做点了没反应的按钮（与页①「没选文件就禁用」同一条）。
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, reason: '还没有标定包',
        metrics: [], params: [], plateau: [], tuned_keys: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    const labels = w.findAll('button').map((b) => b.text())
    expect(labels).toContain('参数优选')
    expect(labels).toContain('开始训练')
    const train = w.findAll('button').find((b) => b.text() === '开始训练')!
    expect(train.attributes('disabled')).toBeDefined()
    // 「先做参数优选」写在按钮旁边，不是一个禁用了却不说话的按钮
    expect(w.text()).toContain('先做参数优选')
  })

  it('有包时「开始训练」可点，「参数优选」永远可点', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const train = w.findAll('button').find((b) => b.text() === '开始训练')!
    const opt = w.findAll('button').find((b) => b.text() === '参数优选')!
    expect(train.attributes('disabled')).toBeUndefined()
    expect(opt.attributes('disabled')).toBeUndefined()
  })

  it('「开始训练」打的是诊断出口，不是又搜一遍参数', async () => {
    // T20：把轻的做成重的 —— 用户只想更新精度，却重搜了一遍参数（几分钟）。
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      urls.push(String(url))
      const body = String(url).includes('/diagnostics') ? DIAG
        : String(url).includes('/api/calibration') ? CAL : FEATURES
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }))
    const w = mount(TrainView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === '开始训练')!.trigger('click')
    await flushPromises()
    expect(urls.some((u) => u.includes('/api/calibration/diagnostics'))).toBe(true)
    expect(urls.some((u) => u.includes('/api/calibration/jobs'))).toBe(false)
  })

  it('基线永远跟模型并排，两行一起出来', async () => {
    // T16：单独一个 0.999 会被读成「几乎完美」。旁边那个基线才说明尺子有多粗。
    const w = await mountWithDiag()
    const rows = w.findAll('tbody tr').map((r) => r.text())
    const base = rows.find((t) => t.includes('拿背景温度当棚温'))!
    const model = rows.find((t) => t.includes('未参与选参'))!
    expect(base).toBeDefined()
    expect(model).toBeDefined()
    expect(w.text()).toContain('2.8 倍')
  })

  it('基线算不出来时，模型那一行**单独**不许出现', async () => {
    // T16 的反面：宁可什么都不给，也不给一个没有尺子的读数。
    const broken = { ...DIAG, accuracy: { ...DIAG.accuracy,
      baseline: { ...DIAG.accuracy.baseline, mae: null, rmse: null, r2: null } } }
    const w = await mountWithDiag(broken)
    const rows = w.findAll('tbody tr').map((r) => r.text())
    expect(rows.some((t) => t.includes('未参与选参')),
      '基线没算出来时不许只渲染模型那一行').toBe(false)
    expect(w.text()).toContain('基线没算出来')
  })

  it('点完训练之后，指标卡里多一格「基线 MAE」，图章是「算」', async () => {
    // 基线是**现场算的**（它不在标定包里），所以它的图章是「算」不是「包」——
    // 两组图章在同一个页面上同时出现，正是 §七 那套三态要表达的东西。
    const w = await mountWithDiag()
    const cards = w.findAll('.stat')
    expect(cards.map((c) => c.find('.label').text()))
      .toEqual(['特征列', '折数', 'MAE', '基线 MAE', 'gap', '最差折'])
    expect(cards.map((c) => c.find('.prov').text()))
      .toEqual(['算', '包', '包', '算', '包', '包'])
  })

  it('没点训练之前没有「基线 MAE」那一格', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.findAll('.stat').map((c) => c.find('.label').text()))
      .toEqual(['特征列', '折数', 'MAE', 'gap', '最差折'])
  })
})
