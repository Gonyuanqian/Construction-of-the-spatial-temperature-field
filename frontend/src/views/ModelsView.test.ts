import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import ModelsView from './ModelsView.vue'
import { createAppRouter } from '../router'
import { makeModelDetailPayload, makeModelsPayload } from '../test/fixtures'
import { BORROWED, MODELS } from '../design/copy'
import type { ModelDetailPayload, ModelsPayload } from '../api/types'

enableAutoUnmount(afterEach)

/**
 * 令牌一次性装好。⚠️ 逐字照 `routes.smoke.test.ts` 那一份 ——
 * jsdom 不加载 tokens.css，而 `readPalette()` 读不到就**抛**（故意如此：
 * 宁可不画，也不用个错的灰）。漏一个令牌的表现是这一页挂载中途抛，
 * 报错离「少了一个令牌」很远。
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
  root.style.setProperty('--layer-top', '#C44E52')
  root.style.setProperty('--layer-mid', '#4C72B0')
  root.style.setProperty('--layer-low', '#55A868')
  root.style.setProperty('--bar', '#D98C2B')
  root.style.setProperty('--size-chart-axis', '12px')
  root.style.setProperty('--size-chart-title', '14px')
}

/**
 * 按 URL 分派三条：设为当前、详情、列表。
 *
 * ⚠️ 详情那一支**从 Task 8 起才用得上，但这里就要写**：`/api/models/1`
 * 是 `/api/models` 的前缀，只按 `includes('/api/models')` 认的话，
 * 详情那一条会拿到列表载荷去当详情解，而报错是「读不到某个字段」。
 */
function stub(list: ModelsPayload, status = 200,
              over: Partial<ModelDetailPayload> = {}) {
  // 详情从**传进来的那一行**派生，不是另起一份：这样改 `rows[0]` 里那几个
  // 列表字段（名字、时间、指纹）才跟着过到详情上。
  // `over` 是给详情**独有**的那几格用的（`metrics` / `ab` / `plateau`），
  // 列表行里根本没有它们。
  const detail = { ...makeModelDetailPayload(), ...list.rows[0], ...over }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const u = String(url)
    const body = u.includes('/current') ? { id: 1, is_current: true }
      : /\/api\/models\/\d+/.test(u) ? detail
      : list
    return new Response(
      JSON.stringify(status === 200 ? body : { detail: '数据库连不上' }),
      { status, headers: { 'Content-Type': 'application/json' } })
  }))
}

async function mountAt(path: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  const w = mount(ModelsView, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('模型库列表', () => {
  beforeEach(() => { installTokens(); vi.restoreAllMocks() })

  it('五列齐全，表头按用户点名的那四个字段排', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const head = w.get('table thead').text()
    for (const col of ['模型的名字', '数据来源', 'ID', '动作']) {
      expect(head).toContain(col)
    }
    // 效果那一列的表头必须带折族与组 —— 不带，三个小数会被读成通用分
    expect(head).toContain('空间折')
    expect(head).toContain('B 组')
  })

  it('数据来源印的是文件名与训练段的起止', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const body = w.get('table tbody').text()
    expect(body).toContain('人参棚_原始.xlsx')
    expect(body).toContain('2026-07-23')
  })

  it('当前那一行有标记，而且只有它一个', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const marked = w.findAll('tr.is-current')
    expect(marked).toHaveLength(1)
    expect(marked[0].text()).toContain('七月下旬那套')
  })

  it('借来的那一行能用，而且标着「借来的」', async () => {
    // ⭐ 2026-10-10 用户裁定「模型不绑数据集」：库里的模型**不按数据集绑**，
    // 借来的那一份照样能设为当前。⚠️ 这一条与下面那条是一对 —— 少了它，
    // 把 `compatible` 改回「两轴都对得上」不会有任何测试红。
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const row = w.findAll('tbody tr').find((r) => r.text().includes('上一份数据训的'))!
    expect(row.text()).toContain(BORROWED)
    const btn = row.findAll('button').find((b) => b.text() === MODELS.setCurrent)!
    expect(btn.attributes('disabled'), '借来的那一行设不了当前').toBeUndefined()
  })

  it('对不上的那一行看得见理由，而且它的「设为当前」是禁用的', async () => {
    // ⚠️ 这原来是**第二行**（数据集对不上）在演。改档之后第二行能用了，
    // 这个角色换到第三行（特征组对不上）—— 它是三档里唯一真的用不了的一种。
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const bad = w.findAll('tbody tr')
      .find((r) => r.text().includes('另一个特征组标的'))!
    expect(bad.text()).toContain('这一份是用别的特征组标出来的')
    const btn = bad.findAll('button').find((b) => b.text() === MODELS.setCurrent)!
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('空库时说的是「还没有模型」，不是一片空白', async () => {
    stub({ rows: [], current_id: null, dataset_file: 'f.xlsx', dataset_sig: 'a' })
    const w = await mountAt('/models')
    expect(w.text()).toContain(MODELS.empty)
    expect(w.text()).toContain(MODELS.emptyWhy)
  })

  it('取数失败时把后端那句话印出来，不吞掉', async () => {
    // ⚠️ 尤其是**数据库连不上**：一个空的列表会让人以为模型丢了，
    // 而去重训一遍；而真相是那个服务没起来。
    stub(makeModelsPayload(), 500)
    const w = await mountAt('/models')
    expect(w.text()).toContain('数据库连不上')
  })

  it('名字里的尖括号被当字面量渲染，不当标签', async () => {
    // 名字是用户输入的。Vue 的 {{ }} 默认转义，这条钉的是「没人把它
    // 换成 v-html」—— 换过去就是一个存进库里的 XSS。
    const p = makeModelsPayload()
    p.rows[0].name = '<img src=x onerror=alert(1)>'
    stub(p)
    const w = await mountAt('/models')
    expect(w.find('img').exists()).toBe(false)
    expect(w.text()).toContain('<img src=x')
  })
})

describe('模型库详情', () => {
  beforeEach(() => { installTokens(); vi.restoreAllMocks() })

  it('两个时间分开印，各用各的词', async () => {
    // ⚠️ 规格书 §6.1 单列一条：`saved_at` 是**用户点保存**的时刻，包里那个
    // `created_at` 是**标定跑完**的时刻。平时只差几秒 —— 印反了没人看得出来，
    // 而「这个模型是哪天定的」正是详情页要回答的事之一。
    stub(makeModelsPayload())
    const w = await mountAt('/models/1')
    const text = w.text()
    expect(text).toContain('保存于')
    expect(text).toContain('2026-10-08 09:12')
    expect(text).toContain('标定于')
    expect(text).toContain('2026-10-08 09:12')     // created_at 那一份在载荷里
    expect(text).not.toContain('保存于 2026-10-08T09:12:28')  // 不许把 created_at 印成保存时刻
  })

  it('参数、特征组、被调过的键都在', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models/1')
    const text = w.text()
    expect(text).toContain('coord')
    for (const k of ['metric.power', 'trend.max_depth']) expect(text).toContain(k)
  })

  it('从详情回到列表会重新取列表 —— 不是一片空白', async () => {
    // ⭐ 终审 Important 3。两条路由共用这一个组件实例（`App.vue` 的
    // `<RouterView :key="dataset.version…">` 在路由切换时 key 不变，实例被
    // 复用、不会重新 mount），于是从 `/models/1` 回到 `/models` 时
    // `onMounted` 不再跑。只接「进详情」那一半的话，`models.data` 停在
    // `null`，列表那三个 `v-else-if` 全不成立，屏上只剩标题 —— 本仓最怕的
    // 那种白屏：不报错，也不说为什么。在详情地址上直接刷新浏览器、再点
    // 「回模型库」，走的就是这条路。
    stub(makeModelsPayload())
    const router = createAppRouter(createMemoryHistory())
    await router.push('/models/1')
    await router.isReady()
    const w = mount(ModelsView, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.text()).toContain('保存于')              // 前提：确实在详情态

    await router.push('/models')
    await flushPromises()

    expect(w.get('table thead').text()).toContain('模型的名字')
    expect(w.text()).not.toContain('保存于')
  })

  it('A/B 分开印，而且 gap 说的是「调参带来的乐观偏差」', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models/1')
    const text = w.text()
    expect(text).toContain('A 组（参与选参）')
    expect(text).toContain('B 组（未参与选参）')
    expect(text).toContain('调参带来的乐观偏差')
  })

  it('逐折指标表按区域与组分开，一列都不少', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models/1')
    const head = w.get('table').text()
    for (const col of ['折', '区域', '组', 'MAE', 'RMSE', 'R²']) {
      expect(head).toContain(col)
    }
  })

  it('没有逐测点表 —— 用户刚把页② 那张撤掉，这里再摆一张是同一个东西', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models/1')
    // 载荷里本来就没有 per_point；这条钉的是「没人又加回去」。
    expect(w.text()).not.toContain('逐点')
  })

  it('指标算不出来时印「无值」，不印 NaN', async () => {
    // ⚠️ 报的必须是**详情那一份**载荷。详情表那几行来自
    // `makeModelDetailPayload()`，而 `rows[0].mae` 是**列表那一列**的 B 组
    // 均值（`report_metrics` 就是 B 组均值，与 `ab.mae_b` 同一个数）——
    // 改列表行够不到详情表，而把那三个数搬到详情上又是同一个数印两遍。
    stub(makeModelsPayload(), 200, {
      metrics: [{
        fold: 'position:x0.15_z0.4', fold_kind: 'position', region: '切面内',
        group: 'B', tag: '报告组', n: 1308, mae: null, rmse: null, r2: null,
      }],
    })
    const w = await mountAt('/models/1')
    expect(w.text()).toContain('无值')
    expect(w.text()).not.toContain('NaN')
  })
})

describe('没有成品的那一行（规格书 D6/D7、§七）', () => {
  beforeEach(() => { installTokens(); vi.restoreAllMocks() })

  /** 在三条基线后面再补一行「有成品但没固化」的。 */
  function withNotSolid(p: ModelsPayload): ModelsPayload {
    p.rows.push({
      ...p.rows[0], id: 9, name: '刚存进来还没固化的一份',
      is_current: false, compatible: true, borrowed: false,
      has_artifact: false, why: '',
    })
    return p
  }

  it('盖「未固化」，并说清选中之后会现训一遍', async () => {
    stub(withNotSolid(makeModelsPayload()))
    const w = await mountAt('/models')
    const row = w.findAll('tbody tr')
      .find((r) => r.text().includes('刚存进来还没固化的一份'))!
    // ⚠️ 「未固化」是**图章上那三个字**，与 `why` 是两件事：
    //     `why` 是**后端**给的理由，那句话前端不另写。
    expect(row.text()).toContain(MODELS.notSolid)
    expect(row.text()).toContain(MODELS.notSolidWhy)
  })

  it('有成品的那一行不盖「未固化」', async () => {
    // 上面那条的反面。少了它，一个「永远盖未固化」的实现照样全绿 ——
    // 而它会让库里每一份模型都声称自己没固化。
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const row = w.findAll('tbody tr')
      .find((r) => r.text().includes('七月下旬那套'))!
    expect(row.text()).not.toContain(MODELS.notSolid)
  })

  it('用不了的那一行只印后端那句 why，不再叠一句「没成品」', async () => {
    // ⚠️ 两条理由会打架：`compatible: false` 时后端那句 `why` 已经说清了
    // 为什么不能选，再叠一句「这一条还没有成品」是把同一件事说两遍。
    // 所以那一句只在 `compatible` 为真、单单缺成品时出现。
    const p = makeModelsPayload()
    p.rows[2] = { ...p.rows[2], has_artifact: false }
    stub(p)
    const w = await mountAt('/models')
    const row = w.findAll('tbody tr')
      .find((r) => r.text().includes('另一个特征组标的'))!
    expect(row.text()).toContain('这一份是用别的特征组标出来的')
    expect(row.text()).toContain(MODELS.notSolid)          // 图章照盖：那是事实
    expect(row.text()).not.toContain(MODELS.notSolidWhy)   // 解释只留一句
  })

  it('没有数据集时，那一句 why 是后端给的，前端逐字印它', async () => {
    const p = makeModelsPayload()
    p.dataset_file = null
    p.dataset_sig = null
    p.rows[0] = {
      ...p.rows[0], compatible: false,
      why: '这一条还没有成品，先导入数据集才能用',
    }
    stub(p)
    const w = await mountAt('/models')
    expect(w.text()).toContain('这一条还没有成品，先导入数据集才能用')
  })
})
