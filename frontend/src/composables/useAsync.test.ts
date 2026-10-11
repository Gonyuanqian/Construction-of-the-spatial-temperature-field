import { describe, expect, it } from 'vitest'
import { useAsync } from './useAsync'
import { ApiError } from '../api/client'

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

  it('把状态码带出来 —— 页① 要拿它把「还没导入」与「出错了」分开', async () => {
    // `error` 只有一个字符串，`409` 与 `500` 在它眼里长得一样。而这两种错
    // 必须分得开：把 500 说成「你还没开始」，会让用户去导一份数据集来解决
    // 一个后端没起来的问题（规格书 §二.1）。
    const { status, run } = useAsync(async () => {
      throw new ApiError('还没有导入数据集。', 409)
    })
    expect(status.value).toBe(0)
    await run()
    expect(status.value).toBe(409)
  })

  it('不是 ApiError 的错，状态码是 0（不是某个 HTTP 码）', async () => {
    // `0` 是本仓 `ApiError` 表示「连不上」的那个值，这里再借它一次表示
    // 「这个错压根没有状态码」。**不能借 409** —— 那会让一个连不上的错
    // 被当成空态。
    const { status, run } = useAsync(async () => { throw new Error('连不上后端') })
    await run()
    expect(status.value).toBe(0)
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
