import { describe, expect, it, vi, beforeEach } from 'vitest'

import { useDataset } from './useDataset'

const DS = { signature: 's', file: 'f.xlsx' }

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
    d.onImported()
    expect(d.state.value).toBe('ok')
    expect(d.version.value).toBe(before + 1)
  })
})
