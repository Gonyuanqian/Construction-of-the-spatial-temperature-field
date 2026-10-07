import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import { useJob } from './useJob'
import type { JobSummary } from '../api/types'

/** 一个能一次一次给答案的替身：第 n 次调用给第 n 个回包，用完了给最后一个。 */
function stubSequence(answers: unknown[]) {
  let i = 0
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    calls.push(String(url))
    const body = answers[Math.min(i, answers.length - 1)]
    i += 1
    return new Response(JSON.stringify(body), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })
  }))
  return calls
}

const RUNNING: JobSummary = { id: 'j1', state: 'running', progress: '阶段 2 试验之间',
                  elapsed_s: 3.2, error: null, created_at: '2026-10-07T10:00:00+00:00' }
const DONE: JobSummary = { ...RUNNING, state: 'done', progress: '', elapsed_s: 41.7 }

describe('useJob 轮询', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('轮询会在 job 结束时停下来，不会再发请求', async () => {
    // T18 的前半：定时器停不下来 = 界面背后永远每秒发一条请求。
    const calls = stubSequence([RUNNING, DONE])
    const j = useJob()
    j.attach('j1')
    await flushPromises()
    expect(j.job.value?.state).toBe('running')

    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(j.job.value?.state).toBe('done')
    expect(j.polling.value).toBe(false)

    const n = calls.length
    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()
    expect(calls.length, '停下来了还在发请求').toBe(n)
  })

  it('停了之后 stop 不会再让它自己活过来', async () => {
    stubSequence([RUNNING])
    const j = useJob()
    j.attach('j1')
    await flushPromises()
    const n = Number(vi.getTimerCount())
    expect(n).toBeGreaterThan(0)
    j.stop()
    expect(vi.getTimerCount()).toBe(0)
    expect(j.polling.value).toBe(false)
  })

  it('轮询失败不当作任务失败 —— 报出来，但接着问', async () => {
    // 网络抖一下不代表那一次算完了。停下定时器会让界面永远停在「正在优选…」。
    let i = 0
    vi.stubGlobal('fetch', vi.fn(async () => {
      i += 1
      if (i === 1) return new Response(JSON.stringify(RUNNING), { status: 200 })
      if (i === 2) return new Response(JSON.stringify({ detail: '连接被重置' }), { status: 500 })
      return new Response(JSON.stringify(DONE), { status: 200 })
    }))
    const j = useJob()
    j.attach('j1')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(j.error.value).toContain('连接被重置')
    expect(j.job.value?.state, 'job 的状态不许被一次网络抖动改掉').toBe('running')
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(j.job.value?.state).toBe('done')
  })

  it('attach 会换 id，旧的轮询作废', async () => {
    const calls = stubSequence([RUNNING])
    const j = useJob()
    j.attach('j1')
    await flushPromises()
    j.attach('j2')
    await flushPromises()
    expect(calls.some((u) => u.includes('/jobs/j2'))).toBe(true)
    expect(calls.filter((u) => u.includes('/jobs/j1')).length).toBe(1)
    j.stop()
  })

  it('attachFrom 只接管还在跑的那个', async () => {
    const calls = stubSequence([RUNNING])
    const j = useJob()
    j.attachFrom({ ...DONE, id: 'j9' })
    await flushPromises()
    expect(calls.length, '已经结束的 job 不该被接管').toBe(0)
    expect(j.job.value?.id).toBe('j9')

    j.attachFrom({ ...RUNNING, id: 'j10' })
    await flushPromises()
    expect(calls.some((u) => u.includes('/jobs/j10'))).toBe(true)
    j.stop()
  })

  it('attachFrom(null) 什么都不做', async () => {
    const calls = stubSequence([RUNNING])
    const j = useJob()
    j.attachFrom(null)
    await flushPromises()
    expect(calls.length).toBe(0)
    expect(j.job.value).toBeNull()
  })

  it('取消之后**不自己改成 cancelled** —— 让后端说', async () => {
    // 提前改的话，界面会在盘的写回还没停下来的那一刻说「已取消」，
    // 而验收 3 要的正是「取消之后盘上逐位没变」。
    const calls = stubSequence([RUNNING, RUNNING, { ...RUNNING, state: 'cancelled' }])
    const j = useJob()
    j.attach('j1')
    await flushPromises()
    await j.cancel()
    await flushPromises()
    expect(j.job.value?.state, '取消的当下不许自称已取消').toBe('running')
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(j.job.value?.state).toBe('cancelled')
    expect(calls.some((u) => u.includes('/jobs/j1'))).toBe(true)
  })

  it('start 遇到 409 时切去轮询已经在跑的那个', async () => {
    // §4.5：第二次 POST 指路。前端据此接着盯**正在跑的那一个**，不报错。
    // id 从 `GET /api/calibration` 的 `job` 字段读 —— 与「刷新之后接上」
    // 是同一条路，一条路比两条可靠。
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      urls.push(`${init?.method ?? 'GET'} ${url}`)
      if (String(url).endsWith('/api/calibration/jobs')) {
        return new Response(JSON.stringify({ detail: '已经有一次标定在跑', job_id: 'j7' }),
                            { status: 409, headers: { 'Content-Type': 'application/json' } })
      }
      if (String(url).endsWith('/api/calibration')) {
        return new Response(JSON.stringify({ present: true, job: { ...RUNNING, id: 'j7' } }),
                            { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(JSON.stringify({ ...RUNNING, id: 'j7' }), { status: 200 })
    }))
    const j = useJob()
    await j.start()
    await flushPromises()
    expect(j.error.value, '409 不是失败').toBe('')
    expect(urls).toContain('POST /api/calibration/jobs')
    expect(urls.some((u) => u.startsWith('GET /api/calibration/jobs/j7'))).toBe(true)
    j.stop()
  })
})
