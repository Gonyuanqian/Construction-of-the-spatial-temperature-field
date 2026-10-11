import { ref, type Ref } from 'vue'

import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: Ref<T | null>
  error: Ref<string>
  /** 出错的 HTTP 状态码；不是 `ApiError` 就是 `0`（含「连不上」）。 */
  status: Ref<number>
  loading: Ref<boolean>
  run: () => Promise<void>
}

/**
 * 取数的加载/错误/结果三态。
 *
 * **为什么需要那一串自增号**：用户连点两次「重新加载」时，两个请求都在飞。
 * 先发的可能后回，于是界面上显示的是**旧请求的结果**，而它看起来完全正常 ——
 * 这类错没有报错、只有错数。用一个自增号记住「现在要的是第几次」，
 * 过期的响应直接丢掉。
 *
 * **`status` 是后加的**：`error` 只有一个字符串，`409` 与 `500` 在它眼里
 * 长得一样，而页① 必须把它们分开 —— 「还没导入」是起点，「500」是故障。
 * 拿字符串去 `includes('还没有导入')` 是把一句文案当成协议，改一个字就断。
 */
export function useAsync<T>(fn: () => Promise<T>): AsyncState<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref('')
  const status = ref(0)
  const loading = ref(false)
  let seq = 0

  async function run(): Promise<void> {
    const mine = ++seq
    loading.value = true
    error.value = ''
    status.value = 0
    try {
      const out = await fn()
      if (mine !== seq) return          // 过期响应，丢掉
      data.value = out
    } catch (e) {
      if (mine !== seq) return
      error.value = e instanceof Error ? e.message : String(e)
      status.value = e instanceof ApiError ? e.status : 0
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  return { data, error, status, loading, run }
}
