import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {defineComponent,ref} from 'vue'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import {useSingleWeatherQuery} from './useSingleWeatherQuery'
import {weatherApi,type WeatherQueryResult} from '../api/weather'
import {makeWeatherQuery,testMonitoringLocation as point} from '../test/weatherQueryFixture'
import type {MonitoringLocation} from '../live/monitoringLocation'
vi.mock('../api/weather',()=>({weatherApi:{query:vi.fn()}}))
enableAutoUnmount(afterEach)
beforeEach(()=>{vi.resetAllMocks();vi.useFakeTimers();vi.mocked(weatherApi.query).mockImplementation(async p=>makeWeatherQuery(p))})
afterEach(()=>vi.useRealTimers())
function setup(){const location=ref<MonitoringLocation|null>(point),enabled=ref(true);const w=mount(defineComponent({setup:()=>useSingleWeatherQuery(location,enabled),template:'<div/>'}));return{w,location,enabled}}
it('仅主动构场时查询，超时、返回页面和切换可见性均不自动取天气',async()=>{
 const{w,enabled}=setup();await flushPromises();expect(weatherApi.query).not.toHaveBeenCalled()
 await w.vm.refresh();expect(weatherApi.query).toHaveBeenCalledTimes(1)
 await vi.advanceTimersByTimeAsync(3_600_000);enabled.value=false;await flushPromises();enabled.value=true;await flushPromises()
 document.dispatchEvent(new Event('visibilitychange'));await flushPromises();expect(weatherApi.query).toHaveBeenCalledTimes(1)
 expect(w.vm.data?.monitoring_mode).toBe('single_shot')
})
it('选点改变后清除旧查询，较晚返回的旧地点不会覆盖新地点',async()=>{
 let finish!:(q:WeatherQueryResult)=>void
 vi.mocked(weatherApi.query).mockReturnValueOnce(new Promise(r=>finish=r))
 const{w,location}=setup();void w.vm.refresh();location.value={...point,longitude:128}
 finish(makeWeatherQuery(point));await flushPromises();expect(w.vm.data).toBeNull()
 await w.vm.refresh();expect(w.vm.data?.requested_coordinates.longitude).toBe(128)
})
it('失败后只等待用户重试，已发起的单次查询离页后仍完成',async()=>{
 vi.mocked(weatherApi.query).mockRejectedValueOnce(new Error('连接失败'))
 const{w,enabled}=setup();await w.vm.refresh();expect(w.vm.error).toBe('连接失败')
 await vi.advanceTimersByTimeAsync(3_600_000);expect(weatherApi.query).toHaveBeenCalledTimes(1)
 const pending=w.vm.refresh();enabled.value=false;await pending;expect(w.vm.data).not.toBeNull()
})
