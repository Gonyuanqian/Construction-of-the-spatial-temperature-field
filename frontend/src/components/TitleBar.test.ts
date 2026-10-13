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

  it('模型库的入口是标题条右边一个图标，不是左导航里的一项', () => {
    // 用户 2026-10-08 指定的入口位置。左导航那一列有测试钉着「<a> 的数量与
    // 次序**精确等于**已开放项」（App.test.ts:83-90），所以模型库不能挤进去。
    stubHealth(true)
    const w = mount(TitleBar, withRouter())
    const link = w.get('a.to-models')
    expect(link.attributes('href')).toBe('/models')
    // ⚠️ 断言的是**可访问名**，不是渲染文本：图标对读屏是隐形的
    // （`aria-hidden="true"`），名字挂在链接的 `aria-label` 上 —— 而
    // `wrapper.text()` **读不到 `aria-label`**。写成
    // `expect(w.text()).toContain(MODELS.entry)` 是一条永远红的断言。
    expect(link.attributes('aria-label')).toBe(MODELS.entry)
  })

  it('图标画的是形状，用 currentColor 上色', () => {
    // 十六进制色只许出现在 tokens.css 与 charts/scale.ts（`guards.test.ts`
    // 那条全仓守卫）。图标走 `currentColor` 就意味着页面上换主题它跟着换。
    stubHealth(true)
    const w = mount(TitleBar, withRouter())
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

  /** 在某个路由上挂一枚标题条（上面那个 `withRouter()` 用的是默认的 `/`）。 */
  async function mountAt(path: string) {
    const router = createAppRouter(createMemoryHistory())
    await router.push(path)
    return mount(TitleBar, { global: { plugins: [router] } })
  }

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
    expect(live.find('.ok').exists(), '实时那一屏没有状态点').toBe(true)

    const train = await mountAt('/data')
    await flushPromises()
    expect(train.find('.ok').exists(), '训练侧也多了个点').toBe(false)
  })
})
