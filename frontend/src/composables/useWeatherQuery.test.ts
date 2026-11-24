import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {defineComponent,ref} from 'vue'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import {useWeatherQuery} from './useWeatherQuery'
import {weatherApi,type WeatherQueryResult} from '../api/weather'
import {makePeriodWeatherQuery as makeWeatherQuery,testMonitoringLocation as point} from '../test/weatherQueryFixture'
import type {MonitoringLocation} from '../live/monitoringLocation'
vi.mock('../api/weather',()=>({weatherApi:{query:vi.fn()}}))
enableAutoUnmount(afterEach)
beforeEach(()=>{vi.clearAllMocks();vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-10T07:00:00Z'));vi.spyOn(document,'visibilityState','get').mockReturnValue('visible');vi.mocked(weatherApi.query).mockImplementation(async place=>makeWeatherQuery(place))})
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()})
function setup(initial:MonitoringLocation|null=point){
  const location=ref(initial),enabled=ref(true)
  const w=mount(defineComponent({setup:()=>useWeatherQuery(location,enabled),template:'<div />'}))
  return {w,location,enabled}
}
it('只在有确认地点时查询，并在15分钟到期后更新，不随5秒状态轮询调用',async()=>{
  const {w,location}=setup(null);await flushPromises();expect(weatherApi.query).not.toHaveBeenCalled()
  location.value=point;await flushPromises();expect(weatherApi.query).toHaveBeenCalledTimes(1);expect(w.vm.data?.weather.bg_rh).toBe(61)
  await vi.advanceTimersByTimeAsync(899_999);expect(weatherApi.query).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1);expect(weatherApi.query).toHaveBeenCalledTimes(2)
})
it('切换地点时清除旧读数，较慢的旧地点回执不会覆盖新地点',async()=>{
  let first!:(value:WeatherQueryResult)=>void,second!:(value:WeatherQueryResult)=>void
  vi.mocked(weatherApi.query).mockReturnValueOnce(new Promise(r=>{first=r})).mockReturnValueOnce(new Promise(r=>{second=r}))
  const {w,location}=setup();await flushPromises();location.value={...point,longitude:128};await flushPromises()
  expect(w.vm.data).toBeNull();second(makeWeatherQuery({...point,longitude:128}));await flushPromises()
  first(makeWeatherQuery());await flushPromises();expect(w.vm.data?.requested_coordinates.longitude).toBe(128)
})
it('离页或窗口不可见时停止到期查询，回来才恢复',async()=>{
  const {enabled}=setup();await flushPromises();enabled.value=false;await flushPromises()
  await vi.advanceTimersByTimeAsync(1_000_000);expect(weatherApi.query).toHaveBeenCalledTimes(1)
  enabled.value=true;await flushPromises();expect(weatherApi.query).toHaveBeenCalledTimes(2)
  vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(1_000_000);expect(weatherApi.query).toHaveBeenCalledTimes(2)
})
it('失败显示错误并等待用户重试，不自动反复请求收费源',async()=>{
  vi.mocked(weatherApi.query).mockRejectedValueOnce(new Error('气象源不可用'))
  const {w}=setup();await flushPromises();expect(w.vm.error).toContain('气象源不可用');expect(w.vm.loading).toBe(false)
  await vi.advanceTimersByTimeAsync(3_600_000);expect(weatherApi.query).toHaveBeenCalledTimes(1)
  await w.vm.refresh();expect(weatherApi.query).toHaveBeenCalledTimes(2);expect(w.vm.data?.data_kind).toBe('current')
})
it('半途进入周期仍在下一个整15分钟刷新，不从进入时间再顺延15分钟',async()=>{
  vi.setSystemTime(new Date('2026-11-10T07:37:00Z'));setup();await flushPromises()
  expect(weatherApi.query).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(479_999);expect(weatherApi.query).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(1);expect(weatherApi.query).toHaveBeenCalledTimes(2)
})
