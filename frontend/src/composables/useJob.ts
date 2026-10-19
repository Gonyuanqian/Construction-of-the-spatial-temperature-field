import { ref, type Ref } from 'vue'

import type { CalibrationPayload, JobSummary } from '../api/types'
import { ApiError, deleteJson, getJson, postJson } from '../api/client'

/** 多久问一次。1 秒：阶段 1 与阶段 3 的那一行是秒级的，慢了会看不出在动。 */
const INTERVAL_MS = 1000

export interface JobState {
  /** 当前 / 最近一次任务。一次都没提交过就是 null。 */
  job: Ref<JobSummary | null>
  error: Ref<string>
  polling: Ref<boolean>
  /** 提交一次新任务。**409 不算失败** —— 切去盯已经在跑的那一个。 */
  start: () => Promise<void>
  /** 取消。⚠️ 不自己改成 cancelled，让后端说（见 cancel 的注释）。 */
  cancel: () => Promise<void>
  /** 接着盯一个 id（`job` 已经是那一份摘要时用）。 */
  attach: (id: string) => void
  /** 拿一份 `GET /api/calibration` 的载荷去接管（刷新之后走这一条）。 */
  attachFrom: (j: JobSummary | null) => void
  /** 停下定时器，**不改 job 的状态**。卸载、切页时用。 */
  stop: () => void
}

/**
 * 一次标定任务的轮询。
 *
 * **为什么单独一个组合式**：页② 有两处要盯同一个 job —— 点按钮提交之后，
 * 以及刷新之后从 `GET /api/calibration` 的 `job` 字段接上。两处各写一遍
 * `setInterval` 就会有两份「什么时候停」的判断，而停不下来的定时器是
 * 这类代码最常见的坏法（界面背后每秒发一条请求，谁也不知道）。
 *
 * **为什么用 `setTimeout` 自己续，不用 `setInterval`**：`setInterval` 在
 * 响应慢于周期时会叠起来发 —— 请求越多越慢，越慢请求越多。
 */
export function useJob(intervalMs: number = INTERVAL_MS): JobState {
  const job = ref<JobSummary | null>(null)
  const error = ref('')
  const polling = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  /** 自增号：让在飞的那一次响应作废。与 `useAsync` 同一个手法。 */
  let seq = 0
  // 收到明确答复后才生成下一次编号；网络断开时重试同一次提交。
  let pendingRequestKey: string | null = null
  let submitting = false

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function stop(): void {
    seq += 1
    clearTimer()
    polling.value = false
  }

  async function tick(id: string): Promise<void> {
    // 先清掉挂着的那个定时器：`attach` / `cancel` 可能在上一次还没排完队时
    // 又调了一次 `tick`，不清就会有两个循环同时跑。
    clearTimer()
    const mine = ++seq
    let again = true
    try {
      const out = await getJson<JobSummary>(`/api/calibration/jobs/${id}`)
      if (mine !== seq) return
      job.value = out
      error.value = ''
      if (out.state !== 'running') again = false
    } catch (e) {
      if (mine !== seq) return
      // Java 任务跨重启保留。404 表示记录确实不可查，停止轮询并提示核对环境。
      if (e instanceof ApiError && e.status === 404) {
        stop()
        job.value = null
        error.value = '找不到这次标定任务的记录，请确认当前服务和数据库，再重新提交。'
        return
      }
      // 其余失败**不当作任务失败**：网络抖一下不代表那一次算完了。
      // 报出来，但接着问 —— 停下定时器会让界面永远停在「正在优选…」，
      // 而那是一个用户无从下手的状态。
      error.value = e instanceof Error ? e.message : String(e)
    }
    if (mine !== seq) return
    if (!again) {
      stop()
      return
    }
    timer = setTimeout(() => void tick(id), intervalMs)
  }

  function attach(id: string): void {
    stop()
    job.value = null
    error.value = ''
    polling.value = true
    void tick(id)
  }

  function attachFrom(j: JobSummary | null): void {
    if (!j) return
    if (j.state === 'running') attach(j.id)
    else job.value = j          // 已经结束的：只把那一行说清，不必轮询
  }

  async function start(): Promise<void> {
    if (submitting) return
    submitting = true
    stop()
    error.value = ''
    const mine = seq
    try {
      pendingRequestKey ??= globalThis.crypto.randomUUID()
      const out = await postJson<JobSummary>('/api/calibration/jobs', undefined,
                                            { 'Idempotency-Key': pendingRequestKey })
      pendingRequestKey = null
      if (mine !== seq) return
      job.value = out
      if (out.state === 'running') {
        polling.value = true
        void tick(out.id)
      }
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) pendingRequestKey = null
      if (mine !== seq) return
      if (e instanceof ApiError && e.status === 409 && e.jobId) {
        // 只接管协议中明确指出的运行任务；数据或参数冲突照常报错。
        try {
          const cal = await getJson<CalibrationPayload>('/api/calibration')
          if (mine !== seq) return
          if (cal.job?.id === e.jobId) attachFrom(cal.job)
          else attach(e.jobId)
        } catch (inner) {
          error.value = inner instanceof Error ? inner.message : String(inner)
        }
        return
      }
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      submitting = false
    }
  }

  async function cancel(): Promise<void> {
    const id = job.value?.id
    if (!id) return
    try {
      const out = await deleteJson<JobSummary>(`/api/calibration/jobs/${id}`)
      job.value = out
      // ⚠️ **后端回来的照样是 `running`，我们不把它改成 `cancelled`。**
      // 真正的取消点在库里那个 `should_stop` 下一次被问到时；提前改会让
      // 界面在包的写回还没停下来的那一刻说「已取消」，而验收 3 要的
      // 正是「取消之后盘上逐位没变」。接着问，让后端说。
      //
      // 续问**排在定时器上**，不在这里立刻 `tick` 一次：DELETE 刚刚才把
      // 那一份状态交给我们，立刻再问一遍拿到的还是同一句话，只是把
      // 「取消的当下」这个瞬间填满了 —— 而那一刻正是用户要看的东西。
      // 先 `clearTimer()` 再排：不排掉旧的那个就会有两根定时器同时跑
      // （与 `tick` 开头那次 `clearTimer()` 同一个理由）。
      if (out.state === 'running') {
        polling.value = true
        clearTimer()
        timer = setTimeout(() => void tick(id), intervalMs)
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    }
  }

  return { job, error, polling, start, cancel, attach, attachFrom, stop }
}
