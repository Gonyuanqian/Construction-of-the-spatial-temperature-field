import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import StatCard from './StatCard.vue'
import StatRow from './StatRow.vue'

describe('一排指标卡', () => {
  it('把插槽里的卡片原样收进来，一张不多一张不少', () => {
    const w = mount(StatRow, {
      slots: {
        default: [
          h(StatCard, { label: '个时刻', value: '1308' }),
          h(StatCard, { label: '列', value: '52' }),
        ],
      },
    })
    expect(w.findAllComponents(StatCard).length).toBe(2)
  })

  it('自己不是表格，也不引标题', () => {
    const w = mount(StatRow)
    expect(w.find('table').exists()).toBe(false)
    expect(w.find('h2').exists()).toBe(false)
    expect(w.find('h3').exists()).toBe(false)
  })
})
