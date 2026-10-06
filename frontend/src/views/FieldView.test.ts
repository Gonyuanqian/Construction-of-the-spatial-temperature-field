import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import FieldView from './FieldView.vue'

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

const OK = { '/api/field/curve': CURVE, '/api/field/compare': COMPARE, '/api/field/sections': SECTIONS }

function mountView() {
  return mount(FieldView, {
    global: {
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
})
