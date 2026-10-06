import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useDataset } from './useDataset'
import type { UploadResult } from '../api/types'

const DS = { signature: 's', file: 'f.xlsx' }

const RESULT: UploadResult = {
  signature: '新', file: '人参棚 副本.xlsx', n_times: 1308, n_columns: 52,
  time_start: '2026-07-23T11:00:00', time_end: '2026-07-27T23:55:00',
}

function stub(status: number, body: unknown = {}) {
  vi.stubGlobal('fetch', vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status, headers: { 'Content-Type': 'application/json' },
    })))
}

describe('useDataset', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // 单例：每条用例先把状态打回起点，否则上一条的结果留给下一条。
    useDataset().reset()
  })

  it('409 是「还没导入」，不是出错', async () => {
    stub(409, { detail: '还没有导入数据集。' })
    const d = useDataset()
    await d.probe()
    expect(d.state.value).toBe('missing')
  })

  it('200 是在用数据集', async () => {
    stub(200, DS)
    const d = useDataset()
    await d.probe()
    expect(d.state.value).toBe('ok')
  })

  it('后端挂了不算空态 —— 500 与 409 是两种处境', async () => {
    // 把「出错了」说成「你还没开始」会让用户去干一件没用的事（导一份数据集），
    // 而真正的问题是后端没起来。这一条守的就是这个分家。
    stub(500, { detail: '内部错误' })
    const d = useDataset()
    await d.probe()
    expect(d.state.value).toBe('error')
    expect(d.state.value).not.toBe('missing')
  })

  it('连不上后端（status 0）也不算空态', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const d = useDataset()
    await d.probe()
    expect(d.state.value).toBe('error')
  })

  it('导入成功把状态直接置为在用，并让版本号前进一格', async () => {
    // 导入已经成功 = 数据集一定在用，不必再问一次（省一条请求）。
    stub(409, { detail: '还没有导入数据集。' })
    const d = useDataset()
    await d.probe()
    expect(d.state.value).toBe('missing')

    const before = d.version.value
    d.onImported(RESULT)
    expect(d.state.value).toBe('ok')
    expect(d.version.value).toBe(before + 1)
  })

  it('导入摘要存在单例里 —— 外壳重挂载之后它还在', async () => {
    // ⚠️ **这正是这一条存在的理由**：`onImported` 会 +1 版本号，而版本号
    // 绑在 `App.vue` 的 `<RouterView :key>` 上 —— 页① 当场被卸掉再挂一次。
    // 摘要是搁在组件里的 `ref`，那一行「当前数据集：…」会**在写上去的同
    // 一瞬间被自己的重挂载抹掉**，而只看 `DataView` 的测试（没有 RouterView）
    // 看不见这件事。
    //
    // 所以摘要必须和 `version` 住在同一个单例里：跨组件实例活得下去。
    const d = useDataset()
    expect(d.lastImport.value).toBeNull()
    d.onImported(RESULT)
    expect(d.lastImport.value).toEqual(RESULT)
  })

  it('reset 把摘要也清掉 —— 否则下一条用例继承上一条的', () => {
    const d = useDataset()
    d.onImported(RESULT)
    d.reset()
    expect(d.lastImport.value).toBeNull()
  })
})
