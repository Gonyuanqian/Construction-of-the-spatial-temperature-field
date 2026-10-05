import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import { makeVolumePayload } from '../test/fixtures'

// **Three 不进测试。** 这一块画的那一半在 `VolumeScene.test.ts` 里单独测，
// 而这里测的是取数、判定、文案、防抖 —— 全都与 WebGL 无关。
vi.mock('./VolumeScene.vue', () => ({
  default: {
    name: 'VolumeScene',
    props: ['spec', 'payload', 'picked'],
    emits: ['hover', 'pick'],
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

async function mountView(tIndex = 12, clockTime = VOLUME.time) {
  const w = mount(VolumeView, { props: { tIndex, clockTime } })
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

  it('一挂上就去取这一卷，参数只带 t_index（其余走后端默认）', async () => {
    const urls = stub()
    await mountView()
    expect(urls).toHaveLength(1)
    expect(urls[0]).toContain('/api/field/volume')
    expect(urls[0]).toContain('t_index=12')
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
    expect(w.text()).toContain(VOLUME.time)
    release()
    await flushPromises()
    expect(w.text()).not.toContain('正在构体')
  })

  it('画面还停在上一刻而时钟已经走了时，明说这件事', async () => {
    stub()
    const w = await mountView(12, '2026-07-23T17:40:00')
    expect(w.text()).toContain('画面仍是')
    expect(w.text()).toContain(VOLUME.time)
    expect(w.text()).toContain('2026-07-23T17:40:00')
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
    expect(table.text()).toContain(VOLUME.time)
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
    expect(t.text()).toContain('已钉住')
  })

  it('取消钉住之后读数跟着鼠标走', async () => {
    stub()
    const w = await mountView()
    const scene = w.findComponent({ name: 'VolumeScene' })
    scene.vm.$emit('hover', { planeIndex: 0, ix: 1, iz: 1 })
    scene.vm.$emit('pick', { planeIndex: 0, ix: 1, iz: 1 })
    await flushPromises()
    const btn = w.findAll('button').find((b) => b.text().includes('取消钉住'))
    expect(btn, '取消钉住按钮不在').toBeTruthy()
    await btn!.trigger('click')
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
        planes: [{ y: 3, measured: true, shed: 'p1', values: [[1, 2], [3, 4]] }],
        stripes: [],
      })
      return new Response(JSON.stringify(small), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })
    }))
    await w.setProps({ tIndex: 13 })
    await new Promise((r) => setTimeout(r, 400))
    await flushPromises()
    expect(w.find('table').exists(), '越界的钉住没被放掉').toBe(false)
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

  it('**坐标查询要写出吸附之后的坐标，不插值**', async () => {
    // 用户输的是 5.4、拿到的是 5.5 的值，不写出来就是撒谎。
    stub()
    const w = await mountView()
    // 先悬停一次：不悬停的话读数表不渲染，查询表就是第 0 张 ——
    // 而下面按 `[1]` 取，取的是「查询那一张」这件事才有意义。
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
    const note = '三格共享同一个色标范围；拱外不画。'
    stub(makeVolumePayload({ note }))
    const w = await mountView()
    expect(w.text()).toContain('示意')
    expect(w.text()).toContain(note)
  })
})
