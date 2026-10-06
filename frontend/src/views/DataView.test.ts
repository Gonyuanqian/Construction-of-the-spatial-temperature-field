import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import DataView from './DataView.vue'
import { useDataset } from '../composables/useDataset'

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
  root.style.setProperty('--layer-top', '#C44E52')
  root.style.setProperty('--layer-mid', '#4C72B0')
  root.style.setProperty('--layer-low', '#55A868')
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
  // 测点编号单独一格，与 `positions`（几何）分开。
  point_codes: { 'x0.15_z0.4': 'B1' },
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
    // 数据集单例是模块级的：页① 现在会读它的 `lastImport`，不清就等于让
    // 结果取决于文件里谁先跑。
    useDataset().reset()
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

  it('页尾那段「还没有入口」的话已经删掉 —— 现在入口就在页顶', async () => {
    // 这条**取代**了原来那条「页① 说清了『换数据集』这块还没有入口」。
    // 那条钉的是「名字许诺了、界面上没有、还不说」；现在界面上有了
    // （页顶的导入块），那句话就成了一句**当着入口说没有入口**的话 ——
    // 比不说更坏。所以改钉它的反面：旧话不许残留。
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH,
           '/api/dataset/timeseries': TS, '/api/dataset/layer-timeheight': TH })
    const w = mountView()
    await flushPromises()
    expect(w.text()).not.toContain('还没有入口')
    expect(w.find('input[type="file"]').exists(), '页顶没有导入块').toBe(true)
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

describe('页① 第一块：数据导入', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
    // 单例是模块级的，会跨用例留下上一次的版本号 —— 不清就等于让用例的
    // 结果取决于文件里谁先跑。
    useDataset().reset()
  })

  /** 一次「选中文件」：把一个 File 塞进 input，再触发 change。 */
  async function pickFile(w: ReturnType<typeof mountView>, name = '人参棚 副本.xlsx') {
    const input = w.find('input[type="file"]')
    const file = new File([new Uint8Array([1, 2, 3])], name)
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    return file
  }

  it('没选文件时按钮是禁用的 —— 不是一个点了没反应的按钮', async () => {
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH })
    const w = mountView()
    await flushPromises()
    const btn = w.find('button.import')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('导入成功后写一行身份，并让外壳重挂载', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (String(url).includes('/api/dataset/upload')) {
        expect(init?.method).toBe('POST')
        return new Response(JSON.stringify({
          signature: '新', file: '人参棚 副本.xlsx', n_times: 1308, n_columns: 52,
          time_start: '2026-07-23T11:00:00', time_end: '2026-07-27T23:55:00',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify(
        String(url).includes('/api/field/arch') ? ARCH : DATASET), {
        status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const before = useDataset().version.value
    const w = mountView()
    await flushPromises()
    await pickFile(w)
    await w.find('button.import').trigger('click')
    await flushPromises()

    expect(w.text()).toContain('人参棚 副本.xlsx')
    // 四个数全部来自上传响应，前端一处加法都没有。
    expect(w.text()).toContain('1308')
    expect(w.text()).toContain('2026-07-23 11:00 至 2026-07-27 23:55')
    // 外壳的版本号前进了 —— 当前挂着的那一页（就是这一页）随组件一起
    // 被丢掉再挂一次，页面上任何一处旧 datum 都不可能留在原处。
    expect(useDataset().version.value).toBe(before + 1)
  })

  it('导入中按钮禁用并写「正在导入…」，不做假进度条', async () => {
    let release: (() => void) | null = null
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).includes('/api/dataset/upload')) {
        await new Promise<void>((res) => { release = res })
        return new Response(JSON.stringify({
          signature: '新', file: 'a.xlsx', n_times: 1, n_columns: 2,
          time_start: '2026-07-23T11:00:00', time_end: '2026-07-23T11:00:00',
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify(
        String(url).includes('/api/field/arch') ? ARCH : DATASET), {
        status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const w = mountView()
    await flushPromises()
    await pickFile(w)
    await w.find('button.import').trigger('click')
    await flushPromises()

    const btn = w.find('button.import')
    expect(btn.text()).toContain('正在导入')
    expect(btn.attributes('disabled')).toBeDefined()
    // 这一句是**文字**，不是进度条：假进度条只会撒谎。
    expect(w.find('progress').exists()).toBe(false)
    expect(w.find('[role="progressbar"]').exists()).toBe(false)

    release!()
    await flushPromises()
    expect(w.find('button.import').text()).toContain('导入')
  })

  it('失败时把后端那句话原样摆出来，并且不动版本号', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).includes('/api/dataset/upload')) {
        return new Response('{"detail":"这份文件读不成数据集：KeyError: 宽表"}', {
          status: 400, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify(
        String(url).includes('/api/field/arch') ? ARCH : DATASET), {
        status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const before = useDataset().version.value
    const w = mountView()
    await flushPromises()
    await pickFile(w)
    await w.find('button.import').trigger('click')
    await flushPromises()

    const alert = w.find('[role="alert"]')
    expect(alert.exists(), '导入失败没有 role="alert"').toBe(true)
    expect(alert.text()).toContain('KeyError: 宽表')
    // 失败不算导入成功 —— 版本号不动，界面不许重挂载（否则用户会以为成了）
    expect(useDataset().version.value).toBe(before)
  })

  it('导入块在页① 的最上面 —— 这是系统的起点', async () => {
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH })
    const w = mountView()
    await flushPromises()
    const h3s = w.findAll('h3').map((h) => h.text())
    expect(h3s[0]).toContain('导入')
  })

  it('这一块的文案没有禁用字形', async () => {
    stub({ '/api/dataset': DATASET, '/api/field/arch': ARCH })
    const w = mountView()
    await flushPromises()
    for (const bad of ['——', '**', '`', ' · ', '→', '↳']) {
      expect(w.text(), `出现了被禁的 ${JSON.stringify(bad)}`).not.toContain(bad)
    }
  })
})

describe('页① 的空态：只有导入块，没有一句告警', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
    useDataset().reset()
  })

  /** 后端在没导入数据集时的原话（`api/errors.py` 的 `NO_DATASET_DETAIL`）。 */
  const NO_DATASET = '还没有导入数据集。到「数据导入与检查」那一页导入一份 xlsx。'

  function stubEmpty() {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).includes('/api/field/arch')) {
        return new Response(JSON.stringify(ARCH), {
          status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      // `/api/field/arch` 是纯常量，空态下**照常 200**。所以这一页的
      // 空态不是「全挂」，而是「数据集那一路 409、几何那一路好好的」。
      return new Response(JSON.stringify({ detail: NO_DATASET }), {
        status: 409, headers: { 'Content-Type': 'application/json' } })
    }))
  }

  it('没有 role="alert" —— 空态是起点，不是故障', async () => {
    // 这是**验收的人第一次打开系统**看到的画面。把 409 原样摆成一条告警，
    // 他会以为哪里坏了（规格书 §二.1：空态是系统的起点）。
    stubEmpty()
    const w = mountView()
    await flushPromises()
    expect(w.findAll('[role="alert"]').length, '空态下出现了告警').toBe(0)
    expect(w.text()).not.toContain('还没有导入数据集')
  })

  it('导入块在，其余三块都不在 —— 空态下它是唯一可用的一块', async () => {
    stubEmpty()
    const w = mountView()
    await flushPromises()
    expect(w.find('input[type="file"]').exists()).toBe(true)
    expect(w.find('button.import').exists()).toBe(true)
    // 指标卡（没数据可报）、主图（没几何可画）、口径与出处（里面那句
    // 「数据集：」会印成一个空值）—— 三块在空态下都没有可说的东西。
    expect(w.findAll('.stat').length).toBe(0)
    expect(w.findAllComponents({ name: 'EChart' }).length).toBe(0)
    expect(w.findAll('details').length).toBe(0)
    // 那句「测点或几何没取到」是在指一条并不存在的上方提示。
    expect(w.text()).not.toContain('没取到')
  })

  it('500 照旧报出来 —— 只有 409 才是空态', async () => {
    // 把 500 也吞成空态，就等于让用户去导一份数据集来解决一个后端没起来的
    // 问题 —— 这正是规格书 §二.1 点名要分开的两种错。
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      '{"detail":"Internal Server Error"}',
      { status: 500, headers: { 'Content-Type': 'application/json' } })))
    const w = mountView()
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(true)
    expect(w.text()).toContain('Internal Server Error')
    expect(w.findAll('details').length, '500 不该被当成空态').toBe(1)
  })
})
