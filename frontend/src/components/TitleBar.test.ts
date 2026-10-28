import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import TitleBar from './TitleBar.vue'
import { createAppRouter } from '../router'
import { MODELS, SYSTEM_TITLE } from '../design/copy'

// 名字从 copy.ts 取，不在这里抄一遍 —— `guards.test.ts` 有一条守卫扫全仓，
// 标题字面量只允许出现在 copy.ts 与 index.html 两处。
function stubHealth(ok: boolean) {
  vi.stubGlobal('fetch', vi.fn(async () => (ok
    ? new Response(JSON.stringify({ status: 'ok', version: '0.1.0' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } })
    : new Response('{"detail":"后端没起"}', { status: 500 }))))
}

/**
 * 标题条现在挂着一条 `<RouterLink>`，所以每条用例都要给一个真路由。
 *
 * ⚠️ 不给的话 Vue 解析不出 `RouterLink`，按未知标签渲染并打警告 ——
 * 断言照样绿，只是从此每次跑测试都刷一遍警告。警告刷久了就没人看了，
 * 而下一个**真的**警告会淹没在里面。
 */
function withRouter() {
  return { global: { plugins: [createAppRouter(createMemoryHistory())] } }
}

// 挂载过的组件在每条用例收尾时卸掉。⚠️ 这一段是 2026-10-12 加的：本机挂钟
// 在实时那一屏上开着一个 `setInterval`，不卸载就得靠 `vi.useRealTimers()`
// 兜底 —— 卸载走 `onUnmounted` 里那条 `clearInterval`，那才是产品里的路径。
enableAutoUnmount(afterEach)

/**
 * 在某个路由上挂一枚标题条（上面那个 `withRouter()` 用的是默认的 `/`）。
 *
 * ⚠️ 提到这一层，是因为**页⑤ 精修那一段也要用它** —— 两段各抄一份的话，
 * 谁改了一处、另一处没跟上，红的会是看不懂的那一条。
 */
async function mountAt(path: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  return mount(TitleBar, { global: { plugins: [router] } })
}

describe('标题条', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('标题常驻，用的是 copy.ts 那一个名字', () => {
    stubHealth(true)
    const w = mount(TitleBar, withRouter())
    expect(w.get('header').text()).toContain(SYSTEM_TITLE)
  })

  it('后端状态在标题条上：没回来时说「检查中」，回来了报版本号', async () => {
    // 状态原先挂在侧栏底部，而 `/live` 一屏把导航收起来了 ——
    // 最需要确认「这是哪个后端」的那一屏反而看不到它（spec §5.2）。
    stubHealth(true)
    const w = mount(TitleBar, withRouter())
    expect(w.text()).toContain('检查中')
    await flushPromises()
    expect(w.text()).toContain('0.1.0')
  })

  it('后端挂了就把原话报出来，不吞成空白', async () => {
    stubHealth(false)
    const w = mount(TitleBar, withRouter())
    await flushPromises()
    expect(w.text()).toContain('后端没起')
  })

  it('标题排在中间那一格、状态在右格 —— 居中靠栅格，不靠 flex', () => {
    // 右端有状态在，用 flex 居中会被它推偏。形状钉在栅格列号上。
    stubHealth(true)
    const w = mount(TitleBar, withRouter())
    // 用 `find` 而不是 `get`：`get` 的返回类型把 `exists` 从签名里去掉了
    // （它本身就保证存在，`exists()` 恒真），`vue-tsc` 会报 TS2339。
    expect(w.find('h1').exists()).toBe(true)
    expect(w.find('.backend').exists()).toBe(true)
  })

  it('实时顶栏保留模型库快捷入口，训练顶栏使用导航入口', async () => {
    stubHealth(true)
    const w = await mountAt('/live')
    const link = w.get('a.to-models')
    expect(link.attributes('href')).toBe('/models')
    // ⚠️ 断言的是**可访问名**，不是渲染文本：图标对读屏是隐形的
    // （`aria-hidden="true"`），名字挂在链接的 `aria-label` 上 —— 而
    // `wrapper.text()` **读不到 `aria-label`**。写成
    // `expect(w.text()).toContain(MODELS.entry)` 是一条永远红的断言。
    expect(link.attributes('aria-label')).toBe(MODELS.entry)
    const train = await mountAt('/data')
    expect(train.find('a.to-models').exists()).toBe(false)
  })

  it('图标画的是形状，用 currentColor 上色', async () => {
    // 十六进制色只许出现在 tokens.css 与 charts/scale.ts（`guards.test.ts`
    // 那条全仓守卫）。图标走 `currentColor` 就意味着页面上换主题它跟着换。
    stubHealth(true)
    const w = await mountAt('/live')
    const svg = w.get('a.to-models svg')
    expect(svg.attributes('stroke')).toBe('currentColor')
    expect(svg.attributes('aria-hidden')).toBe('true')
  })
})

/**
 * 本机挂钟与正常状态点（2026-10-12 页⑤ 仪表盘）。
 *
 * ⚠️ **这一段是加在已有的六条后面的，不是另起一个文件**：计划 Step 1 把它写成
 * 「新建 `frontend/src/components/TitleBar.test.ts`」—— 而那个文件早就在了
 * （标题、后端状态、图标那六条）。照字面新建会把那六条连同它们守着的形状
 * 一起删掉，而删掉之后**一条都不会红**。
 *
 * ⚠️ **定时器必须用假时钟**（`vi.useFakeTimers`）：真时钟下这条用例的结果
 * 取决于跑它的那一分钟，而从「过了一分钟它就变了」这个角度说，
 * 它是**偶尔**绿 —— 那比红更坏。
 */
describe('本机挂钟与状态点', () => {
  beforeEach(() => { vi.restoreAllMocks(); stubHealth(true) })
  afterEach(() => { vi.useRealTimers() })

  it('只在实时那一屏上，且走的是**本机时区**', async () => {
    // ⚠️ 这条断的正是最容易写错的一处：`new Date().toISOString()` 是 **UTC**，
    // 在东八区会把上午十点印成凌晨两点。本仓要的是「本机的时间」（用户原话）。
    // 造一个本地时刻，再断言屏上印的就是它的本地时分。
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    const at = new Date(2026, 9, 12, 14, 5, 0)      // 本机 2026-10-12 14:05
    vi.setSystemTime(at)

    const w = await mountAt('/live')
    await flushPromises()
    expect(w.text(), '实时那一屏没有本机时间').toContain('14:05')
  })

  it('训练侧那四页上没有它', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date(2026, 9, 12, 14, 5, 0))
    const w = await mountAt('/data')
    await flushPromises()
    expect(w.text(), '训练侧也挂上了挂钟 —— 那是四页一起改').not.toContain('14:05')
  })

  it('过一分钟它跟着走', async () => {
    // 反面：「只在挂载时算一次」也满足上面两条。这一条把它挡住。
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(new Date(2026, 9, 12, 14, 5, 0))
    const w = await mountAt('/live')
    await flushPromises()
    vi.setSystemTime(new Date(2026, 9, 12, 14, 6, 0))
    await vi.advanceTimersByTimeAsync(2000)
    expect(w.text()).toContain('14:06')
  })

  it('实时那一屏上正常时有一枚点，训练侧没有', async () => {
    // 参考图上顶栏右上角那枚绿点说的是「系统运行正常」。
    // ⚠️ **只在实时那一屏**：加在训练侧就是四页一起改（本轮不许）。
    const live = await mountAt('/live')
    await flushPromises()
    // ⚠️ 2026-10-16 精修：那一簇改成「一枚点 + 一句话」，那枚点的类名由
    // `.ok` 换成 `.dot`（亮不亮由外层的 `.status.ok` 说）。钉的东西没变：
    // 实时那一屏上有这枚点、训练侧没有。
    expect(live.find('.dot').exists(), '实时那一屏没有状态点').toBe(true)

    const train = await mountAt('/data')
    await flushPromises()
    expect(train.find('.dot').exists(), '训练侧也多了个点').toBe(false)
  })
})

/**
 * 页⑤ 精修：标题条（2026-10-16 用户发来的第一部分要求）。
 *
 * ⚠️ 这一段断的全是**结构**：有没有那枚图标、`live` 这个类挂上没有、
 * 那句话在不在。「底部那条发光的青线」与「顶部那道折角」是纯装饰 ——
 * jsdom 不做样式计算，看不见它们。它们由 `design/liveShell.test.ts`
 * 那份读源码的守卫钉着，与 `shell.test.ts` 同一个做法、同一个代价：
 * 钉的是**写法**，不是效果。
 */
describe('页⑤ 精修：标题条', () => {
  beforeEach(() => { vi.restoreAllMocks(); stubHealth(true) })

  it('两种模式各自显示对应的叶片标识', async () => {
    const live = await mountAt('/live')
    await flushPromises()
    expect(live.find('.live-leaf').exists(), '实时那一屏没画叶片').toBe(true)

    const train = await mountAt('/data')
    await flushPromises()
    expect(train.find('.brand-mark .icon').exists()).toBe(true)
    expect(train.find('.live-leaf').exists()).toBe(false)
  })

  it('`live` 这个类只挂在实时那一屏的标题条上', async () => {
    // 这一轮的新样式**全部**挂在它底下。类漏挂了，屏上是「一处都没变」，
    // 而一条断言都不会红 —— 所以先钉住这个总闸。
    const live = await mountAt('/live')
    await flushPromises()
    expect(live.get('header').classes(), '实时那一屏的标题条没挂 live').toContain('live')

    const train = await mountAt('/data')
    await flushPromises()
    expect(train.get('header').classes(), '训练侧的标题条也挂上了 live').not.toContain('live')
  })

  it('状态合成一条：接上了说「前后端已连接」，并亮起那枚点', async () => {
    // 用户 2026-10-16：「这个状态应该以前后端服务有没有成功连接上来判断」。
    // 要求里的「后端连接状态」与「数据服务运行状态」是**一条**（当场裁定 R2）——
    // 判据只有一个（能不能连上），拆成两行是在同一句话旁边写第二遍。
    const live = await mountAt('/live')
    await flushPromises()
    expect(live.text()).toContain('前后端已连接')
    expect(live.find('.status.ok').exists(), '接上了那枚点却没亮').toBe(true)
  })

  it('还没回来时说「检查中」，点不亮', async () => {
    const live = await mountAt('/live')
    expect(live.text()).toContain('检查中')
    expect(live.find('.status.ok').exists()).toBe(false)
    await flushPromises()
  })

  it('连不上就把后端的原话报出来 —— 不吞成一句「异常」', async () => {
    stubHealth(false)
    const live = await mountAt('/live')
    await flushPromises()
    expect(live.text()).toContain('后端没起')
    expect(live.find('.status.bad').exists()).toBe(true)
  })

  it('实时那一屏上不再挂库版本号', async () => {
    // 用户 2026-10-16：「这个后面挂着的『库版本 0.1.0』可以撤掉了」。
    // ⚠️ 撤的只是**实时那一屏**：训练侧那四页那一行照旧（浅色档是深绿铭牌、
    // 版式也没动），所以这一条只在 /live 上断。
    const live = await mountAt('/live')
    await flushPromises()
    expect(live.text()).not.toContain('0.1.0')
  })
})
