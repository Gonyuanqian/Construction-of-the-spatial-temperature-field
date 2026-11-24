import { computed, onUnmounted, ref, watch, type Ref } from 'vue'

export const MONITORING_INTERVALS = [5, 15, 30, 60] as const

/** Page-owned scheduler. A missed deadline is coalesced into one update, never a backlog. */
export function useTimedMonitoring(options: {
  run: () => Promise<void>
  busy: Ref<boolean>
  active: Ref<boolean>
  location: Ref<unknown | null>
  userId: Ref<string | null>
}) {
  const enabled = ref(false), intervalMinutes = ref(15), nextAt = ref<number | null>(null)
  const running = ref(false), error = ref(''), visible = ref(document.visibilityState !== 'hidden')
  const paused = computed(() => enabled.value && (!options.active.value || !visible.value))
  let timer: ReturnType<typeof setTimeout> | undefined
  let alive = true, generation = 0
  const storageKey = () => options.userId.value ? `tfield.monitoring-interval.v1.${options.userId.value}` : null

  function clearTimer() { if (timer !== undefined) clearTimeout(timer); timer = undefined }
  function arm() {
    clearTimer()
    if (!alive || !enabled.value || paused.value || nextAt.value === null) return
    if (nextAt.value <= Date.now() && (running.value || options.busy.value)) return
    timer = setTimeout(() => { timer = undefined; void tick() }, Math.max(0, nextAt.value - Date.now()))
  }
  async function tick() {
    if (!alive || !enabled.value || paused.value || nextAt.value === null) return
    if (nextAt.value > Date.now()) { arm(); return }
    if (running.value || options.busy.value) return
    const mine = generation
    running.value = true
    error.value = ''
    nextAt.value = Date.now() + intervalMinutes.value * 60_000
    try { await options.run() }
    catch (e) { if (alive && mine === generation) error.value = e instanceof Error ? e.message : '定时更新失败' }
    finally { running.value = false; arm() }
  }
  function stop() { generation++; enabled.value = false; nextAt.value = null; error.value = ''; clearTimer() }
  function start() {
    if (!alive || enabled.value || !options.location.value || !options.userId.value) return
    generation++; enabled.value = true; error.value = ''; nextAt.value = Date.now()
    void tick()
  }
  function setIntervalMinutes(value: number) {
    if (!MONITORING_INTERVALS.some(n => n === value)) return
    intervalMinutes.value = value
    try { const key = storageKey(); if (key) localStorage.setItem(key, String(value)) } catch { /* Preference is optional. */ }
    if (enabled.value) nextAt.value = Date.now() + value * 60_000
    arm()
  }
  watch(options.userId, () => {
    stop(); intervalMinutes.value = 15
    try {
      const key = storageKey(), saved = key ? Number(localStorage.getItem(key)) : NaN
      if (MONITORING_INTERVALS.some(n => n === saved)) intervalMinutes.value = saved
    } catch { /* A blocked store uses the default. Never restore enabled state. */ }
  }, { immediate: true, flush: 'sync' })
  watch(options.location, value => {
    if (!value) { stop(); return }
    // Selecting a location already starts one explicit query in LiveView.
    if (enabled.value) { nextAt.value = Date.now() + intervalMinutes.value * 60_000; arm() }
  }, { flush: 'sync' })
  watch([options.active, visible, options.busy], arm, { flush: 'post' })
  function visibilityChanged() { visible.value = document.visibilityState !== 'hidden' }
  document.addEventListener('visibilitychange', visibilityChanged)
  onUnmounted(() => { alive = false; stop(); document.removeEventListener('visibilitychange', visibilityChanged) })
  return { enabled, intervalMinutes, nextAt, running, paused, error, start, stop, setIntervalMinutes }
}
