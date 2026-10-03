/**
 * 与 FastAPI 的契约层 —— 全前端唯一 fetch 的地方。
 *
 * 图表组件不许自己 fetch：取数集中在页面/store，图表只负责画。
 */

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function getJson<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path)
  } catch {
    // 浏览器原话是 "Failed to fetch"，对新用户毫无信息量。
    throw new ApiError('连不上后端（8503）——确认 API 服务已经起来', 0)
  }
  if (!res.ok) {
    // 后端的报错在 detail 里，原样透出来，别吞掉。
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch { /* 响应体不是 JSON，就用状态码 */ }
    throw new ApiError(detail, res.status)
  }
  return (await res.json()) as T
}
