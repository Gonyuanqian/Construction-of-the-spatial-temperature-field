import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import Provenance from './Provenance.vue'
import { PROV } from '../design/copy'

describe('Provenance（出处标记）', () => {
  it('三态在屏上各是一个字，且互不相同', () => {
    const marks = (['pack', 'live', 'test'] as const)
      .map((k) => mount(Provenance, { props: { kind: k } }).text())
    expect(marks).toEqual(['包', '算', '测'])
    expect(new Set(marks).size).toBe(3)
  })

  it('整句没丢，改挂在 title 上（降噪不是删掉解释）', () => {
    const w = mount(Provenance, { props: { kind: 'pack' } })
    expect(w.get('span').attributes('title')).toBe(PROV.pack.why)
    expect(w.get('span').attributes('title')).toContain('随标定包')
  })

  it('「只有验收测试守」是最弱的一态，必须在 title 里自己说出来', () => {
    const w = mount(Provenance, { props: { kind: 'test' } })
    expect(w.get('span').attributes('title')).toContain('只有验收测试')
  })

  it('可见文本里不许出现被禁的连接符（spec §8.5）', () => {
    for (const k of ['pack', 'live', 'test'] as const) {
      const t = mount(Provenance, { props: { kind: k } }).text()
      for (const bad of ['——', '**', '`', ' · ', '→', '↳']) {
        expect(t, `${k} 的可见文本里出现了 ${bad}`).not.toContain(bad)
      }
    }
  })
})
