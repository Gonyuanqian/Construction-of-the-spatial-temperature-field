import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ModeSwitch from './ModeSwitch.vue'
import { MODES } from '../design/copy'

describe('模式开关', () => {
  it('外层仍是 nav[aria-label="模式"]，两项都是 button', () => {
    // 形状不许换：`App.test.ts` 按 `nav[aria-label="模式"]` 与 `findAll('button')`
    // 找它（spec §十三.3、§十三.4）。
    const w = mount(ModeSwitch, { props: { modelValue: 'train' } })
    const nav = w.get('nav[aria-label="模式"]')
    expect(nav.findAll('button').map((b) => b.text())).toEqual(MODES.map((m) => m.label))
  })

  it('选中项带 on，其它不带', () => {
    const w = mount(ModeSwitch, { props: { modelValue: 'live' } })
    const btn = (label: string) => w.findAll('button').find((b) => b.text() === label)!
    expect(btn('实时模式').classes()).toContain('on')
    expect(btn('训练模式').classes()).not.toContain('on')
  })

  it('未开放的项 disabled，且理由在 title 上', async () => {
    const w = mount(ModeSwitch, { props: { modelValue: 'train' } })
    const off = MODES.filter((m) => !m.enabled)
    for (const m of off) {
      const b = w.findAll('button').find((x) => x.text() === m.label)!
      expect(b.attributes('disabled')).toBeDefined()
      expect(b.attributes('title')).toBe(m.why)
    }
  })

  it('点一下就改 v-model', async () => {
    const w = mount(ModeSwitch, { props: { modelValue: 'train' } })
    await w.findAll('button').find((b) => b.text() === '实时模式')!.trigger('click')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['live'])
  })
})
