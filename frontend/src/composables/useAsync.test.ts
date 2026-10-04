import { describe, expect, it } from 'vitest'
import { useAsync } from './useAsync'

describe('useAsync', () => {
  it('成功后 data 有值、error 为空、loading 归位', async () => {
    const { data, error, loading, run } = useAsync(async () => 42)
    expect(loading.value).toBe(false)
    await run()
    expect(data.value).toBe(42)
    expect(error.value).toBe('')
    expect(loading.value).toBe(false)
  })

  it('把 ApiError 的 message 原样透出，不吞成 "Error"', async () => {
    const { error, data, run } = useAsync(async () => {
      throw new Error('数据集不存在：C:/x.xlsx')
    })
    await run()
    expect(error.value).toBe('数据集不存在：C:/x.xlsx')
    expect(data.value).toBeNull()
  })

  it('重跑会先清掉上一次的错', async () => {
    let fail = true
    const { error, run } = useAsync(async () => {
      if (fail) throw new Error('第一次失败')
      return 1
    })
    await run()
    expect(error.value).toBe('第一次失败')
    fail = false
    await run()
    expect(error.value).toBe('')
  })

  it('两次并发只留最后一次的结果（防止旧响应盖掉新的）', async () => {
    const seq: Array<(v: number) => void> = []
    const { data, run } = useAsync(() => new Promise<number>((res) => seq.push(res)))
    const a = run()
    const b = run()
    seq[1](2)      // 第二次先回来
    seq[0](1)      // 第一次后回来 —— 不许它盖掉
    await Promise.all([a, b])
    expect(data.value).toBe(2)
  })
})
