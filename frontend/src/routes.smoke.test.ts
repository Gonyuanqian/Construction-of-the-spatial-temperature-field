/**
 * 每个已注册的路由都点得进去，且不抛异常。
 *
 * SPA 的路由只有真的走一遍才知道崩没崩 —— 这正是 spec §〇 里说的
 * 「框架限制消失之后要自己补回来的东西」（Streamlit 是多页重跑，
 * 一页崩了其它页不受影响；SPA 不是）。
 *
 * 这一条覆盖的是「挂载期与首次取数期」的崩溃。真浏览器的渲染
 * （canvas、CSS 布局）不在这里 —— 见计划里的 Ruling。
 *
 * 另有一条**被禁字形**的扫描（裁定 R9）：把标题、导航、两页一起渲染出来，
 * 扫渲染后的文本。但它扫到的是**渲染结果与 mock 载荷** —— mock 里
 * `checks: []`、`checks_note: ''`、`notes: []`，所以页① 与 features 由
 * **真实后端**产出的文案不经过这里。
 *
 * 分工（谁守哪一份，别让两边都以为对方在守）：
 * - **前端守这条**：标题、导航、以及页面从 mock 载荷渲染出来的文本；
 * - **后端守真实文案**：`backend/tests/test_on_screen_copy.py` 扫
 *   `/api/dataset`、`/api/dataset/timeseries`、`/api/dataset/layer-timeheight`、
 *   `/api/features` 的**真实响应体**；`test_api_train.py` 扫标定包那一份。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import App from './App.vue'
import { createAppRouter } from './router'
import { NAV_ITEMS } from './design/copy'

// EChart 在 jsdom 里没有 canvas，这里换掉它 —— 冒烟测的是路由，不是画图。
// `vi.mock` 会被提升到文件顶端，放这里与放 beforeEach 里等价；写在模块作用域
// 是让「它管整个文件」这件事一眼可见。
vi.mock('./charts/EChart.vue', () => ({
  default: { name: 'EChart', props: ['option'], template: '<div />' },
}))

/**
 * jsdom 不加载 tokens.css，而两页都要 `readPalette()`；读不到它就**抛错**
 * （这是故意的：宁可不画，也不用个错的灰）。所以挂载页面的测试必须先把令牌
 * 装进 `document.documentElement` 的内联样式里 —— 与 `App.test.ts` 的
 * `installTokens()`、`DataView.test.ts` 的 `installEnvironment()` 同一手法。
 */
function installTokens(): void {
  const root = document.documentElement
  root.style.setProperty('--paper', '#F7F6F2')
  root.style.setProperty('--ink', '#211F1C')
  root.style.setProperty('--ink-muted', '#5C5850')
  root.style.setProperty('--steel', '#DEDCD6')
  root.style.setProperty('--leaf', '#14532D')
  root.style.setProperty('--leaf-soft', '#E7EFE9')
  root.style.setProperty('--net', '#0B0F0D')
}

const PAYLOADS: Record<string, unknown> = {
  '/api/health': { status: 'ok', version: '0.1.0' },
  '/api/dataset': {
    signature: 's', file: 'f.xlsx', n_times: 1, n_columns: 1,
    time_start: 't', time_end: 't',
    sheds: { p1: 3 }, positions: [], temperature: [],
    fix: { n_rows: 1, fixed_indices: [], monotonic_before: true,
           monotonic_after: true, spacing_seconds: 300, n_gaps: 0 },
    checks: [], checks_note: '',
  },
  '/api/field/arch': {
    x_min: 0, x_max: 2.1, z_max: 1.3017, max_measured_z: 1.1,
    arch: [[0, 0.4535]], sheds: [{ id: 'p1', y: 3 }],
  },
  '/api/dataset/timeseries': {
    n_times: 0, time: [], bg_temp: [], sensors: {}, shed_mean: {},
    detrended: {}, detrended_mean: {}, detrended_domain: [-3, 3], note: '',
  },
  '/api/dataset/layer-timeheight': {
    step: 1, n_times: 0, n_columns: 0, time: [], x_label: '', source: '', sheds: {},
  },
  '/api/features': {
    default_groups: [], groups: [], all_columns: [],
    // 后端给的全列计数（Task 10 的裁定 R4）。前端不许用 `all_columns.length`
    // 自己数，所以 mock 里也必须给 —— 缺了它页面会静默渲染 `undefined`，
    // 而冒烟测试照样绿。这里与 `all_columns: []` 自洽：并集长度 0。
    n_all_columns: 0,
    notes: [],
  },
  '/api/calibration': {
    present: false, reason: '还没有标定包', created_at: null, tool_version: null,
    groups_sig: null, dataset_sig: 's', feature_groups: [], trend_kind: 'xgboost',
    tuned_keys: [], params: [], plateau: [], lz_note: null,
    metrics: [], per_point: [], ab: null, fold_kind: null, n_folds: 0,
    worst_fold: null, ab_note: '', note: '兜底参数不是最优',
  },
}

/** spec §8.5 禁的连接符与会漏成字面字符的 markdown 标记。 */
const BANNED = ['——', '**', '`', ' · ', '→', '↳'] as const

function assertCleanText(text: string, where: string): void {
  for (const bad of BANNED) {
    expect(text, `${where} 的渲染文本里出现了被禁的 ${JSON.stringify(bad)}`)
      .not.toContain(bad)
  }
}

describe('路由冒烟', () => {
  beforeEach(() => {
    installTokens()
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      // 取**最长**的匹配前缀，不是第一个命中的键。`/api/dataset` 是
      // `/api/dataset/timeseries` 与 `/api/dataset/layer-timeheight` 的前缀；
      // 用 `find` 的话后者会被前者吃掉，图表构造器里再报错，离现场很远
      // （`DataView.test.ts::stub` 的注释解释过同一个坑）。
      const hit = Object.keys(PAYLOADS)
        .filter((k) => String(url).includes(k))
        .sort((a, b) => b.length - a.length)[0]
      return new Response(JSON.stringify(hit ? PAYLOADS[hit] : {}), {
        status: hit ? 200 : 404,
        headers: { 'Content-Type': 'application/json' },
      })
    }))
  })

  for (const item of NAV_ITEMS.filter((i) => i.enabled)) {
    it(`${item.to} 点得进去，并且在页面上看得见它的标题`, async () => {
      const router = createAppRouter(createMemoryHistory())
      await router.push(item.to)
      await router.isReady()
      const w = mount(App, { global: { plugins: [router] } })
      await flushPromises()
      expect(router.currentRoute.value.path).toBe(item.to)
      expect(w.text()).toContain(item.label)
      // R9：整页渲染出来的文本必须干净 —— 两页 × 后端文案合起来扫一次。
      assertCleanText(w.text(), item.to)
    })
  }

  it('未开启的页没有路由，直接敲地址会落回页①', async () => {
    const router = createAppRouter(createMemoryHistory())
    for (const item of NAV_ITEMS.filter((i) => !i.enabled)) {
      await router.push(item.to)
      await router.isReady()
      expect(router.currentRoute.value.path).toBe('/data')
    }
  })
})
