/**
 * 断面那一档的问数卡。**三个输入框与一张表**，判定全在调用者那一侧。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SectionAsk from './SectionAsk.vue'

/**
 * ⚠️ **取三个框不能用 `input:nth-of-type(n)`**：三个 `<input>` 各自住在**一个**
 * `<label>` 里（形状照抄 `VolumeView.vue` 那一块），于是每一个都是自己那个
 * 父元素里第 1 个 `input` —— `nth-of-type(2)` 一个都选不中，`get()` 当场抛
 * `Unable to get input:nth-of-type(2)`。按出现次序取。
 */

describe('SectionAsk', () => {
  it('三格都填了才发得出去', async () => {
    const w = mount(SectionAsk, {
      props: { answer: null, error: '', note: '可用范围：…' },
    })
    const btn = w.get('button')
    expect(btn.attributes('disabled'), '空着就能点').toBeDefined()
    const boxes = w.findAll('input')
    await boxes[0]!.setValue('0.7')
    await boxes[1]!.setValue('3')
    await boxes[2]!.setValue('0.7')
    expect(w.get('button').attributes('disabled'), '三格都填了还点不动').toBeUndefined()
  })

  it('发出去的是三个**数**，不是三个字符串', async () => {
    // ⚠️ `<input type="number">` 上 `v-model` 自己做数字转换，清空时给的是
    // **空串** —— 而 `Number('') === 0`。空串当 0 用，等于把「没填」当成
    // 「问 0 米处」，屏上会给出一个不是他问的答案，看起来却完全正常。
    const w = mount(SectionAsk, {
      props: { answer: null, error: '', note: '' },
    })
    const boxes = w.findAll('input')
    await boxes[0]!.setValue('0.7')
    await boxes[1]!.setValue('3.4')
    await boxes[2]!.setValue('0.7')
    await w.get('button').trigger('click')
    expect(w.emitted('query')![0]).toEqual([{ x: 0.7, y: 3.4, z: 0.7 }])
  })

  it('清空一格之后立刻点不动 —— 空串不许当 0', async () => {
    const w = mount(SectionAsk, {
      props: { answer: null, error: '', note: '' },
    })
    const boxes = w.findAll('input')
    await boxes[0]!.setValue('0.7')
    await boxes[1]!.setValue('3')
    await boxes[2]!.setValue('0.7')
    await boxes[1]!.setValue('')
    expect(w.get('button').attributes('disabled'), '清空之后还能点').toBeDefined()
  })

  it('答案与错误都原样印，不加工', () => {
    const w = mount(SectionAsk, {
      props: {
        answer: { where: '最近格点 (0.70, 3.00, 0.70)', text: '实测 26.5 °C' },
        error: '',
        note: '可用范围：x 0.00 至 2.10 m。',
      },
    })
    expect(w.text()).toContain('最近格点 (0.70, 3.00, 0.70)')
    expect(w.text()).toContain('实测 26.5 °C')
    expect(w.text()).toContain('可用范围：x 0.00 至 2.10 m。')
  })

  it('出错时给的是 `role="alert"`，不是一句灰字', () => {
    const w = mount(SectionAsk, {
      props: { answer: null, error: '坐标超出这一帧的范围。', note: '' },
    })
    expect(w.get('[role="alert"]').text()).toContain('坐标超出这一帧的范围。')
  })
})
