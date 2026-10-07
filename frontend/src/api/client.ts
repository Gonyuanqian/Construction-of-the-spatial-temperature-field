/**
 * 与 FastAPI 的契约层 —— 全前端唯一 fetch 的地方。
 *
 * 图表组件不许自己 fetch：取数集中在页面/store，图表只负责画。
 */
import type { UploadResult } from './types'

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

//: ⚠️ 这里原来用的是**两侧破折号**，而那是本仓明令禁用的上屏字形之一。
//: 它一直没被抓住，因为三条上屏字形守卫各自只扫一块地方（`design/prose.test.ts`
//: 扫四个视图的 template、`NoDataset.test.ts` 与 `routes.smoke.test.ts` 各扫
//: 自己那一片），而这句话是在这个文件里拼好、由页面原样上屏的 —— 三块都不覆盖它。
const OFFLINE = '连不上后端（8503）。确认 API 服务已经起来'

/**
 * 后端的报错在 `detail` 里，原样透出来，别吞掉。
 *
 * 抽出来是因为它原先在 `getJson` / `postJson` 里一模一样地写了两遍，
 * `uploadDataset` 会是第三遍 —— 三份一样的翻译，改一处漏两处。
 *
 * 响应体不是 JSON 时退回状态码：`detail` 是 FastAPI 的约定，
 * 而这个函数也会撞上代理或网关回的 HTML 错误页。
 */
async function asError(res: Response): Promise<ApiError> {
  let detail = `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (body?.detail) detail = String(body.detail)
  } catch { /* 响应体不是 JSON，就用状态码 */ }
  return new ApiError(detail, res.status)
}

export async function getJson<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path)
  } catch {
    // 浏览器原话是 "Failed to fetch"，对新用户毫无信息量。
    throw new ApiError(OFFLINE, 0)
  }
  if (!res.ok) throw await asError(res)
  return (await res.json()) as T
}

/** `getJson` 的写那一半。实时模式那三个动作接口是 `POST`，**没有请求体**。 */
export async function postJson<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { method: 'POST' })
  } catch {
    throw new ApiError(OFFLINE, 0)
  }
  if (!res.ok) throw await asError(res)
  return (await res.json()) as T
}

/**
 * 上传数据集：**原始请求体**，不是 multipart（规格书 §4.1）。
 *
 * `body: file` 直接发 `File` 对象 —— 浏览器会把字节原样放进 body。
 * 文件名走 query 不走请求头：`X-Filename` 里的中文要走 RFC 5987 编码，
 * 而 query 天生是 UTF-8，少一层编码就少一处「某些文件名会乱码」。
 *
 * `Content-Type` 显式写死：浏览器按 `File.type` 猜出来的类型五花八门
 * （`.xlsx` 有可能是空串、也有可能是 `application/vnd...`），
 * 而后端**一个都不看** —— 判据是文件名后缀，不是媒体类型。
 */
export async function uploadDataset(file: File): Promise<UploadResult> {
  let res: Response
  try {
    res = await fetch(`/api/dataset/upload?name=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    })
  } catch {
    throw new ApiError(OFFLINE, 0)
  }
  if (!res.ok) throw await asError(res)
  return (await res.json()) as UploadResult
}

/**
 * `getJson` 的动作那一半里，取消用的那个。
 *
 * 与 `postJson` 分开而不是加一个 `method` 参数：本仓只有这两个动词，
 * 而 `delete` 是保留字，写成 `deleteJson` 一眼知道它是干什么的。
 * **没有请求体** —— 取消谁由路径上的 id 说了。
 */
export async function deleteJson<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { method: 'DELETE' })
  } catch {
    throw new ApiError(OFFLINE, 0)
  }
  if (!res.ok) throw await asError(res)
  return (await res.json()) as T
}
