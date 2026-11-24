import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { useTimedMonitoring } from './useTimedMonitoring'

enableAutoUnmount(afterEach)
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-11T02:00:00Z')); localStorage.clear(); visibility('visible') })
afterEach(() => vi.useRealTimers())
function visibility(value: string) { Object.defineProperty(document, 'visibilityState', { configurable: true, value }); document.dispatchEvent(new Event('visibilitychange')) }
function setup(run = vi.fn(async () => {})) {
  const busy = ref(false), active = ref(true), location = ref<unknown | null>({ city: 'a' }), userId = ref<string | null>('user-a')
  let schedule!: ReturnType<typeof useTimedMonitoring>
  const w = mount(defineComponent({ setup() { schedule = useTimedMonitoring({ run, busy, active, location, userId }); return () => null } }))
  return { w, schedule, run, busy, active, location, userId }
}
it('默认单次；开启立即更新，然后按间隔运行，暂停后不再调用', async () => {
  const { schedule: s, run } = setup()
  await vi.advanceTimersByTimeAsync(60 * 60_000); expect(run).not.toHaveBeenCalled()
  s.start(); await flushPromises(); expect(run).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(15 * 60_000 - 1); expect(run).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1); expect(run).toHaveBeenCalledTimes(2)
  s.stop(); await vi.advanceTimersByTimeAsync(60 * 60_000); expect(run).toHaveBeenCalledTimes(2)
})
it('修改间隔从修改时重新计时；仅保存间隔，不自动恢复开启状态', async () => {
  const { schedule: s, run, w } = setup(); s.start(); await flushPromises()
  await vi.advanceTimersByTimeAsync(4 * 60_000); s.setIntervalMinutes(5)
  await vi.advanceTimersByTimeAsync(5 * 60_000); expect(run).toHaveBeenCalledTimes(2)
  s.setIntervalMinutes(1); expect(s.intervalMinutes.value).toBe(5)
  w.unmount(); const fresh = setup(); expect(fresh.schedule.intervalMinutes.value).toBe(5); expect(fresh.schedule.enabled.value).toBe(false)
})
it('长构场跨过多个间隔后只补一次，不并行、不积压多次执行', async () => {
  let finish!: () => void
  const run = vi.fn(async () => {}); run.mockImplementationOnce(() => new Promise<void>(r => { finish = r }))
  const { schedule: s } = setup(run); s.setIntervalMinutes(5); s.start()
  await vi.advanceTimersByTimeAsync(21 * 60_000); expect(run).toHaveBeenCalledTimes(1)
  finish(); await flushPromises(); await vi.advanceTimersByTimeAsync(0); expect(run).toHaveBeenCalledTimes(2)
  await vi.advanceTimersByTimeAsync(5 * 60_000); expect(run).toHaveBeenCalledTimes(3)
})
it('手动构场忙碌时等待，完成后只执行一次；等待期间暂停取消后续调用', async () => {
  const { schedule: s, run, busy } = setup(); busy.value = true; s.start(); await flushPromises()
  await vi.advanceTimersByTimeAsync(30 * 60_000); expect(run).not.toHaveBeenCalled()
  busy.value = false; await nextTick(); await vi.advanceTimersByTimeAsync(0); expect(run).toHaveBeenCalledTimes(1)
  busy.value = true; await vi.advanceTimersByTimeAsync(15 * 60_000); s.stop()
  busy.value = false; await nextTick(); await vi.advanceTimersByTimeAsync(0); expect(run).toHaveBeenCalledTimes(1)
})
it('离页或后台标签暂缓，返回只补一次；截止时间未到不提前更新', async () => {
  const { schedule: s, run, active } = setup(); s.start(); await flushPromises()
  active.value = false; await nextTick(); await vi.advanceTimersByTimeAsync(60 * 60_000)
  expect(run).toHaveBeenCalledTimes(1); expect(s.paused.value).toBe(true)
  active.value = true; await nextTick(); await vi.advanceTimersByTimeAsync(0); expect(run).toHaveBeenCalledTimes(2)
  visibility('hidden'); await nextTick(); await vi.advanceTimersByTimeAsync(5 * 60_000)
  visibility('visible'); await nextTick(); await vi.advanceTimersByTimeAsync(0); expect(run).toHaveBeenCalledTimes(2)
  await vi.advanceTimersByTimeAsync(10 * 60_000); expect(run).toHaveBeenCalledTimes(3)
})
it('切换地点重新计时；清空地点、切换账号与卸载均取消调度', async () => {
  const { schedule: s, run, location, userId, w } = setup(); s.start(); await flushPromises()
  await vi.advanceTimersByTimeAsync(10 * 60_000); location.value = { city: 'b' }
  await vi.advanceTimersByTimeAsync(5 * 60_000); expect(run).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(10 * 60_000); expect(run).toHaveBeenCalledTimes(2)
  location.value = null; s.start(); expect(s.enabled.value).toBe(false)
  location.value = {}; s.setIntervalMinutes(5); s.start(); await flushPromises()
  userId.value = 'user-b'; expect(s.enabled.value).toBe(false); expect(s.intervalMinutes.value).toBe(15)
  s.start(); await flushPromises(); const count = run.mock.calls.length; w.unmount()
  await vi.advanceTimersByTimeAsync(60 * 60_000); expect(run).toHaveBeenCalledTimes(count)
})
it('请求失败保留错误并等下个间隔重试，不立即重复调用', async () => {
  const run = vi.fn(async () => {}); run.mockRejectedValueOnce(new Error('连接失败'))
  const { schedule: s } = setup(run); s.start(); await flushPromises()
  expect(s.error.value).toBe('连接失败')
  await vi.advanceTimersByTimeAsync(15 * 60_000 - 1); expect(run).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1); expect(run).toHaveBeenCalledTimes(2); expect(s.error.value).toBe('')
})
