import {afterEach,beforeEach,expect,it} from 'vitest'
import {defineComponent} from 'vue'
import {enableAutoUnmount,mount} from '@vue/test-utils'
import {loginAs} from '../test/authFixture'
import {clearSession} from '../api/session'
import {useHouseDimensions} from './useHouseDimensions'
enableAutoUnmount(afterEach)
beforeEach(()=>{localStorage.clear();loginAs('USER')})
afterEach(()=>clearSession())
it('默认 6 米，按账号保存和恢复，切换账号不串尺寸',()=>{
 const w=mount(defineComponent({setup:useHouseDimensions,template:'<div/>'}))
 expect(w.vm.selected.length_m).toBe(6)
 w.vm.save({length_m:12,width_m:3,height_m:2});expect(w.vm.customized).toBe(true)
 w.unmount();const second=mount(defineComponent({setup:useHouseDimensions,template:'<div/>'}))
 expect(second.vm.selected.length_m).toBe(12)
 loginAs('ADMIN');expect(second.vm.selected.length_m).toBe(6)
 second.vm.save({length_m:0,width_m:3,height_m:2});expect(second.vm.selected.length_m).toBe(6)
})
