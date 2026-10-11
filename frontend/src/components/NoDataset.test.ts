import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import NoDataset from './NoDataset.vue'

/** spec §8.5 禁的连接符与会漏成字面字符的 markdown 标记。 */
const BANNED = ['——', '**', '`', ' · ', '→', '↳'] as const

describe('NoDataset', () => {
  it('说的是一句能照做的话，不是一个状态码', () => {
    const w = mount(NoDataset)
    expect(w.text()).toContain('先导入数据集')
    // 指出该去哪儿 —— 只说「没有数据」等于把用户丢在原地
    expect(w.text()).toContain('数据导入与检查')
  })

  it('没有禁用字形', () => {
    for (const bad of BANNED) {
      expect(mount(NoDataset).text(), `出现了被禁的 ${JSON.stringify(bad)}`)
        .not.toContain(bad)
    }
  })

  it('不出现「错误」二字，也不出现状态码', () => {
    // 空态是系统的**起点**，不是故障。画成一张错误卡，验收的人第一次
    // 打开系统就会以为哪里坏了 —— 这一条守的就是那个观感。
    const w = mount(NoDataset)
    expect(w.text()).not.toContain('错误')
    expect(w.text()).not.toContain('失败')
    expect(w.text()).not.toContain('409')
  })
})
