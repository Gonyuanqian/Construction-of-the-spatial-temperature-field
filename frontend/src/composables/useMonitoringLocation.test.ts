import {afterEach,beforeEach,expect,it} from 'vitest'
import {defineComponent} from 'vue'
import {enableAutoUnmount,flushPromises,mount} from '@vue/test-utils'
import {clearSession,setVerifiedUser} from '../api/session'
import {useMonitoringLocation} from './useMonitoringLocation'
import type {MonitoringLocation} from '../live/monitoringLocation'
enableAutoUnmount(afterEach)
const place: MonitoringLocation={province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市',longitude:127,latitude:42,coordinate_system:'GCJ-02'}
function user(id:string){setVerifiedUser({id,username:id,display_name:id,role:'USER',enabled:true})}
beforeEach(()=>{localStorage.clear();clearSession();user('first')})
afterEach(()=>{localStorage.clear();clearSession()})
it('已确认地点按账号保存，刷新恢复，切换账号不会沿用别人的地点',async()=>{
  const Harness=defineComponent({setup:useMonitoringLocation,template:'<div />'})
  const a=mount(Harness);a.vm.save(place);expect(a.vm.selected?.city_code).toBe('220600');a.unmount()
  const b=mount(Harness);expect(b.vm.selected?.longitude).toBe(127)
  user('second');await flushPromises();expect(b.vm.selected).toBeNull()
  user('first');await flushPromises();expect(b.vm.selected?.longitude).toBe(127)
  clearSession();await flushPromises();expect(b.vm.selected).toBeNull()
})
it('损坏的地点偏好不阻塞页面或变成有效坐标',()=>{
  localStorage.setItem('tfield.monitoring-location.v1.first','{"city_code":"220600","longitude":"invalid"}')
  const w=mount(defineComponent({setup:useMonitoringLocation,template:'<div />'}));expect(w.vm.selected).toBeNull()
})
