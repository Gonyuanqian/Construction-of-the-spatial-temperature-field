import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import FieldView from './FieldView.vue'
import { createAppRouter } from '../router'
import { BORROWED, FIELD_MODEL } from '../design/copy'
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
 * field 那两个接口那一份。
 *
 * ⚠️ **`/api/models` 必须在这里**（从 Task 10 起）：这一页现在先问库里有
 * 没有能用的模型，没有就一个场都不画、一个 field 接口都不打。
 * 缺了它，`stub()` 会把 `/api/models` 判成 404，下面那几条既有用例
 * 全都掉进空态 —— 而它们一条都没改过，红的理由离「少了一个键」很远。
 *
 * ⚠️ 原来这里还有第三个键 `/api/field/curve`（点选之后那条 5 天曲线）。
 * 2026-10-09 连同点选一起撤了 —— 页③ 不再打它，再挂一个 stub 只是让读的人
 * 以为屏上还画着一条曲线。
 */
const OK = { '/api/field/compare': COMPARE,
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

async function startField(w: ReturnType<typeof mountView>, id = '1'): Promise<void> {
  await w.get('#field-model').setValue(id)
  await w.get('[data-action="build-field"]').trigger('click')
  await flushPromises()
}

async function mountBuiltView() {
  const w = mountView()
  await flushPromises()
  await startField(w)
  return w
}

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

  it('断面那一套就两张图：切面场与 ΔT', async () => {
    // 原来是三张 —— 第三张是「点中一格之后的 5 天曲线」。2026-10-09 连图的
    // 点选交互一起撤掉了（见 `FieldView.vue` 文件顶）。写成精确的 2，才拦得住
    // 那两张卡悄悄接回来、或者又长出一张新图。
    stub(OK)
    const w = await mountBuiltView()
    expect(charts(w).length).toBe(2)          // 切面场、ΔT
    expect(w.text()).toContain('空间温度场的构建')
    // 撤掉的那两张卡上的标题不该还在屏上。
    expect(w.text()).not.toContain('这一格是什么')
    expect(w.text()).not.toContain('这一点的 5 天')
  })

  it('切面图画的是后端送来的那三格', async () => {
    stub(OK)
    const w = await mountBuiltView()
    const o = charts(w)[0].props('option') as any
    expect(o.series).toHaveLength(15)
    expect(o.visualMap.min).toBe(SECTIONS.vmin)
    expect(o.visualMap.max).toBe(SECTIONS.vmax)
  })

  it('换时刻会重新取场', async () => {
    // 名字只说这条测试真做的事：夹具对任何 t_index 都回同一个 time，
    // 「显示的时刻跟着变」在这里断言不了 —— 写进名字就是一句空话。
    stub(OK)
    const w = await mountBuiltView()
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
    const w = await mountBuiltView()
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
    const w = await mountBuiltView()
    expect(charts(w).length).toBe(2)                  // 断面那一套：切面场 + ΔT
    expect(w.text()).not.toContain('棚体三维温度场')

    const btn = w.findAll('button').find((b) => b.text().includes('三维'))
    await btn!.trigger('click')
    // 导入可能命中其他用例已加载的模块；此时会直接显示模块，不要求占位停留一拍。
    await flushPromises()
    expect(/正在加载三维模块|棚体三维温度场/.test(w.text())).toBe(true)
    // 再等那一块真的上来。
    expect(await until(() => w.text().includes('棚体三维温度场')),
      '三维那一块一直停在占位上').toBe(true)
    expect(charts(w).length).toBe(0)                  // 四块二维面板让位
    expect(w.text()).not.toContain('三个断面的温度场')
  })

  it('ΔT 面板报出门禁口径', async () => {
    stub(OK)
    const w = await mountBuiltView()
    expect(w.text()).toContain('门禁')
    expect(w.text()).toContain('812')
  })

  it('未标定时明确标出「未标定」', async () => {
    // 兜底参数与标定后的数**同折族、不同参数，不可直接比大小** ——
    // 界面上不标，看图的人会以为这是标定过的结果。
    stub({ ...OK, '/api/field/sections': { ...SECTIONS, calibrated: false } })
    const w = await mountBuiltView()
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
    const w = await mountBuiltView()
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

  it('页面不再有读数表，散文折进唯一一处「口径与出处」', async () => {
    // 撤掉「点选读数」那张卡之后，页③ 上**一张表都没有了**（页顶那排指标卡
    // 不是表）。原来这条钉的是「第一张表仍然是读数表」—— 现在钉它的反面：
    // 读数表没了。留着「第一张表是读数表」就等于在讲一个屏上不存在的东西。
    stub(OK)
    const w = await mountBuiltView()
    expect(w.find('table').exists(), '读数表又回来了').toBe(false)

    const why = w.findAll('details.why')
    expect(why.length).toBe(1)
    // 折在里面那句读图口径还在：三个断面共用同一个色标范围。
    expect(why[0].text()).toContain('共用同一个色标范围')
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
    const w = await mountBuiltView()
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
    const w = await mountBuiltView()
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
    p.rows = p.rows.map((r) => ({ ...r, compatible: false, borrowed: false,
                                  why: '这一份是用别的特征组标出来的' }))
    p.current_id = null
    return p
  }

  function mountWithModels(payload: unknown) {
    stub({ ...OK, '/api/models': payload })
    return mountView()
  }

  it('首次进入即使已有工作区模型，也只加载列表并等待选择', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    expect((w.get('#field-model').element as HTMLSelectElement).value).toBe('')
    expect(w.get('[data-action="build-field"]').attributes('disabled')).toBeDefined()
    expect(w.text()).toContain(FIELD_MODEL.waiting)
    expect(charts(w)).toHaveLength(0)
    expect(w.findAll('.stat')).toHaveLength(0)
    expect(w.find('[data-view]').exists()).toBe(false)
    expect(urls).toEqual(['/api/models'])
  })

  it('启用模型完成前不构场，连续点击也只启用一次', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    const respond = vi.mocked(fetch).getMockImplementation()!
    let finish!: (response: Response) => void
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    vi.mocked(fetch).mockImplementation((input, init) => {
      if (String(input).endsWith('/current')) {
        urls.push(String(input))
        return pending
      }
      return respond(input, init)
    })
    await w.get('#field-model').setValue('2')
    await w.get('[data-action="build-field"]').trigger('click')
    await w.get('[data-action="build-field"]').trigger('click')
    expect(urls.filter((u) => u.includes('/api/field/'))).toEqual([])
    expect(urls.filter((u) => u.endsWith('/current'))).toEqual(['/api/models/2/current'])
    expect(w.get('#field-model').attributes('disabled')).toBeDefined()
    finish(new Response('{"id":2}', { status: 200 }))
    await flushPromises()
    expect(charts(w)).toHaveLength(2)
  })

  it('启用模型失败会显示原因，不构场且允许重试', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    const respond = vi.mocked(fetch).getMockImplementation()!
    let fail = true
    vi.mocked(fetch).mockImplementation((input, init) => {
      if (String(input).endsWith('/current') && fail) {
        urls.push(String(input))
        return Promise.resolve(new Response('{"detail":"所选模型暂不可用"}', { status: 409 }))
      }
      return respond(input, init)
    })
    await startField(w)
    expect(w.get('[role="alert"]').text()).toBe('所选模型暂不可用')
    expect(urls.filter((u) => u.includes('/api/field/'))).toEqual([])
    expect(charts(w)).toHaveLength(0)
    expect(w.get('[data-action="build-field"]').attributes('disabled')).toBeUndefined()
    fail = false
    await w.get('[data-action="build-field"]').trigger('click')
    await flushPromises()
    expect(charts(w)).toHaveLength(2)
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('准备模型期间离开页面，不再发起构场请求', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    let finish!: (response: Response) => void
    vi.mocked(fetch).mockImplementation((input) => {
      urls.push(String(input))
      return new Promise<Response>((resolve) => { finish = resolve })
    })
    await w.get('#field-model').setValue('1')
    await w.get('[data-action="build-field"]').trigger('click')
    w.unmount()
    finish(new Response('{"id":1}', { status: 200 }))
    await flushPromises()
    expect(urls.filter((u) => u.includes('/api/field/'))).toEqual([])
  })

  it('页首有一个下拉，库里的三档都列出来', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    const opts = w.get('#field-model').findAll('option')
    const all = opts.map((o) => o.text()).join(' ')
    expect(all).toContain('七月下旬那套')
    expect(all).toContain('别人家的棚.xlsx')
    // 三档各在：本地的、借来的、用不了的。少一档这条就红 ——
    // 「库里有的都能挑」这句话，靠的正是每一行都列在这儿。
    expect(opts).toHaveLength(4) // 待选择占位 + 三档模型。
  })

  it('借来的那一项**选得中**，而且标着「借来的」', async () => {
    // ⭐ 2026-10-10 用户裁定「模型不绑数据集」在屏上的落点：库里有就能挑。
    // 这一条不能省 —— 少了它，`compatible` 回到「两轴都对得上」照样全绿，
    // 而用户看到的还是「明明库里有模型、页③ 就是不给用」。
    const w = mountWithModels(USABLE)
    await flushPromises()
    const borrowed = w.get('#field-model').findAll('option')
      .find((o) => o.text().includes('别人家的棚.xlsx'))!
    expect(borrowed.attributes('disabled'), '借来的那一项选不了').toBeUndefined()
    expect(borrowed.text()).toContain(BORROWED)
    // 借来的**不是**用不了的：理由那一栏不该印在它身上。
    expect(borrowed.text()).not.toContain('特征组')
  })

  it('对不上的选项被标出来而且选不了', async () => {
    // 规格书 §6.4：对不上的也要**列出来**（用户得知道库里有什么、
    // 为什么用不上），但选不中。
    const w = mountWithModels(USABLE)
    await flushPromises()
    const bad = w.get('#field-model').findAll('option')
      .find((o) => o.text().includes('另一个特征组标的'))!
    expect(bad.attributes('disabled'), '对不上的那一项能选中').toBeDefined()
    expect(bad.text()).toContain('这一份是用别的特征组标出来的')
  })

  it('借来的那一份：图章说「借来的」，口径里逐字印着后端那句话', async () => {
    // ⭐ 2026-10-10 用户裁定「模型不绑数据集」的另一半：借来用的**必须说出来**。
    // 图上那张场是拿别人的参数算的，误差数不算这份数据的成绩 —— 不说，用户
    // 就会把它当本地模型的结果读。
    //
    // ⚠️ 印的是载荷里那句 `mismatch_note`**本身**（后端 `deps._BORROWED_NOTE`
    // 那唯一一句），不是前端另写的一句解释 —— 同一个事实两份措辞，迟早
    // 一处改了另一处没改。所以这里断的是「载荷里那串字原样在屏上」。
    const NOTE = '这一份模型的参数不是用当前这份数据标出来的'
    stub({ ...OK, '/api/field/sections': { ...SECTIONS, mismatch_note: NOTE } })
    const w = await mountBuiltView()
    expect(w.text()).toContain(`已标定（${BORROWED}）`)
    // ⚠️ 在「口径与出处」里，不是常驻在屏上：它是解释，不是读数。
    // `design/prose.test.ts`（spec §十二.11）判的正是这件事。
    const why = w.findAll('details.why')
    expect(why).toHaveLength(1)
    expect(why[0].text()).toContain(NOTE)
  })

  it('本地的那一份：图章是「已标定」，口径里没有借来那句', async () => {
    // 上面那条的反面。少了它，一个「永远说借来的」的实现照样能全绿 ——
    // 而那是这条标注最坏的坏法：本地模型也被标成来路不明。
    stub(OK)                                    // `SECTIONS.mismatch_note` 缺省
    const w = await mountBuiltView()
    expect(w.text()).toContain('已标定')
    expect(w.text()).not.toContain(`已标定（${BORROWED}）`)
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

  it('有可用模型时，确认构场后才请求并展示温度场', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    expect(w.find('#field-model').exists()).toBe(true)
    expect(w.text()).not.toContain(FIELD_MODEL.none)
    expect(charts(w)).toHaveLength(0)
    await startField(w)
    expect(charts(w), '有可用模型却没画').toHaveLength(2)
    expect(urls.some((u) => u.includes('/api/field/sections'))).toBe(true)
  })

  it('选择模型只更新选项，点击开始构场才启用所选模型', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    await w.get('#field-model').setValue('2')
    await flushPromises()
    expect(urls.filter((u) => /\/current|\/api\/field\//.test(u))).toEqual([])
    await w.get('[data-action="build-field"]').trigger('click')
    await flushPromises()
    expect(urls.some((u) => u.includes('/api/models/2/current')),
      '确认构场后没有启用所选模型').toBe(true)
    expect(urls.indexOf('/api/models/2/current'))
      .toBeLessThan(urls.findIndex((u) => u.includes('/api/field/sections')))
  })

  it('更换模型会收起旧场，重新确认后才计算新场', async () => {
    const w = mountWithModels(USABLE)
    await flushPromises()
    await startField(w)
    const before = urls.filter((u) => u.includes('/api/field/sections')).length

    await w.get('#field-model').setValue('2')
    await flushPromises()
    expect(charts(w)).toHaveLength(0)
    expect(w.findAll('.stat')).toHaveLength(0)
    expect(urls.filter((u) => u.includes('/api/field/sections'))).toHaveLength(before)
    expect(urls).not.toContain('/api/models/2/current')
    await w.get('[data-action="build-field"]').trigger('click')
    await flushPromises()

    expect(urls.filter((u) => u.includes('/api/field/sections')).length,
      '重新确认后没有构建新模型的场').toBeGreaterThan(before)
    expect(urls.filter((u) => u.includes('/api/field/compare')).length,
      '换了模型却没重取对比那一张').toBeGreaterThan(1)
  })

  it('成品读不动时，口径里印的是后端那句 artifact_note', async () => {
    const NOTE = '这一条的成品读不动（格式是第 2 版，现在是第 1 版），已退回现训。'
    stub({ ...OK, '/api/field/sections': { ...SECTIONS, artifact_note: NOTE } })
    const w = await mountBuiltView()
    // ⚠️ 仍然只有**一个** `details.why` —— 两句解释在同一个块里，不是两块。
    //    多出一块会让 `design/prose.test.ts`（spec §十二.11）那条断言的
    //    「解释只有一处」失效。
    const why = w.findAll('details.why')
    expect(why).toHaveLength(1)
    expect(why[0].text()).toContain(NOTE)
  })

  it('artifact_note 为空时口径里多一个字都没有', async () => {
    // 这一档是**常态**（成品都在、都读得动）。少了它，一个「永远印那句话」
    // 的实现照样全绿 —— 而它会让每一页都在报一件没发生的事。
    stub(OK)                                  // `SECTIONS.artifact_note` 缺省是 ''
    const w = await mountBuiltView()
    expect(w.text()).not.toContain('成品读不动')
  })

  it('artifact_note 不改变「已标定 / 借来的」那个图章', async () => {
    // ⭐ Review Focus 5：两者是**两个格**。这一句在，图章还是「已标定」——
    //    共用一格的话，一份本地的模型会在这条用例上现原形。
    const NOTE = '这一条的成品读不动（字节坏了），已退回现训。'
    stub({ ...OK, '/api/field/sections': {
      ...SECTIONS, mismatch_note: '', artifact_note: NOTE } })
    const w = await mountBuiltView()
    expect(w.text()).toContain('已标定')
    expect(w.text()).not.toContain(`已标定（${BORROWED}）`)
    expect(w.findAll('details.why')[0].text()).toContain(NOTE)
  })
})
