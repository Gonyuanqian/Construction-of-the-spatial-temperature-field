import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import MonitoringLocationDialog from './MonitoringLocationDialog.vue'
import MonitoringLocationMap from './MonitoringLocationMap.vue'
import {regionApi} from '../api/regions'
import {testRegionCatalog,testRegion} from '../test/archiveFixture'
import {testLocationMap} from '../test/locationMapFixture'

vi.mock('../api/regions',async original=>({...await original<object>(),regionApi:{list:vi.fn()}}))
enableAutoUnmount(afterEach)
beforeEach(()=>{
  vi.clearAllMocks();vi.mocked(regionApi.list).mockResolvedValue(testRegionCatalog)
  vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify(testLocationMap))))
})
afterEach(()=>vi.unstubAllGlobals())
async function open(props={}) {
  const w=mount(MonitoringLocationDialog,{props:{open:true,...props},attachTo:document.body,global:{stubs:{teleport:true}}});await flushPromises();return w
}
it('只在打开时加载地点和地图，不读取模型或提交气象',async()=>{
  const w=await open({open:false});expect(regionApi.list).not.toHaveBeenCalled();expect(fetch).not.toHaveBeenCalled()
  await w.setProps({open:true});await flushPromises()
  expect(w.text()).toContain('选择监测地点')
  expect(w.findAll('select')).toHaveLength(3)
  expect(w.find('input[type=file]').exists()).toBe(false)
  for(const text of ['气象预览','棚体配置','背景温度','导入演示数据','生成温度场']) expect(w.text()).not.toContain(text)
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(vi.mocked(fetch).mock.calls[0]![0]).toBe('/maps/jilin-districts.json')
  expect(w.get('.confirm-location').attributes('disabled')).toBeDefined()
})
it('搜索区县定位地图，确认同时返回行政区和地图坐标',async()=>{
  const w=await open();await w.get('input').setValue('抚松');await w.get('form').trigger('submit')
  expect(w.get('select[aria-label=城市]').element).toHaveProperty('value','220600')
  expect(w.get('select[aria-label=区县]').element).toHaveProperty('value','220621')
  expect(w.getComponent(MonitoringLocationMap).props('focusCode')).toBe('220621')
  await w.get('.confirm-location').trigger('click')
  expect(w.emitted('confirm')?.[0]?.[0]).toEqual(expect.objectContaining({city_code:'220600',district_code:'220621',longitude:127,latitude:42,coordinate_system:'GCJ-02'}))
})
it('取消草稿后重新打开恢复原地点，不把未确认的变更发出去',async()=>{
  const w=await open({modelValue:testRegion})
  await w.get('select[aria-label=区县]').setValue('220622')
  expect(w.get('.selected-place').text()).toContain('靖宇县')
  await w.get('footer button').trigger('click');expect(w.emitted('close')).toHaveLength(1);expect(w.emitted('confirm')).toBeUndefined()
  await w.setProps({open:false});await w.setProps({open:true});await flushPromises()
  expect(w.get('select[aria-label=区县]').element).toHaveProperty('value','')
  expect(w.get('.selected-place').text()).not.toContain('靖宇县')
})
it('地图选点同步区县，下拉切换城市清除旧区县',async()=>{
  const w=await open();w.getComponent(MonitoringLocationMap).vm.$emit('pick',[128.4,42.2]);await flushPromises()
  expect(w.get('select[aria-label=区县]').element).toHaveProperty('value','220622')
  await w.get('.confirm-location').trigger('click')
  expect(w.emitted('confirm')?.[0]?.[0]).toEqual(expect.objectContaining({longitude:128.4,latitude:42.2}))
  await w.get('select[aria-label=城市]').setValue('220200')
  expect(w.get('select[aria-label=区县]').element).toHaveProperty('value','')
})
it('省外点击和未匹配搜索不伪造位置',async()=>{
  const w=await open();w.getComponent(MonitoringLocationMap).vm.$emit('pick',[116,39]);await flushPromises()
  expect(w.get('.picker-hint').text()).toContain('吉林省行政区范围')
  expect(w.get('.confirm-location').attributes('disabled')).toBeDefined()
  await w.get('input').setValue('不存在地点');await w.get('form').trigger('submit')
  expect(w.get('.search-results').text()).toContain('未找到匹配地点')
  expect(w.emitted('confirm')).toBeUndefined()
})
it('地图失败可重试，关闭后迟到请求不修改新草稿',async()=>{
  vi.mocked(fetch).mockResolvedValueOnce(new Response('{}',{status:503}))
  const w=await open();expect(w.get('[role=alert]').text()).toContain('地图暂时无法读取')
  await w.get('[role=alert] button').trigger('click');await flushPromises()
  expect(w.findComponent(MonitoringLocationMap).exists()).toBe(true)
  let resolve!:(v:typeof testRegionCatalog)=>void
  vi.mocked(regionApi.list).mockReturnValueOnce(new Promise(r=>{resolve=r}))
  await w.setProps({open:false});await w.setProps({open:true});await w.setProps({open:false})
  resolve(testRegionCatalog);await flushPromises();expect(w.find('dialog').exists()).toBe(false)
})
