import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiError, getJson } from './client'

describe('getJson', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('200 时返回解析后的 JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      })))
    await expect(getJson<{ status: string }>('/api/health')).resolves.toEqual({ status: 'ok' })
  })

  it('非 200 时抛出带状态码的 ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: '数据集不存在：C:/x.xlsx' }), {
        status: 404, headers: { 'Content-Type': 'application/json' },
      })))
    const err = await getJson('/api/dataset').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(404)
    expect((err as ApiError).message).toContain('数据集不存在')
  })

  it('连不上后端时给出可读的错，而不是 "Failed to fetch"', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    const err = await getJson('/api/health').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).message).toContain('连不上后端')
  })
})
