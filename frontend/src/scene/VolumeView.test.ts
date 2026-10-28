import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import { makeVolumePayload } from '../test/fixtures'

// **Three 不进测试。** 这一块画的那一半在 `VolumeScene.test.ts` 里单独测，
// 而这里测的是取数、判定、文案、防抖 —— 全都与 WebGL 无关。
vi.mock('./VolumeScene.vue', () => ({
  default: {
    name: 'VolumeScene',
    // ⚠️ 替身的属性表是**写死的**：不在这个数组里的属性会被 Vue 当成
    // 透传属性（fallthrough attr），于是 `findComponent(...).props('x')`
    // 读出 `undefined` —— 而生产代码是对的。新加一个属性就要来这里加一个名字，
    // 否则那条测试会以「功能没接上」的样子红着，指错方向。
    props: ['spec', 'payload', 'picked', 'cutY', 'showViewControls'],
    emits: ['hover', 'pick', 'ready'],
    template: '<div class="scene-stub" />',
  },
}))

import VolumeView from './VolumeView.vue'

const VOLUME = makeVolumePayload()

function stub(body: unknown = VOLUME) {
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    urls.push(String(url))
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
  return urls
}

// ⚠️ 第三个参数是 2026-10-12 加的（页⑤ 要传 `panels`）。**位置参数一个都没动** ——
// 计划给的替换签名只有一个 `extra` 对象，那会把上面十几处 `mountView(12, '…')`
// 全部改成读一个带默认值的对象，是同一个接口的第二种叫法，白改一圈。
async function mountView(
  tIndex = 12, clockTime = VOLUME.time, extra: Record<string, unknown> = {},
) {
  const w = mount(VolumeView, { props: { tIndex, clockTime, ...extra } })
  await flushPromises()
  return w
}

/** 把三个输入框填上。`inputs` 是 [x, y, z]。 */
async function typeQuery(w: ReturnType<typeof mount>, values: [string, string, string]) {
  const inputs = w.findAll('input[type="number"]')
  expect(inputs, '三个坐标输入框不在').toHaveLength(3)
  for (let i = 0; i < 3; i++) await inputs[i].setValue(values[i])
}

async function submitQuery(w: ReturnType<typeof mount>) {
  const btn = w.findAll('button').find((b) => b.text().includes('查询'))
  expect(btn, '查询按钮不在').toBeTruthy()
  await btn!.trigger('click')
  await flushPromises()
}

describe('页③ 三维面板', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('未选点或未查询时保留完整结果字段，清除选点后恢复占位', async () => {
    stub()
    const w = await mountView()
    const selected = () => w.get('table[aria-label="画布选点读数"]')
    const queried = () => w.get('table[aria-label="坐标查询结果"]')
    expect(selected().findAll('tr')).toHaveLength(4)
    expect(queried().findAll('tr')).toHaveLength(3)
    expect(selected().text()).toContain('待选点')
    expect(queried().text()).toContain('待查询')

    const scene = w.findComponent({ name: 'VolumeScene' })
    scene.vm.$emit('pick', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    expect(selected().text()).toContain('(0.70, 3.00, 0.70)')
    await w.get('button[aria-label="取消钉住"]').trigger('click')
    expect(selected().findAll('tr')).toHaveLength(4)
    expect(selected().text()).toContain('待选点')
    expect(queried().text()).toContain('待查询')
  })

  it('一挂上就去取这一卷，参数只带 t_index（其余走后端默认）', async () => {
    const urls = stub()
    await mountView()
    expect(urls).toHaveLength(1)
    expect(urls[0]).toContain('/api/field/volume')
    expect(urls[0]).toContain('t_index=12')
  })

  it('传 source="live" 时改打实时那条取数口，且不再带 t_index 查询串', async () => {
    // 实时模式那一屏**复用这一块**（规格书 §「三维：懒加载 scene/VolumeView.vue」）：
    // 判定、文案、吸附、坐标查询只有这一处，实时屏不新写第二份。
    // 两条路的载荷形状本来就同源，差别只在**去哪儿取** ——
    // 这条钉的就是那个差别，以及「实时那条不走查询串」。
    const urls = stub()
    const w = mount(VolumeView, {
      props: { tIndex: 3, clockTime: VOLUME.time, source: 'live' },
    })
    await flushPromises()
    expect(urls).toEqual(['/api/live/volume/3'])
    expect(w.text()).toContain('棚体三维温度场')
  })

  it('**拖时刻滑块只发一次请求**（防抖）', async () => {
    // 不防抖的话，一次拖动就是十几个 1.2 s 的构体请求，最后一个才用得上。
    vi.useFakeTimers()
    try {
      const urls = stub()
      const w = mount(VolumeView, { props: { tIndex: 12, clockTime: VOLUME.time } })
      await vi.advanceTimersByTimeAsync(0)
      expect(urls).toHaveLength(1)

      for (const t of [13, 14, 15]) {
        await w.setProps({ tIndex: t })
        await vi.advanceTimersByTimeAsync(100)     // 比防抖窗口短
      }
      expect(urls, '拖动过程中就发了请求').toHaveLength(1)

      await vi.advanceTimersByTimeAsync(400)
      expect(urls, '停手之后应当只补一次').toHaveLength(2)
      expect(urls[1]).toContain('t_index=15')
    } finally {
      vi.useRealTimers()
    }
  })

  it('**正在构体时说清自己构的是哪一刻**（Review Focus 5）', async () => {
    // 三维比二维慢（实测换一帧约 1.2 s）。这段时间里两张图**不是同一刻** ——
    // 面板要说出来，而不是等构好了再默默换掉。
    // `release` 由下面那个 fetch 假实现赋上，而它一进 `mount()` 就会被调到 ——
    // 所以走到 `release()` 那一行时它一定在。写成明确赋值断言而不是 `| null`：
    // 赋值发生在闭包里，外面的控制流分析看不见，`release?.()` 会被收窄成
    // `never`，`vue-tsc` 报 TS2349。
    let release!: () => void
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Promise<Response>((resolve) => {
        release = () => resolve(new Response(JSON.stringify(VOLUME), {
          status: 200, headers: { 'Content-Type': 'application/json' },
        }))
      })))
    const w = mount(VolumeView, { props: { tIndex: 12, clockTime: VOLUME.time } })
    await Promise.resolve()
    expect(w.text()).toContain('正在构体')
    // 只说「正在构体」不够 —— 这一条要的是「说清自己构的是**哪一刻**」，
    // 而那半句由 `正在构体…（{{ clockTime }}）` 提供。把它删掉，光断言
    // 「正在构体」照样绿：名字承诺的失败模式就抓不到了。
    expect(w.text()).toContain('2026-07-23 12:00')
    release()
    await flushPromises()
    expect(w.text()).not.toContain('正在构体')
  })

  it('画面还停在上一刻而时钟已经走了时，明说这件事', async () => {
    stub()
    const w = await mountView(12, '2026-07-23T17:40:00')
    expect(w.text()).toContain('画面仍是')
    expect(w.text()).toContain('2026-07-23 12:00')
    expect(w.text()).toContain('2026-07-23 17:40')
  })

  it('时刻对上了就不说那句', async () => {
    stub()
    const w = await mountView(12, VOLUME.time)
    expect(w.text()).not.toContain('画面仍是')
  })

  it('**每一条读数都带时刻**（Review Focus 5）', async () => {
    stub()
    const w = await mountView()
    // 悬停事件由场景发上来。这里直接对着 stub 组件发。
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    const table = w.find('table')
    expect(table.exists(), '悬停之后读数表没出现').toBe(true)
    expect(table.text()).toContain('2026-07-23 12:00')
    // 夹具里 (ix=1, iz=1) 那一格是 2（`test/fixtures.ts` 的 `makeValues()`）。
    // 用夹具自己的数，不另写一个：写死一个夹具里没有的数，这条会红，
    // 而红的原因是夹具对不上，不是功能坏了。
    expect(table.text()).toContain('2.00')
  })

  it('悬停读出最近格点的坐标，并说清这一片是实测还是混合', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 1, ix: 2, iz: 3 })
    await flushPromises()
    const t = w.find('table')
    expect(t.text()).toContain('(1.40, 3.50, 2.10)')
    expect(t.text()).toContain('混合')
    expect(t.text()).toContain('不是实测断面')
  })

  it('悬停到无测量带上时不报数', async () => {
    stub()
    const w = await mountView()
    // (2, 0) 是斜纹格，且值确实在（夹具里是 3）。
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 0, ix: 2, iz: 0 })
    await flushPromises()
    expect(w.find('table').text()).toContain('不报数')
  })

  it('悬停到拱外时答无定义', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 0, ix: 0, iz: 3 })
    await flushPromises()
    expect(w.find('table').text()).toContain('无定义')
  })

  it('单击把当前格点钉住，再悬停别处读数不变', async () => {
    stub()
    const w = await mountView()
    const scene = w.findComponent({ name: 'VolumeScene' })
    scene.vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    scene.vm.$emit('pick', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    scene.vm.$emit('hover', { planeIndex: 1, ix: 3, iz: 0 })
    await flushPromises()
    const t = w.find('table')
    expect(t.text()).toContain('(0.70, 3.00, 0.70)')     // 还是钉住的那个
    expect(t.text()).not.toContain('已钉住')
    expect(t.text()).not.toContain('读数不跟鼠标跑')
    expect(w.find('button[aria-label="取消钉住"]').exists()).toBe(true)
  })

  it('取消钉住之后读数跟着鼠标走', async () => {
    stub()
    const w = await mountView()
    const scene = w.findComponent({ name: 'VolumeScene' })
    scene.vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    scene.vm.$emit('pick', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    const btn = w.find('button[aria-label="取消钉住"]')
    expect(btn.exists(), '取消钉住按钮不在').toBe(true)
    await btn.trigger('click')
    await flushPromises()
    scene.vm.$emit('hover', { planeIndex: 1, ix: 3, iz: 0 })
    await flushPromises()
    expect(w.find('table').text()).toContain('(2.10, 3.50, 0.00)')
  })

  it('载荷换了形状之后，钉住的那个下标被放掉（不然会读到越界）', async () => {
    const urls = stub()
    const w = await mountView()
    const scene = w.findComponent({ name: 'VolumeScene' })
    scene.vm.$emit('pick', { planeIndex: 1, ix: 3, iz: 3 })
    await flushPromises()
    expect(w.find('table').exists()).toBe(true)

    // 换一卷：只剩一片、四个格子。
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      urls.push(String(url))
      const small = makeVolumePayload({
        x: [0, 1], z: [0, 1],
        planes: [{ y: 3, measured: true, shed: 'p1', values: [[1, 2], [3, 4]], mean: 26.5 }],
        stripes: [],
      })
      return new Response(JSON.stringify(small), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }))
    await w.setProps({ tIndex: 13 })
    await new Promise((r) => setTimeout(r, 400))
    await flushPromises()
    expect(w.find('button[aria-label="取消钉住"]').exists(), '越界的钉住没被放掉').toBe(false)
    expect(w.find('.pick-readout').classes()).toContain('is-empty')
    expect(w.find('.pick-readout').text()).toContain('待选点')
  })

  it('**坐标查询：同一个点，两条路给的答案一定一样**', async () => {
    stub()
    const w = await mountView()
    const scene = w.findComponent({ name: 'VolumeScene' })
    scene.vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    const byMouse = w.find('table').text()

    await typeQuery(w, ['0.7', '3.0', '0.7'])
    await submitQuery(w)
    const byQuery = w.findAll('table')[1].text()
    expect(byQuery).toContain('(0.70, 3.00, 0.70)')
    // 数值那句两处逐字相同 —— 判定与文案都只有一处。
    const value = byMouse.match(/现场重算：[\d.]+ °C/)
    expect(value, '悬停读数里没有那句数值').toBeTruthy()
    expect(byQuery).toContain(value![0])
  })

  it('读数表里的时刻走 `fmtTime`，不把 ISO 的 T 印给人看（终审 I-3）', async () => {
    // 这一块是页③ 与实时屏共用的三维面板；它的两张读数表原来直接铺载荷里的
    // `2026-07-23T12:00:00`。同一页上断面读数走 `fmtTime`、三维读数不走，
    // 「同一个数四页同一种写法」就不成立了。
    stub()
    // 时钟故意与载荷错开：这条要看的是**一整屏**，包括「画面仍是…」那句
    // 里嵌着的两个时刻 —— 它们原先也是原样铺出来的。
    const w = await mountView(12, '2026-07-23T17:40:00')
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    expect(w.text(), '屏上还印着带 T 的时间戳').not.toContain('2026-07-23T')
    expect(w.find('table').text()).toMatch(/2026-07-23 12:00/)
  })

  it('**坐标查询要写出吸附之后的坐标，不插值**', async () => {
    // 用户输的是 5.4、拿到的是 5.5 的值，不写出来就是撒谎。
    stub()
    const w = await mountView()
    // 先填充画布读数，确认它与下面的坐标查询结果各自保留自己的位置。
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    await typeQuery(w, ['1.23', '3.4', '0.66'])
    await submitQuery(w)
    expect(w.findAll('table')[1].text()).toContain('(1.40, 3.50, 0.70)')
  })

  it('**坐标超出这一卷的范围时报错，不给数**（Review Focus 2）', async () => {
    // 把它吸附到最近的边上格点，屏幕上写的是「最近格点」，而用户以为自己
    // 问的是 100 米处 —— 一个不是他问的答案，看起来却完全正常。
    stub()
    const w = await mountView()
    for (const bad of [['1.0', '100', '0.5'], ['-1', '3.0', '0.5'], ['1.0', '3.0', '9']]) {
      await typeQuery(w, bad as [string, string, string])
      await submitQuery(w)
      expect(w.find('[role="alert"]').exists(), `${bad} 应当报错`).toBe(true)
      expect(w.find('[role="alert"]').text()).toContain('超出这一卷的范围')
    }
  })

  it('超出范围之后把范围本身写出来', async () => {
    stub()
    const w = await mountView()
    await typeQuery(w, ['1.0', '100', '0.5'])
    await submitQuery(w)
    const t = w.find('[role="alert"]').text()
    expect(t).toContain('0.00 至 2.10')     // x
    expect(t).toContain('3.00 至 3.50')     // y，来自载荷的片，不是写死的 0 与 18
  })

  it('查询按钮在三个框都填上之前是禁用的', async () => {
    stub()
    const w = await mountView()
    const btn = () => w.findAll('button').find((b) => b.text().includes('查询'))!
    expect(btn().attributes('disabled')).toBeDefined()
    await typeQuery(w, ['1', '3', '0.5'])
    expect(btn().attributes('disabled')).toBeUndefined()
  })

  it('坐标里写了非数字时按钮仍然禁用（不是「查一下再说」）', async () => {
    stub()
    const w = await mountView()
    await typeQuery(w, ['1', 'abc', '0.5'])
    const btn = w.findAll('button').find((b) => b.text().includes('查询'))
    expect(btn!.attributes('disabled')).toBeDefined()
  })

  it('取数失败时把后端的原话显示出来', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('{"detail":"这一卷有 258852 个格子，超过上限 200000"}', {
        status: 400, headers: { 'Content-Type': 'application/json' } })))
    const w = await mountView()
    expect(w.text()).toContain('超过上限')
  })

  it('把载荷的口径与壳长的说明摆出来', async () => {
    // 夹具的 `note` 是空串，而 `toContain('')` 永远成立 —— 照计划那行写下来，
    // 这条断言等于没有。所以这里给它一句真的口径，测的还是同一件事：
    // **后端的 note 会被摆到界面上**。
    //
    // ⚠️ 这条同时也是「`showNotes` 默认开着」的钉子：页⑤ 不摆那两句
    // （用户裁定，见下面那一组），而默认值取的是「页③ 现在什么样」——
    // 把默认值翻成 `false`，这里立刻红。
    const note = '三格共享同一个色标范围；拱外不画。'
    stub(makeVolumePayload({ note }))
    const w = await mountView()
    expect(w.text()).toContain('示意')
    expect(w.text()).toContain(note)
  })
})

/**
 * 训练页保留三张独立卡片：画布在左，查询在右上，几何与剖切在查询下方。
 * 这里检查各张卡片的内容归属，实际行列位置需要浏览器布局验证。
 */
describe('训练页左右版面：画布与查询、几何控制', () => {
  /**
   * 按类名找到三张卡片，不把源码次序当成屏幕位置。
   * 实时页复用模板的 Teleport 顺序，训练页由 CSS 命名区域负责排列。
   */
  function columns(w: ReturnType<typeof mount>) {
    const grid = w.find('.vol-grid')
    expect(grid.exists(), '没有三维布局容器').toBe(true)
    const cols = Array.from(grid.element.children) as HTMLElement[]
    expect(cols, '应保留三张卡片').toHaveLength(3)
    const pick = (cls: string): HTMLElement => {
      const el = cols.find((c) => c.classList.contains(cls))
      expect(el, `没有 ${cls} 那一栏`).toBeTruthy()
      return el!
    }
    return { geom: pick('vol-geom'), stage: pick('vol-stage'), ask: pick('vol-ask') }
  }

  it('画布、几何与剖切、查询分别保留各自的内容', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', true)
    await flushPromises()
    const { geom, stage, ask } = columns(w)

    expect(stage.querySelector('.scene-stub'), '三维画布不在画布卡片').toBeTruthy()
    expect(geom.textContent).toContain('棚体示意长度')
    expect(ask.textContent).toContain('查一个坐标')
    // 反着再钉一遍：只写正例挡不住「三栏各装了一点」——那时候两边都含关键词，
    // 两条正例断言照样绿，而版面已经不是这个名字说的那个样子了。
    expect(geom.textContent, '几何卡片混入坐标查询').not.toContain('查一个坐标')
    expect(ask.textContent, '查询卡片混入几何设置').not.toContain('棚体示意长度')
    expect(ask.querySelector('.scene-stub'), '画布被复制到了右栏').toBeNull()
  })

  it('读数表也在右栏 —— 它与坐标查询是同一侧的话', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    const { ask } = columns(w)
    expect(ask.querySelector('table'), '读数表不在右栏').toBeTruthy()
  })

  it('三个模块各自复用统一卡片', async () => {
    // 2026-10-09 用户裁定：三栏拆开之后，三个部分直接浮在纸底上，只靠栏里那几个
    // `<fieldset>` 的细线互相区分。而同一页上「三个断面的温度场」「ΔT」都是
    // `<Card class="block">` —— **三维这一块是唯一一块没套卡片的**。
    //
    // 断言的是**用的是全站那一档卡片**（圆角与阴影的唯一一处，`components/Card.vue`），
    // 不是「有个框」：各写一遍自己的圆角与阴影，那条判据迟早守不住。
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', true)
    await flushPromises()
    const names = ['几何与剖切', '画布', '问数']
    Object.values(columns(w)).forEach((col, i) => {
      expect(col.classList.contains('card'), `${names[i]}不是一张卡片`).toBe(true)
    })
  })
})

/**
 * 剖切刀原先住在 `VolumeScene.vue` 里（连状态一起）。左栏要放它，它就得搬到
 * 页级 —— 而 `VolumeScene` 自己的文件头写着的正是「这一层只做 Three 的调用，
 * **不做任何判断**」：一个带状态的用户控件住在那里本来就不对。
 *
 * 「画不出来时不挂它」这条不变量也跟着控件一起搬上来了（原来挂在
 * `VolumeScene.test.ts` 上）。搬的理由不是测试写在哪边都能跑，而是**性质该由
 * 拥有它的那一层来守**：现在只有页级知道画布到底出来没有。
 */
describe('剖切刀：住在页级，且只在场景画得出来时才挂', () => {
  const cut = (w: ReturnType<typeof mount>) => w.find('input[aria-label="剖切刀"]')

  it('场景没报「画得出来」之前不挂 —— 一个对自己无效的控件比没有更难看', async () => {
    stub()
    const w = await mountView()
    expect(cut(w).exists(), '场景还没上来就挂了剖切刀').toBe(false)

    // 明说画不出来：仍然不挂。
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', false)
    await flushPromises()
    expect(cut(w).exists(), '场景说画不出来，剖切刀还挂着').toBe(false)

    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', true)
    await flushPromises()
    expect(cut(w).exists(), '场景上来了，剖切刀却没有').toBe(true)
  })

  it('初值是「不切」（最远的那一片），上下界与步长都来自载荷', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', true)
    await flushPromises()
    const input = cut(w)
    // 夹具的片在 y = 3 与 3.5，`y_step` 是 0.5。写死这三个数而不是断言
    // 「有个数就行」：范围推错了（比如按 sheds 的 3/9/15 算）照样「有个数」。
    expect(input.attributes('min')).toBe('3')
    expect(input.attributes('max')).toBe('3.5')
    expect(input.attributes('step')).toBe('0.5')
    expect(w.find('.vol-grid').text()).toContain('切到 y = 3.50 m 为止')
  })

  it('刀一拖，数就传给场景 —— 状态在页级，场景只照做', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', true)
    await flushPromises()
    expect(w.findComponent({ name: 'VolumeScene' }).props('cutY')).toBe(3.5)

    await cut(w).setValue('3')
    await flushPromises()
    expect(w.findComponent({ name: 'VolumeScene' }).props('cutY'), '刀动了，场景没收到')
      .toBe(3)
    expect(w.find('.vol-grid').text()).toContain('切到 y = 3.00 m 为止')
  })
})

/**
 * 2026-10-09 用户裁定：页⑤ 不摆那排指标卡（「第几帧，一共多少帧……后端系统
 * 知道就行」），但「手上这一屏画的是哪一刻」要一直看得见 —— 用户的话是
 * 「这个时间可以放到生成的三维影像图中的左上角或者右上角就行了」。
 *
 * ⚠️ 开关在这一块上，**默认关**：页③ 的钟在上面那条滑块上是显式的
 * （「切到 y = … m 为止」旁边那一路读下来，时刻一路写着），同一个数在同一屏里
 * 再说一遍不是澄清。两页共用这一块 —— 要不要这枚读数由**页**来定，
 * 不是由这一块替两页一起决定。
 */
describe('画面角上那枚时刻', () => {
  const clock = (w: ReturnType<typeof mount>) => w.find('.stage-clock')

  function withClock(props: Record<string, unknown> = {}) {
    return mount(VolumeView, {
      props: { tIndex: 12, clockTime: VOLUME.time, showClock: true, ...props },
    })
  }

  it('默认不挂 —— 页③ 的钟在滑块那一路上已经写着', async () => {
    stub()
    const w = await mountView()
    w.findComponent({ name: 'VolumeScene' }).vm.$emit('ready', true)
    await flushPromises()
    expect(clock(w).exists(), '页③ 上多出一枚时刻').toBe(false)
  })

  it('打开它：印的是**画面自己那一刻**，走 `fmtTime`', async () => {
    // 读的是载荷自己的 `time`，不是外面传进来的 `clockTime` —— 这枚读数回答的
    // 是「画面上这一屏是哪一刻」。两者错开（正在构体那一秒）时正是它最该
    // 说话的时候，而那时候载荷还是旧的，印出来的就该是旧的。
    stub()
    const w = withClock({ tIndex: 3, source: 'live', clockTime: '2026-07-23T17:40:00' })
    await flushPromises()
    expect(clock(w).text()).toBe('2026-07-23 12:00')
    expect(w.text(), '画面上印着带 T 的时间戳').not.toContain('2026-07-23T')
  })

  it('挂在**放画布的那一栏**里 —— 它是画面的一部分，不是另一边的一条元信息', async () => {
    // 用户说的是「三维影像图中的左上角/右上角」。挂到左栏或右栏去，
    // 它就成了又一条控件说明 —— 与它要替代的那张指标卡没有区别。
    stub()
    const w = withClock()
    await flushPromises()
    const stage = w.find('.vol-stage')
    expect(stage.exists(), '放画布的那一栏不在').toBe(true)
    expect(stage.find('.scene-stub').exists(), '中栏里没有画布').toBe(true)
    expect(stage.find('.stage-clock').exists(), '时刻不在放画布的那一栏里').toBe(true)
    expect(w.findAll('.vol-side .stage-clock'), '时刻跑到左栏或右栏去了').toHaveLength(0)
  })

  it('载荷还没到时什么都不印 —— 印一个空角比不印更难看', async () => {
    // `fmtTime(null)` 会拼出个坏值，而那一瞬间屏上本来就写着「正在构体…」。
    stub()
    const w = withClock()
    expect(clock(w).exists()).toBe(false)
    await flushPromises()
    expect(clock(w).text()).toBe('2026-07-23 12:00')
  })
})

/**
 * 2026-10-09 用户裁定：页⑤ 把画面上方那两行说明去掉（「这一段话也没必要
 * 展示了」）。那一屏只留温度场。
 *
 * 那两行是**两个来路**，删之前各查过一次：
 *   · 头一行是**后端给的**（载荷的 `note`，前端只负责摆上去，不重写它）；
 *   · 第二行是 `SHELL_NOTE`，它挂着规格书 §5.3「图上必须标明『棚体示意』，
 *     不允许读成『测了这么长』」。
 * 后者撤掉仍然成立，见最后那一条用例。
 *
 * ⚠️ 开关**不复用 `source`**：`source` 说的是「这份数从哪条取数口来」，
 * 而这件事说的是「这一屏要不要那几行字」。绑在一起的话，以后哪一页想换个
 * 摆法就得先动取数口 —— 与 `showClock` 同一条理由：由**页**来定。
 */
describe('画面上方那两句口径说明', () => {
  const SHELL = '拱壳按拱形截面示意'
  const NOTE = '三格共享同一个色标范围；拱外不画。'

  async function mountWith(showNotes: boolean) {
    stub(makeVolumePayload({ note: NOTE }))
    const w = mount(VolumeView, {
      props: { tIndex: 12, clockTime: VOLUME.time, showNotes },
    })
    await flushPromises()
    return w
  }

  it('开着（页③）：两句都在，`note` 是后端原话', async () => {
    const w = await mountWith(true)
    expect(w.text()).toContain(NOTE)
    expect(w.text()).toContain(SHELL)
  })

  it('关掉之后两句都不在，`测了这么长` 那句警告也跟着走', async () => {
    const w = await mountWith(false)
    expect(w.text(), '后端那句口径还在').not.toContain(NOTE)
    expect(w.text(), '壳长那句说明还在').not.toContain(SHELL)
    expect(w.text()).not.toContain('测了这么长')
  })

  it('去掉的是那两行字，不是这一块 —— 场、控件、问数一样不少', async () => {
    // 反面。只钉「两句不在」的话，把这一整块删掉也照样绿。
    const w = await mountWith(false)
    expect(w.text()).toContain('棚体三维温度场')
    expect(w.findComponent({ name: 'VolumeScene' }).exists()).toBe(true)
    expect(w.find('input[aria-label="棚体示意长度"]').exists()).toBe(true)
    expect(w.text()).toContain('查一个坐标')
  })

  it('**规格书 §5.3 那条要求由滑块自己接管**，不是跟着这两行一起没了', async () => {
    // 原文：「棚长滑块只改几何、不改场，图上必须标明『棚体示意』，
    // 不允许读成『测了这么长』。」
    // 撤掉那句长说明之后，这条要求仍然落在屏上 —— 滑块的标题就叫
    // 「棚体示意长度」，底下读数写着「只改几何，不改场」。
    // 所以页⑤ 去掉它不破规格；破了的话是**这两条断言**先红。
    const w = await mountWith(false)
    expect(w.text()).toContain('棚体示意长度')
    expect(w.text()).toContain('只改几何，不改场')
  })
})

describe('视角按钮那一组：透传', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('`showViewControls` 默认关、传了就透传给三维那一层（页③ 全靠这条不变）', async () => {
    // ⚠️ 断的是**两面**，而且这里断的是**透传**不是渲染。
    // 渲染那一面在 jsdom 里断不了：`VolumeScene` 的 `hasWebGL()` 读的是
    // `canvas.getContext('webgl2')`，jsdom 恒返回 null，所以真场景永远建不起来。
    // 于是「属性有没有走到」就成了自动测试能覆盖的全部 ——
    // 而这恰恰是最容易错的一环：`LiveView` → `VolumeView` → `VolumeScene`
    // 三处属性名里错一个，不报错、只是按钮永远不出现。
    // 页③（默认档）不被牵连，靠的就是第一半。
    const off = mount(VolumeView, { props: { tIndex: 12, clockTime: VOLUME.time } })
    await flushPromises()
    expect(
      off.findComponent({ name: 'VolumeScene' }).props('showViewControls'),
      '页③ 的默认档上这个属性不为假',
    ).toBe(false)

    const on = mount(VolumeView, {
      props: { tIndex: 12, clockTime: VOLUME.time, showViewControls: true },
    })
    await flushPromises()
    expect(
      on.findComponent({ name: 'VolumeScene' }).props('showViewControls'),
      '属性没走到三维那一层（三处名字里有一处对不上）',
    ).toBe(true)
  })
})

/**
 * 2026-10-12：页⑤ 上这一块只留**中栏**，左右两栏投进外壳的右栏
 * （`App.vue` 渲染的 `<aside id="shell-side">`）。
 *
 * ⚠️ **落点必须真的在文档里。** 字符串选择器的 Teleport 落点是在 `document`
 * 上找的：找不到时 Vue **静默不挂**（不报错、也不渲染在别处），
 * 于是右栏整块消失，而「它不该在中栏里」这一类断言照样绿。
 */
describe('页⑤ 那一档：只留中栏，侧栏投进外壳', () => {
  /** 造一个落点、返回它的引用；`document.body` 上必须有它。 */
  function provisionSide(): HTMLElement {
    const el = document.createElement('div')
    el.id = 'shell-side'
    document.body.appendChild(el)
    return el
  }

  afterEach(() => { document.getElementById('shell-side')?.remove() })

  it('查询保留在右栏，几何控制移入画布', async () => {
    stub()
    const side = provisionSide()
    const w = await mountView(12, VOLUME.time, { panels: 'shell' })

    expect(side.textContent, '右栏一块都没进去').toContain('查一个坐标')
    expect(side.textContent).not.toContain('棚体示意长度')
    expect(w.find('.vol-stage .stage-geometry-controls').text()).toContain('棚体示意长度')

    const cols = Array.from(w.find('.vol-grid').element.children) as HTMLElement[]
    expect(cols, '中栏里还留着别的栏').toHaveLength(1)
    expect(cols[0]!.classList.contains('vol-stage')).toBe(true)
  })

  it('三维视图控制在右栏，提供三种拖动模式与复位', async () => {
    stub()
    const side = provisionSide()
    await mountView(12, VOLUME.time, { panels: 'shell' })
    expect(side.textContent).toContain('三维视图控制')
    expect(side.querySelectorAll('.mode-tile')).toHaveLength(3)
    expect(side.querySelectorAll('[data-view-act="reset"]')).toHaveLength(1)
  })

  it('页③ 那一档（不传 panels）落点里一个字节都没有', async () => {
    // 反面：只断「页⑤ 的时候右栏有东西」的话，把 Teleport 写成**永远开着**
    // 也照样绿 —— 而那样页③ 的三栏就空了。
    stub()
    const side = provisionSide()
    const w = await mountView()
    expect(side.textContent, '页③ 的侧栏被投出去了').toBe('')
    expect(Array.from(w.find('.vol-grid').element.children)).toHaveLength(3)
  })
})
