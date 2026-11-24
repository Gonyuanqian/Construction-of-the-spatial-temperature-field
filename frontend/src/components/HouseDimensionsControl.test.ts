import {afterEach,expect,it} from 'vitest'
import {enableAutoUnmount,mount} from '@vue/test-utils'
import HouseDimensionsControl from './HouseDimensionsControl.vue'
import {REFERENCE_DIMENSIONS} from '../live/houseDimensions'
enableAutoUnmount(afterEach)
it('编辑三项尺寸并应用，关闭浮层并恢复焦点',async()=>{
 const w=mount(HouseDimensionsControl,{props:{modelValue:REFERENCE_DIMENSIONS},attachTo:document.body})
 await w.get('[aria-label="棚体尺寸"]').trigger('click')
 expect(w.get('[role="dialog"]').attributes('aria-label')).toBe('棚体尺寸设置')
 await w.get('input').setValue('12')
 await w.get('form').trigger('submit')
 expect(w.emitted('confirm')).toEqual([[{...REFERENCE_DIMENSIONS,length_m:12}]])
 expect(w.find('[role="dialog"]').exists()).toBe(false)
 expect(document.activeElement).toBe(w.get('[aria-label="棚体尺寸"]').element)
})
it('非法尺寸和构场忙碌时不提交，Escape 可关闭',async()=>{
 const w=mount(HouseDimensionsControl,{props:{modelValue:REFERENCE_DIMENSIONS}})
 await w.get('[aria-label="棚体尺寸"]').trigger('click');await w.get('input').setValue('0')
 expect(w.get('[type="submit"]').attributes('disabled')).toBeDefined()
 await w.get('form').trigger('submit');expect(w.emitted('confirm')).toBeUndefined()
 await w.setProps({busy:true});await w.get('form').trigger('submit');expect(w.emitted('confirm')).toBeUndefined()
})
