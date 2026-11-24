import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {defineComponent,ref} from 'vue'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import {useAutomaticField} from './useAutomaticField'
import {weatherApi,type AutomaticFieldResult,type WeatherQueryResult} from '../api/weather'
import {makeWeatherQuery} from '../test/weatherQueryFixture'
import {makeLiveStatus} from '../test/fixtures'
import {REFERENCE_DIMENSIONS} from '../live/houseDimensions'
vi.mock('../api/weather',()=>({weatherApi:{construct:vi.fn()}}))
enableAutoUnmount(afterEach)
const result=(query:WeatherQueryResult,id='field')=>({id,live:makeLiveStatus({state:'ready',session_id:id,time:query.field_time,weather:query.weather,weather_source:{provider:'qweather',source_fingerprint:query.source_fingerprint}})}) as AutomaticFieldResult
beforeEach(()=>{vi.resetAllMocks();vi.mocked(weatherApi.construct).mockImplementation(async()=>result(makeWeatherQuery()))})
function setup(){
 const query=ref<WeatherQueryResult|null>(null),enabled=ref(true)
 const wrapper=mount(defineComponent({setup:()=>useAutomaticField(query,enabled),template:'<div />'}))
 return {query,enabled,wrapper}
}
it('只用服务端查询凭据自动构场，没有气象时不发请求',async()=>{
 const {query,wrapper}=setup();await flushPromises();expect(weatherApi.construct).not.toHaveBeenCalled()
 query.value=makeWeatherQuery();await flushPromises()
 expect(weatherApi.construct).toHaveBeenCalledWith(query.value.query_id);expect(wrapper.vm.data?.id).toBe('field');expect(wrapper.vm.loading).toBe(false)
})
it('快速切地点时丢弃旧构场回执，不能覆盖新地点',async()=>{
 let first!:(r:AutomaticFieldResult)=>void,second!:(r:AutomaticFieldResult)=>void
 vi.mocked(weatherApi.construct).mockReturnValueOnce(new Promise(r=>first=r)).mockReturnValueOnce(new Promise(r=>second=r))
 const {query,wrapper}=setup();const a=makeWeatherQuery(),b={...a,query_id:'second',source_fingerprint:'other-grid'}
 query.value=a;await flushPromises();query.value=null;await flushPromises();query.value=b;await flushPromises()
 second(result(b,'new'));await flushPromises();first(result(a,'old'));await flushPromises()
 expect(wrapper.vm.data?.id).toBe('new')
})
it('构场失败不自动无限重试，重新查询后可恢复',async()=>{
 vi.mocked(weatherApi.construct).mockRejectedValueOnce(new Error('模型尚未发布'))
 const {query,wrapper}=setup();query.value=makeWeatherQuery();await flushPromises()
 expect(wrapper.vm.error).toContain('模型尚未发布');expect(wrapper.vm.loading).toBe(false)
 query.value={...query.value!,query_id:'new-ticket'};await flushPromises()
 expect(wrapper.vm.error).toBe('');expect(wrapper.vm.data?.id).toBe('field');expect(weatherApi.construct).toHaveBeenCalledTimes(2)
})
it('离页后完成的旧请求不写入视图，返回的新查询凭据重新接续',async()=>{
 let finish!:(r:AutomaticFieldResult)=>void
 vi.mocked(weatherApi.construct).mockReturnValueOnce(new Promise(r=>finish=r))
 const {query,enabled,wrapper}=setup();const a=makeWeatherQuery();query.value=a;await flushPromises()
 enabled.value=false;await flushPromises();finish(result(a));await flushPromises()
 expect(wrapper.vm.data).toBeNull();expect(wrapper.vm.loading).toBe(false)
 enabled.value=true;query.value={...a,query_id:'fresh-ticket'};await flushPromises()
 expect(wrapper.vm.data?.id).toBe('field')
})
it('缺少近实时光照或旧预报响应不触发构场',async()=>{
 const {query,wrapper}=setup()
 query.value={...makeWeatherQuery(),construction_ready:false,detail:'暂无15分钟内光照'};await flushPromises()
 expect(wrapper.vm.blocked).toBe('暂无15分钟内光照');expect(weatherApi.construct).not.toHaveBeenCalled()
 query.value={...makeWeatherQuery(),data_kind:'forecast'};await flushPromises()
 expect(weatherApi.construct).not.toHaveBeenCalled();expect(wrapper.vm.data).toBeNull()
})
it('settled 等待整个构场请求及响应写入，不能仅等待气象查询',async()=>{
 let finish!:(r:AutomaticFieldResult)=>void
 vi.mocked(weatherApi.construct).mockReturnValueOnce(new Promise(r=>finish=r))
 const {query,wrapper}=setup();const a=makeWeatherQuery();query.value=a
 let complete=false;const pending=wrapper.vm.settled().then(()=>{complete=true})
 await flushPromises();expect(complete).toBe(false);expect(wrapper.vm.loading).toBe(true)
 finish(result(a));await pending;expect(complete).toBe(true);expect(wrapper.vm.data?.id).toBe('field')
})
it('尺寸变更丢弃未完成的旧尺寸回执，等待新查询后只采用匹配尺寸的原型结果',async()=>{
 const query=ref<WeatherQueryResult|null>(null),enabled=ref(true),dimensions=ref({...REFERENCE_DIMENSIONS})
 const wrapper=mount(defineComponent({setup:()=>useAutomaticField(query,enabled,dimensions),template:'<div />'}))
 let finish!:(r:AutomaticFieldResult)=>void
 vi.mocked(weatherApi.construct).mockReturnValueOnce(new Promise(r=>finish=r))
 const a=makeWeatherQuery();query.value=a;await flushPromises()
 expect(weatherApi.construct).toHaveBeenLastCalledWith(a.query_id,REFERENCE_DIMENSIONS)
 dimensions.value={length_m:8,width_m:3,height_m:1.8};await flushPromises()
 finish({...result(a),live:{...result(a).live,prototype:true,dimensions:{...REFERENCE_DIMENSIONS}}});await flushPromises()
 expect(wrapper.vm.data).toBeNull();expect(wrapper.vm.loading).toBe(false)
 vi.mocked(weatherApi.construct).mockImplementation(async()=>({...result(a,'sized'),live:{...result(a,'sized').live,prototype:true,dimensions:{...dimensions.value}}}))
 query.value={...a,query_id:'size-ticket'};await flushPromises()
 expect(wrapper.vm.data?.id).toBe('sized')
 vi.mocked(weatherApi.construct).mockResolvedValue(result(a,'legacy'))
 query.value={...a,query_id:'bad-response'};await flushPromises()
 expect(wrapper.vm.error).toContain('尺寸不一致')
})
