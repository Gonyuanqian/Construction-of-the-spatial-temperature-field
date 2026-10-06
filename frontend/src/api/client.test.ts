import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ApiError, getJson, uploadDataset } from './client'

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

describe('uploadDataset', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('走原始请求体，文件名放在 query 里（不是 multipart，不是请求头）', async () => {
    // 这一条钉的是**形状**：换成 FormData 或 UploadFile 都要引
    // python-multipart，而它不在 requirements-api.txt 里 —— 那会让整个后端
    // 在干净机器上起不来，而前端这一侧的测试照样绿。
    const seen: RequestInit[] = []
    const urls: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      seen.push(init)
      urls.push(String(url))
      expect(String(url)).toContain('/api/dataset/upload?name=')
      return new Response(JSON.stringify({ file: 'a.xlsx', n_times: 1 }), {
        status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const NAME = '人参棚 副本.xlsx'
    const file = new File([new Uint8Array([1, 2, 3])], NAME)
    await uploadDataset(file)
    expect(seen[0].method).toBe('POST')
    // 名字要 encodeURIComponent 过 —— 中文与空格直接进 URL 会在某些
    // 浏览器/代理上被截断，而后端收到的是一个少半截的文件名。
    // 这两条断言是补的：计划原文只在注释里说了这件事，断言里没有它 ——
    // 直接把 `file.name` 拼进 URL 也照样绿。
    expect(urls[0]).toContain(`name=${encodeURIComponent(NAME)}`)
    expect(urls[0], '名字没编码，中文原样进了 URL').not.toContain(NAME)
    expect(seen[0].body).toBeInstanceOf(File)
  })

  it('后端的 detail 原样透出来，带上状态码', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('{"detail":"这份文件读不成数据集：KeyError: 宽表"}', {
        status: 400, headers: { 'Content-Type': 'application/json' } })))
    const file = new File([new Uint8Array([1])], 'x.xlsx')
    await expect(uploadDataset(file)).rejects.toMatchObject({
      message: '这份文件读不成数据集：KeyError: 宽表', status: 400,
    })
  })
})
