import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import DataView from './DataView.vue'

/**
 * 两件测试环境的事，都在这里备好（Ruling P5）：
 *
 * 1. `readPalette()` 从 computed style 读令牌，而 jsdom 不加载 tokens.css，
 *    读不到就**抛错**（这是故意的：它宁可不画，也不肯用个错的灰）。所以凡
 *    挂载用到调色板的组件，测试必须先把这个夹具装好。
 * 2. jsdom 里没有 `ResizeObserver`。`EChart.vue` 在 onMounted 里 new 一个，
 *    没有就 ReferenceError。这里补上。本测试把 EChart 换成了占位（见
 *    mountView），占位不会去 new，但夹具留着：它是这一层测试环境的义务，
 *    不该等哪天有人去掉 stub 才想起来。
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
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
}

const DATASET = {
  signature: '6145fa9261e89f1b',
  file: '人参棚_多棚温湿度_气象时间对齐数据集.xlsx',
  n_times: 1308, n_columns: 52,
  n_missing: 0, n_dup_times: 4,
  time_start: '2026-07-23T11:00:00', time_end: '2026-07-27T23:55:00',
  sheds: { p1: 3, p2: 9, p3: 15 },
  positions: [{ id: 'x0.15_z0.4', x: 0.15, z: 0.4, layer: 'z0.4' }],
  temperature: [{ shed: 'p1', position: 'x0.15_z0.4', mean: 38.4, min: 24.1, max: 45.0 }],
  fix: {
    n_rows: 1308, fixed_indices: [60, 348, 636, 924, 1212],
    monotonic_before: false, monotonic_after: true,
    spacing_seconds: 300, n_gaps: 0,
  },
  checks: [
    { no: 1, name: '结构完整性', what: '必需 sheet 与列是否齐', status: 'ok', evidence: '宽表 1308 × 52' },
    { no: 2, name: '时间轴', what: '单调、无重复', status: 'ok', evidence: '等间隔 300 s' },
    { no: 3, name: '缺失', what: '逐列缺失计数', status: 'ok', evidence: '缺失 0' },
  ],
  checks_note: '其余 5 项（值域、卡死、跨棚离群、质量标记、对齐）后端照算，只是没有铺在页面上。',
}

const ARCH = {
  x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 1.1,
  arch: [[0, 0.4535], [2.1, 0.4535]],
  sheds: [{ id: 'p1', y: 3 }, { id: 'p2', y: 9 }, { id: 'p3', y: 15 }],
}

const TS = {
  n_times: 2, time: ['2026-07-23T11:00:00', '2026-07-23T11:05:00'],
  bg_temp: [30, 31], sensors: { 'p1|x0.15_z0.4': [40, 41] },
  shed_mean: { p1: [39, 40] },
  detrended: { 'p1|x0.15_z0.4': [10, 10] }, detrended_mean: { p1: [9, 9] },
  detrended_domain: [-3, 3], note: '减法在后端做',
}

const TH = {
  step: 4, n_times: 1308, n_columns: 2,
  time: TS.time, x_label: '时刻', source: '实测棚温',
  sheds: { p1: { labels: ['z0.4'], z: [0.4], values: [[40, 41]] } },
}

function stub(routes: Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    // ⚠️ 取**最长**的匹配前缀，不是第一个命中。路由里 '/api/dataset' 是
    // '/api/dataset/timeseries' 的前缀；用 find 的话，对象字面量里先写
    // 短的那条，长接口就会被它吃掉，ts 拿到的是数据集载荷 —— 报错发生在
    // 图表构造器里，离现场很远。按最长匹配，写不写先后都对。
    const hit = Object.keys(routes)
      .filter((k) => String(url).includes(k))
      .sort((a, b) => b.length - a.length)[0]
    if (!hit) return new Response('{"detail":"没有这个接口"}', { status: 404 })
    return new Response(JSON.stringify(routes[hit]), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
}

function mountView() {
  // EChart 是 DOM 管道（jsdom 里没有 canvas），这里换成占位，
  // 断言落在它收到的 option 上 —— option 才是这个页面真正产出的东西。
  return mount(DataView, {
    global: {
      stubs: {
        EChart: {
          // 占位必须自称 EChart：findAllComponents({ name }) 按名字找，
          // 对象形式的 stub 不会被 VTU 自动命名。
          name: 'EChart',
          props: ['option'],
          template: '<div class="chart-stub" :data-series="option.series.length" />',
        },
      },
    },
  })
}

describe('页① 数据导入与检查', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
  })

  it('一排四张卡：样本数 / 样本时间范围 / 缺失样本量 / 重复样本量', async () => {
    stub({ '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH,
           '/api/field/arch': ARCH, '/api/dataset': DATASET })
    const w = mountView()
    await flushPromises()
    const cards = w.findAll('.stat')
    expect(cards.map((c) => c.find('.label').text()))
      .toEqual(['样本数', '样本时间范围', '缺失样本量', '重复样本量'])
    const value = (label: string) =>
      cards.find((c) => c.find('.label').text() === label)!.find('.value').text()
    expect(value('样本数')).toBe('1308')
    // 时刻走 `fmtTime`（不带 T、不带秒），两端用「至」接 —— §8.5 禁的是
    // 破折号与中点那类装饰连接符，「至」不在禁列。
    expect(value('样本时间范围')).toBe('2026-07-23 11:00 至 2026-07-27 23:55')
    expect(value('缺失样本量')).toBe('0')
    expect(value('重复样本量')).toBe('4')
  })

  it('这一排卡铺浅叶色底，与页上别处的白卡分得开', async () => {
    stub({ '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH,
           '/api/field/arch': ARCH, '/api/dataset': DATASET })
    const w = mountView()
    await flushPromises()
    expect(w.find('.stats').classes(), '这一排卡没有铺浅叶底').toContain('tinted')
  })

  it('「数据检查」那张表整块撤下 —— 四个数已经在上面的卡片里', async () => {
    // 用户 2026-10-06 裁定：表去掉，内容换成页顶那排卡。接口照旧返回
    // `checks`/`checks_note`（夹具里还在），前端不再渲染它们 ——
    // 所以这条同时钉住了「后端那份数据不能漏到屏上」。
    stub({ '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH,
           '/api/field/arch': ARCH, '/api/dataset': DATASET })
    const w = mountView()
    await flushPromises()
    expect(w.findAll('table').length, '页① 还有一张表').toBe(0)
    expect(w.text()).not.toContain('在查什么')
    expect(w.text()).not.toContain('结构完整性')
    expect(w.text()).not.toContain('跨棚离群')
  })

  it('指纹与列数不再出现在页面上', async () => {
    // 五张卡换四张，指纹与列数都没了新位置。指纹撤下之后，页尾那两句
    // 讲「指纹是数据集身份」的话也一并删了 —— 留着就是讲一个屏上没有的东西。
    stub({ '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH,
           '/api/field/arch': ARCH, '/api/dataset': DATASET })
    const w = mountView()
    await flushPromises()
    expect(w.text()).not.toContain('6145fa9261e89f1b')
    expect(w.text()).not.toContain('指纹')
  })

  it('后端挂了就说清是哪个接口挂了，不是一片空白', async () => {
    stub({ '/api/dataset': { detail: '数据集不存在：C:/x.xlsx' } })
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('{"detail":"数据集不存在：C:/x.xlsx"}', {
        status: 404, headers: { 'Content-Type': 'application/json' } })))
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('数据集不存在')
  })

  it('页① 说清了「换数据集」这块还没有入口', async () => {
    // 页名与导航标签是「数据导入与检查」，spec §2.1 的第 1 块也确实是
    // 「数据集导入 —— 换数据集」。但本轮只交付了**只读的**身份卡，没有换数据集的
    // 入口（那要新接口、缓存失效、以及指纹一变 ②③④ 全锁的一整套，不在本轮）。
    // 名字许诺了、界面上没有、还不说 —— 这正是「被砍掉的五项检查」那条
    // Review Focus 的同一形态，所以按同样的办法钉住：**自己说出来**。
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH,
           '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH })
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('换数据集')
  })

  it('四张卡各自带出处图章（屏上一个字，整句在 title 上）', async () => {
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH,
           '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH })
    const w = mountView()
    await flushPromises()
    const stamps = w.findAll('.stat .prov')
    expect(stamps.length, '四张卡的图章不齐').toBe(4)
    for (const s of stamps) {
      expect(s.text()).toBe('算')
      expect(s.attributes('title')).toContain('现场重算')
    }
  })

  it('首屏是一排指标卡，主图在它们下面（spec §6.2）', async () => {
    stub({ '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH,
           '/api/field/arch': ARCH, '/api/dataset': DATASET })
    const w = mountView()
    await flushPromises()
    const cards = w.findAll('.stat')
    expect(cards.length, '页① 的指标卡不是四张').toBe(4)
    // 长值那一格收一档字号，卡片高度不变（`compact`）；四格等宽由 StatRow 管。
    const span = cards.find((c) => c.find('.label').text() === '样本时间范围')!
    expect(span.find('.value').classes()).toContain('compact')
    expect(w.findAllComponents({ name: 'EChart' }).length, '主图不见了').toBe(1)
  })

  it('散文折进「口径与出处」，正文里不再有裸的说明段（spec §八）', async () => {
    stub({ '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH,
           '/api/field/arch': ARCH, '/api/dataset': DATASET })
    const w = mountView()
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why.length, '「口径与出处」不是恰好一处').toBe(1)
    expect(why[0].find('summary').text()).toContain('口径与出处')
    // 收起来的 `<details>` 内容仍在 DOM 里 —— 这正是选它而不是弹层的首要理由
    expect(why[0].text()).toContain('只读')
  })

  it('页① 只剩一张主图 —— 「昼夜与残差」整块撤下（spec §6.2 页① 修订）', async () => {
    // 用户 2026-10-06 裁定：两条折线与时间×高度热图共用一份图表配置，整块删。
    // 这条测试**取代**了原来那条「两张图都挂上了」。
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH })
    const w = mountView()
    await flushPromises()
    expect(w.findAllComponents({ name: 'EChart' }).length).toBe(1)
    expect(w.text()).not.toContain('昼夜与残差')
  })

  it('撤下之后，只为那一块存在的请求不再发（spec §6.2 页① 修订）', async () => {
    // 死代码要连根拔：图删了而 `ts` / `th` 还在，就是每开一次页① 白发两条请求。
    const asked: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      asked.push(String(input))
      // 只把 `/api/dataset` 回成数据集，其余一律 404。
      // **不能全回 DATASET**：那样 `arch` 会拿到一个数据集形状的载荷，
      // 而 `buildSensorLayoutOption` 会去 `arch.sheds.map(...)` —— sheds 在
      // 数据集里是个对象，于是抛一个 unhandled rejection。断言照样过，
      // 但测试输出不再干净：一条测试留下一个没人处理的错误，比它变红更坏。
      if (String(input).endsWith('/api/dataset')) {
        return new Response(JSON.stringify(DATASET), {
          status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response('{"detail":"这条测试不关心这个接口"}', { status: 404 })
    }))
    mountView()
    await flushPromises()
    expect(asked.some((u) => u.includes('/api/dataset/timeseries'))).toBe(false)
    expect(asked.some((u) => u.includes('/api/dataset/layer-timeheight'))).toBe(false)
  })
})
