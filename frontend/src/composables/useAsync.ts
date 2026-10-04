import { ref, type Ref } from 'vue'

export interface AsyncState<T> {
  data: Ref<T | null>
  error: Ref<string>
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
 */
export function useAsync<T>(fn: () => Promise<T>): AsyncState<T> {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref('')
  const loading = ref(false)
  let seq = 0

  async function run(): Promise<void> {
    const mine = ++seq
    loading.value = true
    error.value = ''
    try {
      const out = await fn()
      if (mine !== seq) return          // 过期响应，丢掉
      data.value = out
    } catch (e) {
      if (mine !== seq) return
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  return { data, error, loading, run }
}
