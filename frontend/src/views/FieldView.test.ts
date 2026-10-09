import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import FieldView from './FieldView.vue'
import { createAppRouter } from '../router'
import { FIELD_MODEL } from '../design/copy'
import { makeModelsPayload } from '../test/fixtures'

/**
 * 与页① 同款的两个环境夹具（Ruling P5）：tokens 读不到就抛错的调色板，
 * 以及 jsdom 里没有的 ResizeObserver。
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

/** 4×4 的小场，四种格子各占一角（与 pick / sectionField 的测试同一套）。 */
function makeShed(shed: string, y: number) {
  return {
    shed, y,
    values: [[1, 2, 3, 4], [1, 43.216137, 3, 4], [null, 2, 3, 4], [null, null, 3, 4]],
    stripes: [[2, 0], [2, 1], [2, 2], [2, 3], [3, 2], [3, 3]],
  }
}

const SECTIONS = {
  t_index: 12, time: '2026-07-23T12:00:00', n_times: 1308,
  preset: 'standard', monotonic: true, calibrated: true,
  vmin: 0.9, vmax: 5.1, max_measured_z: 2,
  x_min: 0, x_max: 2.1, z_max: 1.3017,
  x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
  arch: [[0, 0], [2.1, 0]],
  sensors: [{ id: 'x0.7_z0.7', x: 0.7, z: 0.7, layer: 'z0.7' }],
  sheds: [makeShed('p1', 3), makeShed('p2', 9), makeShed('p3', 15)],
  note: '三格共享同一个色标范围。拱外不画。',
}

const COMPARE = {
  shed: 'p1', y: 3, t_index: 12, time: '2026-07-23T12:00:00', n_times: 1308,
  preset: 'standard',
  x: [0, 0.7, 1.4, 2.1], z: [0, 0.7, 1.4, 2.1],
  arch: [[0, 0], [2.1, 0]],
  sensors: [{ id: 'x0.7_z0.7', x: 0.7, z: 0.7, layer: 'z0.7' }],
  max_measured_z: 2,
  before: [[1, 2, 3, 4], [1, 4, 3, 4], [null, 2, 3, 4], [null, null, 3, 4]],
  after: [[1, 2, 3, 4], [1, 4.2, 3, 4], [null, 2, 3, 4], [null, null, 3, 4]],
  delta: [[0, 0, 0, 0], [0, -0.2, 0, 0], [null, 0, 0, 0], [null, null, 0, 0]],
  stripes: [[2, 0], [2, 1], [2, 2], [2, 3], [3, 2], [3, 3]],
  vmin: 1, vmax: 5, delta_vmax: 0.2,
  light: 812, gate_open: true, gate_label: '开（有光照）', identical: false,
  note: '',
}

const CURVE = {
  shed: 'p1', x: 0.7, y: 3, z: 0.7, label: 'p1  x 0.70  z 0.70',
  n_times: 4, time: ['t0', 't1', 't2', 't3'],
  values: [40.1, 43.2, 39.8, 38.5], defined: true,
  note: '这条曲线没有施加竖直软单调投影：单点没有邻点可投影。',
}

/** 记下每一次请求的 URL，用来断言"换时刻真的换了一次请求"。 */
const urls: string[] = []

function stub(routes: Record<string, unknown>) {
  urls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    urls.push(String(url))
    const hit = Object.keys(routes)
      .filter((k) => String(url).includes(k))
      .sort((a, b) => b.length - a.length)[0]
    if (!hit) return new Response('{"detail":"没有这个接口"}', { status: 404 })
    return new Response(JSON.stringify(routes[hit]), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
}

/**
 * 三个 field 接口那一份。
 *
 * ⚠️ **`/api/models` 必须在这里**（从 Task 10 起）：这一页现在先问库里有
 * 没有能用的模型，没有就一个场都不画、三个 field 接口一个都不打。
 * 缺了它，`stub()` 会把 `/api/models` 判成 404，下面那十几条既有用例
 * 全都掉进空态 —— 而它们一条都没改过，红的理由离「少了一个键」很远。
 */
const OK = { '/api/field/curve': CURVE, '/api/field/compare': COMPARE,
             '/api/field/sections': SECTIONS, '/api/models': makeModelsPayload() }

function mountView() {
  return mount(FieldView, {
    global: {
      // 空态那一支挂着 `<RouterLink>`（「去模型库挑一个」／「去模型训练训一个」）。
      // 不给路由的话 Vue 解析不出 `RouterLink`，按未知标签渲染并**打警告** ——
      // 断言照样绿，但每次跑测试都刷一遍警告。
      plugins: [createAppRouter(createMemoryHistory())],
      stubs: {
        // 占位必须自称 EChart：findAllComponents({name}) 按名字找。
        EChart: { name: 'EChart', props: ['option'], emits: ['pick'],
                  template: '<div class="chart-stub" />' },
        // Teleport 在测试里就地渲染，这样断言能落在控件上。
        Teleport: true,
      },
    },
  })
}

const charts = (w: ReturnType<typeof mountView>) => w.findAllComponents({ name: 'EChart' })

/**
 * 等一个条件成立。
 *
 * 懒加载那一块要**真去解析一个模块**：`import()` 在 vitest 里走的是 vite-node
 * 的转换请求，不是一个微任务能等到的，`flushPromises()` 等不来。有上限，
 * 不是死等 —— 真的没上来就返回 false，让断言红在那里。
 */
async function until(ok: () => boolean, ms = 3000): Promise<boolean> {
  const end = Date.now() + ms
  while (!ok() && Date.now() < end) await new Promise((r) => setTimeout(r, 10))
  return ok()
}

describe('页③ 空间温度场的构建', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
  })

  it('切面场与 ΔT 一开始就挂上；曲线要等点选之后才出现', async () => {
    // **初始是 2 个，不是 3 个。** 曲线画的是「你点中的那一格」——没点过就不知道
    // 画哪一个点。Task 11 也定过「全 null 时页面负责不画它」。所以曲线是点选的
    // 结果，不是一进页面就有的东西。断言 3 会永远红。
    stub(OK)
    const w = mountView()
    await flushPromises()
    expect(charts(w).length).toBe(2)          // 切面场、ΔT
    expect(w.text()).toContain('空间温度场的构建')

    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    expect(charts(w).length).toBe(3)          // 点中之后才多出曲线
  })

  it('切面图画的是后端送来的那三格', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    const o = charts(w)[0].props('option') as any
    expect(o.series).toHaveLength(15)
    expect(o.visualMap.min).toBe(SECTIONS.vmin)
    expect(o.visualMap.max).toBe(SECTIONS.vmax)
  })

  it('没点任何格子时：只说怎么点，不提前谈曲线口径', async () => {
    // 断言的是**那句完整文案**，不是光一个「点」字 —— 页面上常驻的
    // 「点一个格子看它的读数与 5 天曲线」里也有「点」，只查一个字会恒绿。
    stub(OK)
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('还没点任何格子')
    // 曲线口径是**那条曲线**的口径。线还没画出来就先说它，
    // 读者会去找一条不存在的线。
    expect(w.text()).not.toContain('没有施加竖直软单调投影')
  })

  it('点在实测格上：报的是格子里那个数，且标明是现场重算', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    // 落在读数表上：整页文本里那句「现场重算」是**图章的 title**，不进 `text()`；
    // 而表里这个「现场重算」来自 `charts/pick.ts` 给实测格的分级文案，
    // 与 `Provenance` 无关 —— 查整页只会白送。
    const t = w.find('table')
    expect(t.exists(), '点选之后读数表没出现').toBe(true)
    expect(t.text()).toContain('43.22')
    expect(t.text()).toContain('现场重算')
  })

  it('点在无测量带上：不报数', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [2, 0] })
    await flushPromises()
    // **断言必须落在读数表上，不能查整页文本。** 页面上常驻的那句提示语里本来
    // 就写着「拱外无定义 / 无测量带不报数」—— 查 `w.text()` 会恒绿：点选整个坏掉、
    // 一个字都不报，它也照过。表只在**点中之后**才存在，所以这一查同时钉住了
    // 「点选确实产生了读数」。
    const t = w.find('table')
    expect(t.exists(), '点选之后读数表没出现').toBe(true)
    expect(t.text()).toContain('不报数')
    // 这一格**存着牌面值 3**（见夹具），但它在无测量带里 —— 一个字也不许报。
    // 写成 `not.toContain('现场重算：3.00')` 会随格式变化悄悄失效（改成「3.0」
    // 就恒真），所以直接查「现场重算」这四个字在不在。
    // **必须在读数表上查，不能查整页**：页面标题那一行挂着
    // `<Provenance kind="live" />`，只要载荷到了它就恒在 —— 查整页这条就永远红，
    // 与上面那两条"永远绿"同源。而表里这四个字来自 `charts/pick.ts`：
    // 不报数的那一格根本不产出它。
    expect(t.text()).not.toContain('现场重算')
  })

  it('点在拱外：无定义', async () => {
    // 拱外那批格子走的是遮罩系列（下标 0），不是热力场。
    stub(OK)
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 0, value: [0, 2] })
    await flushPromises()
    // 同上：常驻提示语里就带着「拱外无定义」四个字，只查整页文本等于什么都没断言。
    const t = w.find('table')
    expect(t.exists(), '点选之后读数表没出现').toBe(true)
    expect(t.text()).toContain('无定义')
  })

  it('点选只从已有载荷里读，**不**再打一次接口', async () => {
    // spec §七 V5：「点选是拾取，不是重跑」。这样屏幕上的数必然等于图上的格子，
    // 而且点一下是秒回的。
    stub(OK)
    const w = mountView()
    await flushPromises()
    const before = urls.filter((u) => u.includes('/api/field/sections')).length
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    expect(urls.filter((u) => u.includes('/api/field/sections')).length).toBe(before)
  })

  it('点中之后才去取那一格的曲线', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    expect(urls.some((u) => u.includes('/api/field/curve'))).toBe(false)
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    const req = urls.find((u) => u.includes('/api/field/curve'))!
    expect(req).toContain('shed=p1')
    expect(req).toContain('x=0.7')     // 载荷里 x[1] = 0.7
    expect(req).toContain('z=0.7')
  })

  it('曲线旁边写着它没有竖直软单调投影', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    expect(w.text()).toContain('没有施加竖直软单调投影')
  })

  it('载荷没带口径时，兜底文案顶上', async () => {
    // Task 11 专门造了 `CURVE_NO_MONOTONIC_NOTE`，为的就是这一刻：载荷的
    // `note` 一缺，曲线上「没有施加竖直软单调投影」会**无声消失**，看图的人
    // 于是以为它经过了投影。兜底不是装饰品 —— 页面必须真的接住它。
    stub({ ...OK, '/api/field/curve': { ...CURVE, note: '' } })
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    expect(w.text()).toContain('没有施加竖直软单调投影')
  })

  it('该点无定义时不画曲线，也不谈曲线口径', async () => {
    // `vCurve` 上的 `c.defined` 与 `curveNote` 上的同一个判断，都在**没有任何测试**
    // 的情况下活着（评审者的破坏性探针：把 `c.defined` 去掉，15 条全绿）。
    // 真断了会是这样：后端明说这一点无定义，页面上却照画一条线，而那句
    // 「该点无定义…不画曲线」**无声消失** —— 看图的人于是以为那条线是真的。
    // 这与 Review Focus 第 3 条（曲线被说成施加了投影）是同一类撒谎。
    stub({ ...OK, '/api/field/curve': { ...CURVE, defined: false } })
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    expect(charts(w).length).toBe(2)                    // 第三条（曲线）不该出现
    expect(w.text()).toContain('该点无定义（拱外或在无测量带里），不画曲线。')
    expect(w.text()).not.toContain('没有施加竖直软单调投影')   // 别去谈一条不存在的线
  })

  it('点中别棚的格子，ΔT 面板跟着换棚', async () => {
    // `activeShed` 的注释写着「点中别棚的格子就跟着走」—— 没有这条测试，它就只是
    // 一句注释。真断了会是这样：读数报的是 p2，ΔT 面板画的还是 p1，两块面板
    // 各说各的，谁都不报错。与 Review Focus 第 1 条「两条路径漂了不报错」同源。
    // 下标 6 是 p2 的热力场：每棚占连续 5 个系列（`SERIES_PER_SHED`），
    // 块内偏移 1 才是热力场（偏移 0 是拱外遮罩），所以 p2 是 1*5+1。
    // 发 5 也能走到 p2 —— `shedOfSeries` 只看块号 —— 但那模拟的是「点拱外遮罩」，
    // 不是点热力场上的格子；这里要的是后者。
    stub(OK)
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 6, value: [1, 1] })
    await flushPromises()
    expect(w.text()).toContain('p2')                    // 读数认的是 p2
    expect(
      urls.some((u) => u.includes('/api/field/compare') && u.includes('shed=p2')),
    ).toBe(true)                                        // ΔT 也真的按 p2 重取了
  })

  it('换时刻会重新取场', async () => {
    // 名字只说这条测试真做的事：夹具对任何 t_index 都回同一个 time，
    // 「显示的时刻跟着变」在这里断言不了 —— 写进名字就是一句空话。
    stub(OK)
    const w = mountView()
    await flushPromises()
    const slider = w.find('input[type="range"]')
    expect(slider.exists(), '时刻游标不在').toBe(true)
    await slider.setValue('13')
    await flushPromises()
    // 必须**指名** sections：compare 的请求也带 t_index=13，
    // 只查 `includes('t_index=13')` 会被它喂绿 —— 场其实没重取也照过。
    expect(
      urls.some((u) => u.includes('/api/field/sections') && u.includes('t_index=13')),
    ).toBe(true)
  })

  it('三维可用了，而且不再挂那句未开放的理由', async () => {
    // 已开放 / 未开放这两态各有一条测试钉着（`guards.test.ts` 管「未开放的必须
    // 带理由」，这条管「开放了就别再挂理由」）。少了这一条，删掉 `why` 却忘了
    // 改 `enabled` 的话，界面上会同时出现一个能点的按钮和一句「排在下一份计划」。
    stub(OK)
    const w = mountView()
    await flushPromises()
    const btn = w.findAll('button').find((b) => b.text().includes('三维'))
    expect(btn).toBeTruthy()
    expect(btn!.attributes('disabled')).toBeUndefined()
    expect(w.text()).not.toContain('V7')
    expect(w.text()).not.toContain('排在下一份计划')
  })

  it('默然还是断面那一套：三维面板不对着没切过去的人加载', async () => {
    // 三维是懒加载的一块。这条钉的是**它不在一开始就加载** ——
    // 也就是「断面的首屏不付 Three 那个钱」。
    //
    // 后半段（切过去才出现）是这条的**判据**，不是添头：只有前半句的话，
    // 它在「三维压根没接」的那一版上同样是绿的 —— 一条在功能还不存在时
    // 照样成立的断言，钉不住任何东西。
    //
    // 这里**不 mock** 那一块：一渲染它就会把真的 `VolumeView` 拉起来
    // （连带 Three）。正是要这样 —— 「没切过去就不加载」这句话的证据，
    // 只能是「切过去之后它真的出来了」。
    stub(OK)
    const w = mountView()
    await flushPromises()
    expect(charts(w).length).toBe(2)                  // 断面那一套：切面场 + ΔT
    expect(w.text()).not.toContain('棚体三维温度场')

    const btn = w.findAll('button').find((b) => b.text().includes('三维'))
    await btn!.trigger('click')
    // 第一帧是**占位**（「正在加载三维模块…」，`delay: 0`）——这就是懒加载的样子。
    await flushPromises()
    expect(w.text()).toContain('正在加载三维模块')
    // 再等那一块真的上来。
    expect(await until(() => w.text().includes('棚体三维温度场')),
      '三维那一块一直停在占位上').toBe(true)
    expect(charts(w).length).toBe(0)                  // 四块二维面板让位
    expect(w.text()).not.toContain('三个断面的温度场')
  })

  it('ΔT 面板报出门禁口径', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('门禁')
    expect(w.text()).toContain('812')
  })

  it('未标定时明确标出「未标定」', async () => {
    // 兜底参数与标定后的数**同折族、不同参数，不可直接比大小** ——
    // 界面上不标，看图的人会以为这是标定过的结果。
    stub({ ...OK, '/api/field/sections': { ...SECTIONS, calibrated: false } })
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('未标定')
  })

  it('后端挂了就把后端的原话显示出来，不吞成空白', async () => {
    // 名字只说这条测试真做的事：应用显示的是后端 `detail` 的**原话**，
    // 而消息里并没有接口名 —— 「说清是哪个接口挂了」在这里断言不了。
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('{"detail":"数据集不存在：C:/x.xlsx"}', {
        status: 404, headers: { 'Content-Type': 'application/json' } })))
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('数据集不存在')
  })

  it('一排四张指标卡，第四格在拒绝报数（spec §6.2 页③）', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    const cards = w.findAll('.stat')
    expect(cards.map((c) => c.find('.label').text()))
      .toEqual(['时刻', '色标', '标定', '无测量带'])
    const band = cards[3]
    expect(band.find('.value').text()).toContain('不报数')
    // 第四格**没有**出处图章 —— 它不是从一个接口取来的数，是一句口径。
    // 查 `exists()` 而不是 `text()`：没有图章时 `StatCard` 渲染的是 `.blank`
    // 占位，`.prov` 根本不在 DOM 里，空包装上 `.text()` 会**抛**，不是回空串。
    expect(band.find('.prov').exists(), '第四格不该挂出处图章').toBe(false)
  })

  it('指标卡不是表格，所以第一张表仍然是读数表（spec §十三.1）', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    charts(w)[0].vm.$emit('pick', { seriesIndex: 1, value: [1, 1] })
    await flushPromises()
    const t = w.find('table')
    expect(t.text(), '第一张表不再是读数表').toContain('回答')
    expect(t.text()).toContain('43.22')
  })

  it('散文折进唯一一处「口径与出处」', async () => {
    stub(OK)
    const w = mountView()
    await flushPromises()
    const why = w.findAll('details.why')
    expect(why.length).toBe(1)
    expect(why[0].text()).toContain('三种回答')
  })

  it('视图切换是一条分段控件，不是一排带圆角边框的按钮（spec §九 / 终审 I-1）', async () => {
    // spec §九 逐字要求：`fieldset.rail-box` 的「一个 legend 加几个按钮」
    // 改成**分段控件** —— 一条描边的底，内部按钮无边框、无间距、相邻处一条竖线，
    // 选中的那个叶子底。这一块正是 §一 成因 5「chrome 是细线」的现场：
    // 各带圆角边框的按钮摆一排，读起来是「带框的小表单」，不是开关。
    //
    // 顺带把 `data-view` 钉上：§十三.4 要求页③ 与实时屏的视图按钮**都**带它，
    // 而页③ 这边一直没带（实时屏有）——两条页面对同一件事给了两套钩子，
    // 改的时候只测得到一半。
    stub(OK)
    const w = mountView()
    await flushPromises()
    const seg = w.find('fieldset.rail-box .seg')
    expect(seg.exists(), '视图切换没有分段控件的底').toBe(true)
    expect(seg.findAll('button').map((b) => b.text())).toEqual(['断面', '三维'])
    expect(seg.findAll('[data-view]').map((b) => b.attributes('data-view')))
      .toEqual(['section', 'volume'])
  })

  it('时刻在屏上处处走 `fmtTime`，不把 ISO 的 T 印给人看（终审 I-3）', async () => {
    // `format.ts` 存在的**全部理由**就是「同一个数在四页上是同一种写法」，
    // 而 `fmtTime` 的 doc 第一句就是「ISO 里那个 T 不给人看」。
    // 这一页原来有两处直接把载荷里的 `2026-07-27T12:00:00` 铺在屏上
    // （指标卡的「时刻」与左栏游标下面那一行）——同一页上两个时刻两种写法，
    // 正是本次要治的「文档感」的另一种形态。
    stub(OK)
    const w = mountView()
    await flushPromises()
    expect(w.text(), '屏上还印着带 T 的时间戳').not.toContain('2026-07-27T')

    const card = w.findAll('.stat')[0]
    expect(card.find('.label').text()).toBe('时刻')
    expect(card.find('.value').text()).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  })
})

describe('模型库与页③', () => {
  beforeEach(() => { installEnvironment(); vi.restoreAllMocks() })

  /** 「有一条能用」的那一份：第一行 compatible，且它就是当前。 */
  const USABLE = makeModelsPayload()

  /** 「一条能用的都没有」：把每一行都标成对不上。 */
  function noneUsable() {
    const p = makeModelsPayload()
    p.rows = p.rows.map((r) => ({ ...r, compatible: false,
                                  why: '数据来源不同：别人家的棚.xlsx' }))
    p.current_id = null
    return p
  }

  function mountWithModels(payload: unknown) {
    stub({ ...OK, '/api/models': payload })
    return mountView()
  }

  it('页首有一个下拉，列出能用的与对不上的', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    const opts = w.get('#field-model').findAll('option')
    expect(opts.map((o) => o.text()).join(' ')).toContain('七月下旬那套')
    expect(opts.map((o) => o.text()).join(' ')).toContain('别人家的棚.xlsx')
    expect(opts).toHaveLength(2)
  })

  it('对不上的选项被标出来而且选不了', async () => {
    // 规格书 §6.4：对不上的也要**列出来**（用户得知道库里有什么、
    // 为什么用不上），但选不中。
    const w = mountWithModels(USABLE)
    await flushPromises()
    const bad = w.get('#field-model').findAll('option')
      .find((o) => o.text().includes('别人家的棚.xlsx'))!
    expect(bad.attributes('disabled'), '对不上的那一项能选中').toBeDefined()
    expect(bad.text()).toContain('数据来源不同')
  })

  it('没有可用模型时一个图都不画，而且一个 field 接口都不打', async () => {
    // ⭐ Review Focus 5，也是整条需求的原点：不给用户一个「看着对的错场」。
    //
    // ⚠️ 断言的是 `charts(w)` 与**请求**，不是 `findAll('canvas')`：
    // 这个文件里 `EChart` 是替身（`<div class="chart-stub" />`），
    // jsdom 里本来就没有 canvas —— `expect(w.findAll('canvas')).toHaveLength(0)`
    // 是一条**永远绿**的断言，删掉组件它也绿。
    const w = mountWithModels({ rows: [], current_id: null,
                                dataset_file: 'f.xlsx', dataset_sig: 'a' })
    await flushPromises()
    expect(w.text()).toContain(FIELD_MODEL.none)
    expect(w.text()).toContain(FIELD_MODEL.toLibrary)
    expect(w.text()).toContain(FIELD_MODEL.toTrain)
    expect(charts(w), '没有可用模型却画了图').toHaveLength(0)
    // 断面载荷里那句话 —— 它只可能来自 `/api/field/sections`
    expect(w.text()).not.toContain('三格共享同一个色标范围')
    // ⭐ 而且**根本没问**：多打三个请求只是白等，还会让后端白算一遍场
    expect(urls.filter((u) => u.includes('/api/field/')),
      '没有可用模型却去取了场的数据').toEqual([])
  })

  it('全都对不上时也走空态，不是半画', async () => {
    // 上面那条是「一行都没有」，这条是「有两行、一行都用不上」——
    // 两条分开写，因为它们是两种不同的分支，而后者更容易被写成
    // 「有模型，那就画吧」。
    const w = mountWithModels(noneUsable())
    await flushPromises()
    expect(w.text()).toContain(FIELD_MODEL.none)
    expect(charts(w)).toHaveLength(0)
    expect(urls.filter((u) => u.includes('/api/field/'))).toEqual([])
  })

  it('有可用模型时照常画场，并且页首有下拉', async () => {
    // 上面两条的反面。少了它，一个「永远走空态」的实现照样全绿 ——
    // 而那是这条规则最坏的坏法：页③ 从此什么都画不出来，还不报错。
    const w = mountWithModels(USABLE)
    await flushPromises()
    expect(w.find('#field-model').exists()).toBe(true)
    expect(w.text()).not.toContain(FIELD_MODEL.none)
    // 与文件里那条既有的「一开始就挂上」同数：切面场、ΔT，一张不多一张不少
    // （曲线要等点选）。写成精确值才拦得住「模型对不上也照样把两张画上」。
    expect(charts(w), '有可用模型却没画').toHaveLength(2)
    expect(urls.some((u) => u.includes('/api/field/sections'))).toBe(true)
  })

  it('选另一个模型会把它设成全站当前', async () => {
    // 页③ 与页⑤ 共用「当前模型」这一个概念（规格书 D3）—— 换一处两处都换。
    //
    // ⚠️ 这里**必须**让第二行也可用：`USABLE` 里第二行是对不上的，而下拉里
    // 对不上的那些是 `disabled` —— 拿它演「换一个模型」等于演一件用户做不到
    // 的事（`setValue` 是直接写 DOM，绕过 disabled）。对不上那一项的处置
    // 由上面「对不上的选项被标出来而且选不了」钉着。
    const p = makeModelsPayload()
    p.rows[1] = { ...p.rows[1], compatible: true, why: '' }
    const w = mountWithModels(p)
    await flushPromises()
    await w.get('#field-model').setValue('2')
    await flushPromises()
    expect(urls.some((u) => u.includes('/api/models/2/current')),
      '换了一个模型却没有把它设成全站当前').toBe(true)
  })
})
