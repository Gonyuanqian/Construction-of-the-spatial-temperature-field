import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import TrainView from './TrainView.vue'
import ParamPanel from '../components/ParamPanel.vue'
import { MODELS, NAV_ITEMS } from '../design/copy'

/**
 * jsdom 里没有 canvas，而 `EChart` 一挂上就 `echarts.init` + `setOption` ——
 * zrender 拿到的 2d 上下文是 `null`（jsdom 只打一句「Not implemented」），
 * 紧接着写 `ctx.dpr` 就抛，抛在挂载钩子里，整个 wrapper 跟着废掉。
 * 这一组测的是取数、按钮、文案与表，**不是画图** —— 与 `LiveView.test.ts`、
 * `routes.smoke.test.ts` 同一个处置。「画得对不对」由 `EChart.test.ts`
 * 与页③ 那组测试兜着，不靠这里。
 *
 * ⚠️ 页② 到 Task 10 才第一次有图，所以这个 mock 也是那时才加的。
 */
vi.mock('../charts/EChart.vue', () => ({
  default: {
    name: 'EChart', props: ['option', 'height'], template: '<div class="chart-stub" />',
  },
}))

/**
 * 环境夹具，与页①③⑤ 同款（Ruling P5）：
 * 一是**令牌**——`readPalette()` 读不到 `tokens.css` 的变量就抛错，
 * jsdom 不会去加载那个样式表；二是 `ResizeObserver`——jsdom 里没有，
 * 而 `EChart.vue` 挂载时要建一个。
 *
 * 页② 到本任务才第一次用到这两样（此前这一页一张图都没有）。
 */
function installEnvironment(): void {
  const root = document.documentElement
  root.style.setProperty('--paper', '#F7F6F2')
  root.style.setProperty('--ink', '#211F1C')
  root.style.setProperty('--ink-muted', '#5C5850')
  root.style.setProperty('--steel', '#DEDCD6')
  root.style.setProperty('--leaf', '#14532D')
  root.style.setProperty('--leaf-soft', '#E7EFE9')
  root.style.setProperty('--net', '#0B0F0D')
  root.style.setProperty('--layer-top', '#C44E52')
  root.style.setProperty('--layer-mid', '#4C72B0')
  root.style.setProperty('--layer-low', '#55A868')
  root.style.setProperty('--bar', '#D98C2B')
  root.style.setProperty('--size-chart-axis', '12px')
  root.style.setProperty('--size-chart-title', '14px')
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
}

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
  // 这一份的来路是**库里的当前模型**（不是刚跑完那份）。
  // 「保存到模型库」那一组用例拿它当对照物 —— 见下面 `LIB`。
  source: 'library',
  created_at: '2026-10-03T13:22:00+00:00',
  tool_version: '0.1.0',
  groups_sig: 'd6294c09',
  dataset_sig: '6145fa9261e89f1b',
  feature_groups: ['coord', 'zbasis', 'meteo', 'interaction'],
  trend_kind: 'xgboost',
  // 面板：**一套值，两条来路**。十二维 = 8 + 4 一维都不能少 ——
  // `:455-477` 那条用例名字里的「十二个」、`:212-218` 改写后的「十二个键
  // 都在屏上」、以及 T5 那条「发出去的正是屏上这十二个」，都要靠这份夹具摆全。
  // 自洽的三条（mock 别自相矛盾）：`values` 与 `raw` 同长且同下标、
  // `current` 一定在 `raw` 里、布尔印成「开 / 关」而不是 `true`。
  // 次序照后端给的（`TUNED_KEYS`，也就是 `_params` 里那个次序）。
  //
  // ⚠️ XGBoost 那八维的候选值**不是** `IDW_SPACE` / `TREND_SPACE` 的逐字复刻
  // （那是后端 `test_api_train.py` 的事），这里是一份自洽的示意值。
  // 但对得上号的那几个必须对：`reg:absoluteerror`（`:475` 逐字引用）、
  // `开`（`:476`）、以及十二个 key（`:470-473` 抽查其中四个）。
  panel: {
    trend: [
      { key: 'trend.objective', label: '目标函数',
        values: ['reg:squarederror', 'reg:absoluteerror'],
        raw: ['reg:squarederror', 'reg:absoluteerror'], current: 'reg:squarederror' },
      { key: 'trend.max_depth', label: '每棵树最深几层',
        values: ['3', '4', '5', '6'], raw: [3, 4, 5, 6], current: 4 },
      { key: 'trend.learning_rate', label: '学习率',
        values: ['0.03', '0.05', '0.08', '0.12'], raw: [0.03, 0.05, 0.08, 0.12],
        current: 0.08 },
      { key: 'trend.n_estimators', label: '树的数量',
        values: ['100', '200', '400'], raw: [100, 200, 400], current: 200 },
      { key: 'trend.min_child_weight', label: '叶子最小样本权重和',
        values: ['1', '3', '5', '10'], raw: [1, 3, 5, 10], current: 3 },
      { key: 'trend.subsample', label: '行采样比例',
        values: ['0.7', '0.85', '1'], raw: [0.7, 0.85, 1], current: 0.85 },
      { key: 'trend.colsample_bytree', label: '列采样比例',
        values: ['0.6', '0.8', '1'], raw: [0.6, 0.8, 1], current: 0.8 },
      { key: 'trend.reg_lambda', label: 'L2 正则系数',
        values: ['0.1', '1', '3', '10'], raw: [0.1, 1, 3, 10], current: 1 },
    ],
    idw: [
      { key: 'metric.power', label: 'IDW 距离幂',
        values: ['0.5', '1', '1.5', '2', '2.5', '3', '4'],
        raw: [0.5, 1, 1.5, 2, 2.5, 3, 4], current: 0.5 },
      { key: 'metric.lx', label: 'IDW 棚长方向尺度 / m',
        values: ['0.5', '1', '2', '3'], raw: [0.5, 1, 2, 3], current: 2 },
      { key: 'metric.lz', label: 'IDW 竖直方向尺度 / m',
        values: ['0.005', '0.01', '0.03', '0.12'], raw: [0.005, 0.01, 0.03, 0.12],
        current: 0.005 },
      { key: 'cross_shed', label: '跨棚邻居是否参与',
        values: ['开', '关'], raw: [true, false], current: true },
    ],
    fixed: [{ key: 'metric.ly', label: 'IDW y 方向尺度 / m', value: '1',
              note: '固定 1.0，从未进过搜索空间' }],
  },
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
  // ⚠️ **与 `CAL.created_at` 逐字相同，这不是巧合。** 后端的两个接口各自回
  // 这一格，取值都是**同一份标定包的** `bundle.created_at`
  // （`routes/calibration.py:322`、`:93`）。这一页据此判断「屏上这份诊断
  // 是不是屏上这份包算的」（见 `diagForBundle`），所以夹具里让它俩相等
  // 才是真实的那一对回包 —— 原来这里是随手写的另一个时刻。
  created_at: '2026-10-03T13:22:00+00:00',
  groups_sig: 'd6294c09',
  dataset_sig: '6145fa9261e89f1b',
  n_points: 27936,
  n_sensors: 24,
  n_times: 1164,
  // 屏上那份诊断是拿**哪一套**参数算的。后端把请求体里那十二个值原样回在
  // 这里。与 `CAL.panel` 的十二个 `current` 逐位一致 —— 不一致的那一种由
  // 「参数改过之后，屏上那份精度不作数」自己覆盖，别在这里调。
  params_used: {
    'trend.objective': 'reg:squarederror', 'trend.max_depth': 4,
    'trend.learning_rate': 0.08, 'trend.n_estimators': 200,
    'trend.min_child_weight': 3, 'trend.subsample': 0.85,
    'trend.colsample_bytree': 0.8, 'trend.reg_lambda': 1,
    'metric.power': 0.5, 'metric.lx': 2, 'metric.lz': 0.005,
    'cross_shed': true,
  },
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

/** 面板里某一维那一行。**按 key 找，不按次序找** —— 十二行里屏上第一个
    `.row` 是 `trend.objective`，不是 `trend.max_depth`：`w.find('.row')`
    拿到的是**目标函数**那一格。 */
function rowOf(w: ReturnType<typeof mount>, key: string) {
  return w.findAll('.panel .row').find((r) => r.text().includes(key))!
}

describe('页② 模型训练', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
    // 有一条用例要推进 1 秒的轮询间隔（见「任务跑完之后重取标定包」），
    // 万一它红了，假表会留给后面的用例 —— 这里兜一道。
    vi.useRealTimers()
  })

  it('标题旁显示当前数据集文件名，并去除服务器路径', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL,
      '/api/dataset': { file: 'C:/datasets/B_validation.xlsx' } })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.dataset-badge strong').text()).toBe('B_validation.xlsx')
  })

  it('三段的次序就是流水线的次序', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    // 直接断言三个 <h3>：三段小标题互不相同，既无歧义又更强 ——
    // 用 `text.indexOf('模型训练')` 会被页顶 <h2>模型训练</h2> 抢先命中（索引 0），
    // 测的就不是次序了。这条同时钉住「次序」与「恰好三段」。
    const h3 = w.findAll('h3').map((e) => e.text())
    expect(h3).toEqual(['特征构造', '参数配置', '空间验证结果', '模型训练'])
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

  it('面板上十二个键、各自的候选值、当前那一档，都在屏上', async () => {
    // 这条原来叫「最优参数表把『当前值』和『从哪些值里挑的』并排放」，盯的是
    // 那张连接表里 `metric.power` 与 `0.5、1、2` 同屏。它防的是**清单与最优
    // 参数表对不上号**（两个键空间不一样，见后端 `_SPACE_KEY`）。
    // 判据换成同屏的四样（规格书 §六 给的新判据）：十二个键、每个键的中文名、
    // 它的**全部**候选值、它当前那一档。
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const text = w.text()
    for (const r of [...CAL.panel.trend, ...CAL.panel.idw]) {
      expect(text, `${r.key} 没在屏上`).toContain(r.key)
      expect(text, `${r.key} 的中文名没在屏上`).toContain(r.label)
      // ⚠️ 候选值那一列**逐条比这个面板自己的元素**，不比整页文本：
      // 页面上到处都是数字，`expect(text).toContain('1')` 那种断言等于没断。
      const row = rowOf(w, r.key)
      const opts = row.findAll('option')
      const printed = opts.length
        ? opts.map((o) => o.text())
        : row.findAll('.ticks span').map((s) => s.text())
      expect(printed, `${r.key} 的候选值印错了`).toEqual(r.values)
    }
  })

  it('参数只住在一个地方：面板，不再是几张并排的表', async () => {
    // 这条原来盯「最优参数的选择」这张卡里的 h4 恰好是两个 ——
    // 它防的是**同一件事在屏上说了两遍**（那次删掉的是「这些参数真的进过
    // 搜索空间」那张连接表）。判据换成：这一段里**一张表都没有**，
    // 参数全部住在面板里。
    // 直接扫「这一段里还有没有 table」，比扫 h4 的字面更贴近它防的事 ——
    // h4 的名字以后还会变（比如两个区块改名），而「参数不该是表格」不会。
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    // 按「哪一段装着面板」找那一段，不按小标题的字面找 —— 标题以后会改，
    // 而「参数住在这一段」不会。找不到时断言自己会说话，不要留一个 `!`。
    const card = w.findAll('.block').find((b) => b.findComponent(ParamPanel).exists())
    expect(card, '找不到装着参数面板的那一段').toBeTruthy()
    const tables = card!.findAll('table').map((t) =>
      t.findAll('th').map((th) => th.text()))
    // 这一段里只剩平台区间那一张（维度 / 下界 / 上界）：十二个参数一张表都没有。
    expect(tables).toEqual([])
    expect(w.find('.optimization-results .parameter-ranges').exists()).toBe(true)
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
    expect(w.text()).toContain('0.1157')
    expect(w.text()).toContain('0.1624')
    expect(w.text()).toContain('负数是好消息')
  })

  it('逐点误差那张明细表不上屏（接口照旧回它，只是不画）', async () => {
    // 头一句是**非空断言**，不是装饰：夹具里没数据时，「不显示」是自己成立的，
    // 下面两条会照样绿 —— 那就成了一句永远绿的谎话，测不出删没删干净。
    expect(CAL.per_point.length, '夹具里没有逐点明细，这条测不出东西').toBeGreaterThan(0)
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).not.toContain('逐点误差')
    // 比小标题字面更硬的一条：`点位` 这一列只属于那张表。
    expect(w.findAll('th').map((t) => t.text())).not.toContain('点位')
  })

  it('没有标定包时说「未标定」，并提示跑一次标定', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false,
        reason: '这一份数据集还没有标定包。',
        metrics: [], per_point: [], ab: null, worst_fold: null, lz_note: null,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('未标定')
    expect(w.text()).toContain('还没有标定包')
    expect(w.text()).toContain('metric.lx')
  })

  it('没有优选记录时等待完成，不展示历史验证数值', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, source: null, reason: '尚未完成参数优选',
        metrics: [], per_point: [], ab: null, worst_fold: null,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.optimization-status').attributes('title')).toBe('等待参数优选完成')
    expect(w.find('.optimization-empty').text()).toContain('点击「参数优选」并等待完成')
    expect(w.find('.selection-scores').exists()).toBe(false)
    expect(w.find('.optimization-metrics').exists()).toBe(false)
  })

  it('参数优选正在运行且尚无记录时显示进度，不提前展示成绩', async () => {
    const running = {
      id: 'j7', state: 'running', progress: '正在搜索参数', elapsed_s: 3,
      error: null, created_at: '2026-10-26T13:00:00+00:00',
    }
    stub({
      '/api/calibration/jobs/j7': running,
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, source: null, reason: '尚未完成参数优选',
        metrics: [], per_point: [], ab: null, worst_fold: null, job: running,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.optimization-status').attributes('title')).toBe('参数优选进行中')
    expect(w.find('.optimization-empty').text()).toContain('优选完成后')
    expect(w.find('.selection-scores').exists()).toBe(false)
    w.unmount()
  })

  it('已有模型库记录时标明来源，避免被误认成刚完成的优选', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.optimization-status').attributes('title')).toBe('已有模型库优选记录')
    expect(w.find('.optimization-results').text()).toContain('当前展示模型库中已保存的历史优选记录')
    expect(w.find('.selection-scores').exists()).toBe(true)
  })

  it('模型库记录属于其他数据集时等待当前数据优选，不展示旧误差', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': { ...CAL, mismatch_note: '参数不是用当前数据标出来的' },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.optimization-status').attributes('title')).toBe('等待当前数据集参数优选完成')
    expect(w.find('.optimization-empty').text()).toContain('现有验证结果属于其他数据集')
    expect(w.find('.selection-scores').exists()).toBe(false)
    expect(w.find('.optimization-metrics').exists()).toBe(false)
    expect(w.findAll('.stat').map(card => card.text()).join('')).not.toContain('空间留出 MAE')
  })

  it('未保存的优选结果与模型库历史记录显示不同状态', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': { ...CAL, source: 'unsaved' } })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.optimization-status').attributes('title')).toBe('已有未保存的优选记录')
    expect(w.find('.optimization-results').text()).toContain('结果尚未保存到模型库')
  })

  it('随包数字与现场重算分得开（出处图章）', async () => {
    const w = await mountWithDiag()
    const titles = w.findAll('.prov').map(stamp => stamp.attributes('title') ?? '')
    expect(titles.some(title => title.includes('随标定包'))).toBe(true)
    expect(titles.some(title => title.includes('现场重算'))).toBe(true)
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
    stub({ '/api/features': FEATURES,
      '/api/calibration': { ...CAL, ab: { mae_a: null, mae_b: 0.162401, gap: null } } })
    const w = mount(TrainView)
    await flushPromises()
    const scores = w.findAll('.selection-scores > div')
    expect(scores[0].find('dd').text()).toBe('—')
    expect(scores[1].find('dd').text()).toBe('0.1624')
    expect(scores[2].find('dd').text()).toBe('—')
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

  it('特征数量与验证摘要各归所属区域，保留最差折名称', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.feature-count').text()).toBe('13 个特征')
    expect(w.findAll('.selection-scores > div')).toHaveLength(3)
    expect(w.find('.record-meta').text()).toContain(CAL.worst_fold.fold)
  })

  it('MAE 那一格报的是 B 组，不是挑参数用的 A 组', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const holdout = w.findAll('.selection-scores > div')
      .find(score => score.find('dt').text() === '空间留出组 MAE / ℃')!
    expect(holdout.find('dd').text()).toBe('0.1624')
  })

  it('空间验证记录的来源标注为标定包', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.record-description .prov').text()).toBe('包')
  })

  it('指标卡不改三段标题的数量与次序（spec §十三.1）', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.findAll('h3').map((e) => e.text()))
      .toEqual(['特征构造', '参数配置', '空间验证结果', '模型训练'])
    expect(w.find('.selection-scores').exists()).toBe(true)
  })

  it('未标定时标定那四格一张都不渲染 —— 包里没有的数不许凑（spec §6.2）', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, reason: '还没有标定包',
        metrics: [], plateau: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.feature-count').text()).toBe('13 个特征')
    expect(w.find('.selection-scores').exists()).toBe(false)
  })

  it('散文折进唯一一处「口径与出处」', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why.length).toBe(1)
    expect(why[0].text()).toContain('留一测点')
  })

  it('换数据集后指出历史记录时间，并提示为当前数据重新优选', async () => {
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
        metrics: [], plateau: [],
        worst_fold: null, ab: null, n_folds: 0,
      },
    })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('上次优选记录对应')
    expect(w.text()).toContain('2026-07-27T20:00:00')
    expect(w.text()).toContain('请为当前数据集运行参数优选')
  })

  it('没有 mismatch 时不说那句话 —— 「从来没标过」是另一件事', async () => {
    stub({
      '/api/features': FEATURES,
      '/api/calibration': {
        ...CAL, present: false, reason: '这一份数据集还没有标定包。', mismatch: null,
        metrics: [], plateau: [],
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
        metrics: [], plateau: [],
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
      .toEqual(['特征构造', '参数配置', '空间验证结果', '模型训练'])
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
        metrics: [], plateau: [],
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

  it('训练完成后在右侧展示诊断，可切回空间验证', async () => {
    const w = await mountWithDiag()
    expect(w.find('.diagnostics-body').text()).toContain(DIAG.accuracy.baseline.label)
    expect(w.find('.diagnostics-body').text()).toContain(DIAG.accuracy.baseline.mae.toFixed(4))
    expect(w.find('.diagnostics-body .prov').text()).toBe('算')
    await w.findAll('.result-tabs button').find(button => button.text() === '空间验证')!.trigger('click')
    expect(w.find('.selection-scores').exists()).toBe(true)
    expect(w.find('.record-description .prov').text()).toBe('包')
  })

  it('未训练时显示验证记录，训练状态为尚未开始', async () => {
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.diagnostics-body').exists()).toBe(false)
    expect(w.text()).not.toContain(DIAG.accuracy.baseline.label)
    expect(w.find('.training-status').text()).toBe('尚未开始')
  })

  it('点完训练之后两张图都挂上去了', async () => {
    // 图是**后端算好送上来的** —— 这一页没有一处计算（硬约束 1）。
    // 这里断言的是「两张图各自的 option 都被构造出来了」，
    // 画得对不对由 routes.smoke.test.ts 的路由冒烟兜底。
    // 数的是**组件**不是 `.chart`：`EChart` 在本文件里是替身（见文件顶的
    // mock），按名字找才不依赖替身那行模板长什么样。
    const w = await mountWithDiag()
    expect(w.findAllComponents({ name: 'EChart' })).toHaveLength(4)   // 1 密度 + 3 残差
  })

  it('残差三连是按后端给的项数与次序渲染的', async () => {
    const w = await mountWithDiag()
    const text = w.text()
    expect(text).toContain('残差 vs 昼夜')
    expect(text).toContain('残差 vs 高度')
    expect(text).toContain('残差 vs 棚长')
  })

  it('上屏文案（含新增的口径）仍然没有禁用字形', async () => {
    const w = await mountWithDiag()
    const text = w.text()
    expect(text).not.toContain('——')
    expect(text).not.toContain('**')
    expect(text).not.toContain('`')
    expect(text).not.toContain(' · ')
    expect(text).not.toContain('→')
    expect(text).not.toContain('↳')
  })

  it('任务跑完之后重取一次标定包（T18 的后半）', async () => {
    // `done` 是后端在包**写回之后**才置的（规格书 §5.1 第 4 步），所以这一刻
    // 盘上已经换成新的那一份了。不重取的话，屏上的参数表与指标卡还是
    // 上一次那份，而轮询那一行已经写着「标定完成」。
    vi.useFakeTimers()
    const urls: string[] = []
    let polls = 0
    const RUN = { id: 'j9', state: 'running', progress: '阶段 2 试验之间',
                  elapsed_s: 3.2, error: null, created_at: '2026-10-07T10:00:00+00:00' }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      urls.push(u)
      let body: unknown = FEATURES
      if (u.includes('/api/calibration/jobs/')) {          // 轮询（带 id）
        polls += 1
        body = polls >= 2 ? { ...RUN, state: 'done', progress: '', elapsed_s: 41.7 } : RUN
      } else if (u.includes('/api/calibration/jobs')) {    // 提交（POST，不带 id）
        body = RUN
      } else if (u.includes('/api/calibration')) {
        body = CAL
      }
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }))
    const w = mount(TrainView)
    await flushPromises()
    const cals = () => urls.filter((u) => u.endsWith('/api/calibration')).length
    expect(cals(), '进页那一次标定包没取').toBe(1)

    await w.findAll('button').find((b) => b.text() === '参数优选')!.trigger('click')
    await flushPromises()
    expect(polls, '提交之后没有立刻轮询一次').toBe(1)

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(cals(), '任务跑完之后没有重取标定包').toBe(2)
    expect(w.find('.optimization-progress').text()).toContain('标定完成')
    w.unmount()
  })

  it('包换过之后，上一份包算出来的精度整块不显示，并说清为什么', async () => {
    // 点过「开始训练」之后再去点「参数优选」，包就换了新的；而诊断是
    // **按包缓存**的（`diagnostics.py`），屏上这一份还是上一份包算的。
    // 不挡它的话：新的参数表、新的指标卡旁边挂着上一份包的基线行、
    // 倍数行与两张图，而它们**全都盖着「算」这张图章**。一屏两套数，
    // 且从屏上看不出哪一个是哪一份包的。
    const stale = { ...DIAG, created_at: '2026-10-01T08:00:00+00:00' }
    const w = await mountWithDiag(stale)
    const rows = w.findAll('tbody tr').map((r) => r.text())
    expect(rows.some((t) => t.includes('拿背景温度当棚温')),
      '上一份包的基线行还在屏上').toBe(false)
    expect(w.text()).not.toContain('基线误差是模型的')
    expect(w.findAllComponents({ name: 'EChart' }),
      '上一份包的两张图还在屏上').toHaveLength(0)
    expect(w.findAll('.stat').map((c) => c.find('.label').text()),
      '上一份包的「基线 MAE」还挂在指标卡里').not.toContain('基线 MAE')
    // 不能静默：数字一转眼没了，用户得知道它们为什么没了、怎么弄回来。
    expect(w.text()).toContain('已经不作数')
  })

  it('拖动不发任何请求 —— 值只活在前端', async () => {
    // 规格书 §4.1：滑块会连续产生几十个中间值，每个都发一次请求既没意义、
    // 又会让后端缓存塞满废键。
    stub({ '/api/features': FEATURES, '/api/calibration': CAL })
    const w = mount(TrainView)
    await flushPromises()
    const calls = (fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length
    // 拿面板里那一行，不用 `findAll('input[type="range"]')[0]` —— 那是全页第一个
    // 滑块，页面上多一个滑块它就换人了。
    const slider = rowOf(w, 'trend.max_depth').find('input[type="range"]')
    ;(slider.element as HTMLInputElement).value = '1'
    await slider.trigger('input')
    ;(slider.element as HTMLInputElement).value = '2'
    await slider.trigger('input')
    await flushPromises()
    expect((fetch as unknown as { mock: { calls: unknown[] } }).mock.calls.length)
      .toBe(calls)
  })

  it('开始训练发出去的是屏上那十二个值', async () => {
    // T5：面板与请求不许分家。读的是**请求体**，而且断言「body 里那个数
    // 就是屏上那一格」—— 比断言「body 里是我以为的那个数」硬：
    // 后者在夹具改了之后会跟着一起改，前者不会。
    const bodies: Record<string, unknown>[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url)
      let body: unknown = FEATURES
      if (u.includes('/api/calibration/diagnostics')) {
        const sent = JSON.parse(String(init?.body)) as { params: Record<string, unknown> }
        bodies.push(sent.params)
        // 回声：后端算的就是这一套值，于是这条回包也是**真实形状**
        // （`params_used` 必与请求体一致），`diagForBundle` 那条判据不会误挡。
        body = { ...DIAG, params_used: sent.params }
      } else if (u.includes('/api/calibration')) {
        body = CAL
      }
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }))
    const w = mount(TrainView)
    await flushPromises()

    // 手调一维，再从**屏上**读它现在那一档（读 DOM，不读夹具）。
    // 读的是 `aria-valuetext`：行末尾那个可见的当前值已经删掉了，
    // 这一份就是面板现在对外说的那个值（`ParamPanel.test.ts` 里有专条钉它）。
    const depth = rowOf(w, 'trend.max_depth')
    const guide = depth.find('input[type="range"]')
    ;(guide.element as HTMLInputElement).value = '3'      // 第 4 档 → 6
    await guide.trigger('input')
    const shown = depth.find('input[type="range"]').attributes('aria-valuetext')

    await w.findAll('button').find((b) => b.text() === '开始训练')!.trigger('click')
    await flushPromises()

    expect(bodies.length).toBe(1)
    const expected: Record<string, unknown> = Object.fromEntries(
      [...CAL.panel.trend, ...CAL.panel.idw].map((r) => [r.key, r.current]))
    expected['trend.max_depth'] = 6                       // 上面拖过的那一格
    expect(bodies[0], '发出去的不是那十二个').toEqual(expected)
    expect(Number(shown), '屏上那一格与发出去的那个数对不上').toBe(6)
    expect(bodies[0]['cross_shed']).toBe(true)            // 布尔原样过去，没被字符串化
  })

  it('参数改过之后，屏上那份精度不作数', async () => {
    // T6 / 规格书 §四.3。**这一条与下一条是一对** —— 只写这一条的话，
    // 一个「永远不显示」的实现也能过，而那是这条规则最坏的坏法：
    // 精度静默地再也不出现，还不报错。
    const w = await mountWithDiag()
    // 先证明它本来是在的。用 `:574` 与 `:695` 那两条用例认过的字串，
    // 不另编一个（编出来的那个万一不在屏上，这两条断言就成了摆设）。
    expect(w.text()).toContain('拿背景温度当棚温')
    expect(w.find('.diagnostics-body').text()).toContain(DIAG.accuracy.baseline.mae.toFixed(4))

    const depth = rowOf(w, 'trend.max_depth')
    ;(depth.find('input[type="range"]').element as HTMLInputElement).value = '0'
    await depth.find('input[type="range"]').trigger('input')

    expect(w.text(), '上一套参数的基线还在屏上').not.toContain('拿背景温度当棚温')
    expect(w.find('.diagnostics-body').find('table').exists()).toBe(false)
    // 不能静默：数字一转眼没了，用户得知道它们为什么没了、怎么弄回来。
    expect(w.text()).toContain('参数换过了')
  })

  it('参数没改时，精度照常显示', async () => {
    // 上面那条的反面。两条合起来才钉住「改过才不作数」——
    // 少了这一条，一个把 `diagForBundle` 写成恒返回 null 的实现照样全绿。
    const w = await mountWithDiag()
    expect(w.text()).toContain('拿背景温度当棚温')
    expect(w.text()).not.toContain('参数换过了')
  })

  it('参数优选跑完之后，面板的值被刷成包里的那套', async () => {
    // T8：用户的「优选完的参数自动调整参数值」（规格书 §4.2）。
    // 前端**不加任何新逻辑** —— 它只是「不覆盖从后端取来的值」而已。
    // 骨架照 `:640` 那条「任务跑完之后重取一次标定包」：提交 → 立刻轮询一次 →
    // 推进 1 秒 → 轮询回 `done` → 重取 `/api/calibration`。
    // 这里只是让**第二趟**取回来的 `panel` 与第一趟不同（max_depth 4 → 6）。
    vi.useFakeTimers()
    let polls = 0
    let cals = 0
    const RUN = { id: 'j9', state: 'running', progress: '阶段 2 试验之间',
                  elapsed_s: 3.2, error: null, created_at: '2026-10-07T10:00:00+00:00' }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      let body: unknown = FEATURES
      if (u.includes('/api/calibration/jobs/')) {           // 轮询（带 id）
        polls += 1
        body = polls >= 2 ? { ...RUN, state: 'done', progress: '', elapsed_s: 41.7 } : RUN
      } else if (u.includes('/api/calibration/jobs')) {     // 提交（POST，不带 id）
        body = RUN
      } else if (u.endsWith('/api/calibration')) {
        cals += 1
        // 第二趟 = 包已经写回盘上了：优选把 max_depth 从 4 调到了 6。
        // ⚠️ 只改那一格的 `current`，`raw` 与 `values` 一个都不动 ——
        // 6 本来就在候选 `['3','4','5','6']` 里，这正是后端真优选之后发的形状。
        body = cals === 1 ? CAL : {
          ...CAL,
          panel: {
            ...CAL.panel,
            trend: CAL.panel.trend.map((r) =>
              r.key === 'trend.max_depth' ? { ...r, current: 6 } : r),
          },
        }
      }
      return new Response(JSON.stringify(body), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }))
    const w = mount(TrainView)
    await flushPromises()
    expect(rowOf(w, 'trend.max_depth').find('input[type="range"]')
      .attributes('aria-valuetext'), '第一趟不是包里那套').toBe('4')

    await w.findAll('button').find((b) => b.text() === '参数优选')!.trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    expect(cals, '任务跑完之后没有重取标定包').toBe(2)
    expect(rowOf(w, 'trend.max_depth').find('input[type="range"]')
      .attributes('aria-valuetext'), '重取回来的值没有落到面板上').toBe('6')
    w.unmount()
    vi.useRealTimers()
  })

  it('手改过值之后，B 组那句口径才出现', async () => {
    // T9 / 规格书 §5.1。手动调参是**拿眼睛在屏上搜**：拖滑块时屏上正摆着
    // B 组那几折的 MAE，而那几折的标签写着「B 组，未参与选参」。照着它调，
    // B 组就不再是没被看过的样本了。不藏数（藏不住，他也能拿 A 组的数调），
    // 加一句话。判据用最终定稿的那半句，见 4d。
    const w = await mountWithDiag()
    expect(w.text(), '还没动手就已经在认错了').not.toContain('不是没被看过的样本')

    const depth = rowOf(w, 'trend.max_depth')
    ;(depth.find('input[type="range"]').element as HTMLInputElement).value = '0'
    await depth.find('input[type="range"]').trigger('input')

    expect(w.text(), '改过值了，那句话没上来').toContain('不是没被看过的样本')
    expect(w.text()).toContain('参数优选')          // 下一步给出路
  })
})

describe('保存到模型库', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  /** 「屏上这份包是库里那份」的对照物。 */
  const LIB = { ...CAL, source: 'library' }
  /** 「刚跑完、还没保存」。 */
  const NEW = { ...CAL, source: 'unsaved' }

  /**
   * 一份能走通「保存」这条路的替身。
   *
   * 记下每一次 `METHOD url`，并记下 POST 请求体 —— 「发出去的是不是屏上
   * 那个名字」只能从请求体上读（与上面那条读 `init.body` 同一个手法）。
   *
   * `body` 那一份回调让调用方决定**第几次**取标定包时回什么：保存成功之后
   * 页② 会重取一次，而那一刻后端已经把它置成当前模型了，回来的
   * `source` 该是 `library`。
   */
  function stubSaving(cal: unknown, saveStatus = 201,
                      body: (n: number) => unknown = () => cal) {
    const urls: string[] = []
    const sent: unknown[] = []
    let cals = 0
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url)
      const method = init?.method ?? 'GET'
      urls.push(`${method} ${u}`)
      let out: unknown = FEATURES
      let status = 200
      if (u.includes('/api/models')) {
        if (method === 'POST') {
          sent.push(JSON.parse(String(init?.body)))
          if (saveStatus === 201) {
            out = { id: 1, name: (sent.at(-1) as { name: string }).name }
          } else {
            out = { detail: '手上没有刚跑完的模型。' }
            status = saveStatus
          }
        }
      } else if (u.endsWith('/api/calibration')) {
        cals += 1
        out = body(cals)
      }
      return new Response(JSON.stringify(out), {
        status, headers: { 'Content-Type': 'application/json' } })
    }))
    return { urls, sent, cals: () => cals }
  }

  it('刚跑完还没保存时，读数那块挂的是「未入库」', async () => {
    // ⚠️ 这一条是整行的**全部理由**：刚跑完那一份与库里那份在屏上长得
    // 一模一样时，用户没法判断「我这一块数到底留下来了没有」。
    stubSaving(NEW)
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.record-description .prov').text()).toBe('未入库')
    expect(w.text()).toContain(MODELS.saveTitle)
  })

  it('库里那份的时候图章还是「包」，而且没有保存那一行', async () => {
    // 上面那条的反面。少了它，一个把 `provKind` 恒写成 'unsaved' 的实现
    // 照样全绿 —— 而它会让每一份**已经存好**的模型都在喊「未入库」。
    stubSaving(LIB)
    const w = mount(TrainView)
    await flushPromises()
    expect(w.find('.record-description .prov').text()).toBe('包')
    expect(w.text()).not.toContain(MODELS.saveTitle)
  })

  it('名字是空的时保存按钮按不动', async () => {
    stubSaving(NEW)
    const w = mount(TrainView)
    await flushPromises()
    const btn = w.findAll('button').find((b) => b.text() === MODELS.saveTitle)!
    await w.get('input[name="model-name"]').setValue('   ')
    expect(btn.attributes('disabled'), '名字全是空白时按钮还能点').toBeDefined()
    await w.get('input[name="model-name"]').setValue('棚里那套')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('保存成功之后图章翻成「包」，那一行也收了', async () => {
    const s = stubSaving(NEW, 201, (n) => (n === 1 ? NEW : LIB))
    const w = mount(TrainView)
    await flushPromises()
    expect(w.text()).toContain('未入库')

    await w.get('input[name="model-name"]').setValue('棚里那套')
    await w.findAll('button').find((b) => b.text() === MODELS.saveTitle)!
      .trigger('click')
    await flushPromises()

    // 发出去的就是屏上那个名字
    expect(s.sent.at(-1)).toEqual({ name: '棚里那套' })
    // **重取了一次** —— 不重取的话 `source` 还停在载荷里那个 'unsaved' 上，
    // 图章不翻、那一行不消失，用户会以为没保存成功，再点一次吃 409。
    expect(s.cals(), '保存之后没有重取标定包').toBe(2)
    expect(w.find('.record-description .prov').text()).toBe('包')
    expect(w.text()).not.toContain(MODELS.saveTitle)
  })

  it('保存失败时把后端那句话印出来，不吞掉', async () => {
    // 409：手上没有刚跑完的那一份（另一个标签页先存了、或后端重启过）。
    stubSaving(NEW, 409)
    const w = mount(TrainView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === MODELS.saveTitle)!
      .trigger('click')
    await flushPromises()
    expect(w.text()).toContain('手上没有刚跑完的模型。')
    // 失败之后那一行还在，用户能看着那句话去处理 —— 不许悄悄收掉
    expect(w.text()).toContain(MODELS.saveTitle)
  })

  it('保存那几秒里按钮说的是「正在固化成品」，并写明要十几秒', async () => {
    // ⚠️ 固化 = 把拟合好的趋势存下来，所以保存这一路要**现训一遍**（十几秒）。
    //    只写「保存中」，用户只会以为这台机器卡了 —— 这一条钉的就是那句解释。
    let release!: () => void
    const gate = new Promise<void>((r) => { release = r })
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      const u = String(url)
      if (u.includes('/api/models') && (init?.method ?? 'GET') === 'POST') {
        await gate                                  // 卡在保存上，看那几秒的屏
        return new Response(JSON.stringify({ id: 1, name: '棚里那套' }),
          { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      const out = u.endsWith('/api/calibration') ? NEW : FEATURES
      return new Response(JSON.stringify(out),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    const w = mount(TrainView)
    await flushPromises()
    await w.get('input[name="model-name"]').setValue('棚里那套')
    await w.findAll('button').find((b) => b.text() === MODELS.saveTitle)!
      .trigger('click')
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text() === MODELS.fixating),
      '忙的时候按钮该说「正在固化成品」').toBeTruthy()
    // ⚠️ **判的是按钮，不是整页的 `text()`**：那一行的 `<label for="model-name">`
    //    **永远**印着 `MODELS.saveTitle`（它跟着输入框走，不是动作的一部分），
    //    拿整页判就成了「这一条永远红」。要钉的是「忙的那几秒里**没有一个按钮**
    //    还说保存」。
    expect(w.findAll('button').some((b) => b.text() === MODELS.saveTitle),
      '忙的时候按钮不该还说「保存到模型库」').toBe(false)
    expect(w.text()).toContain(MODELS.fixatingWhy)

    release()
    await flushPromises()
    expect(w.text()).not.toContain(MODELS.fixating)
  })
})
