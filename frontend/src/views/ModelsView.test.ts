import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import ModelsView from './ModelsView.vue'
import { createAppRouter } from '../router'
import { makeModelDetailPayload, makeModelsPayload } from '../test/fixtures'
import { MODELS } from '../design/copy'
import type { ModelsPayload } from '../api/types'

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
function stub(list: ModelsPayload, status = 200) {
  // 详情从**传进来的那一行**派生，不是另起一份：详情那几条用例要改
  // `rows[0].mae` 再断言屏上印「无值」—— 派生的话那个改动才跟着过去。
  const detail = { ...makeModelDetailPayload(), ...list.rows[0] }
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

  it('对不上的那一行看得见理由，而且它的「设为当前」是禁用的', async () => {
    stub(makeModelsPayload())
    const w = await mountAt('/models')
    const rows = w.findAll('tbody tr')
    const bad = rows.find((r) => r.text().includes('别人家的棚.xlsx'))!
    expect(bad.text()).toContain('数据来源不同：别人家的棚.xlsx')
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
