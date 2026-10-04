import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Provenance from './Provenance.vue'

describe('Provenance（出处标记）', () => {
  it('三态各有自己的说明，且互不相同', () => {
    const texts = (['pack', 'live', 'test'] as const).map(
      (k) => mount(Provenance, { props: { kind: k } }).text())
    expect(new Set(texts).size).toBe(3)
  })

  it('「随包数字」说的是随包，不是现场重算', () => {
    const t = mount(Provenance, { props: { kind: 'pack' } }).text()
    expect(t).toContain('随标定包')
  })

  it('「只有验收测试守」是最弱的一态，必须自己说出来', () => {
    const t = mount(Provenance, { props: { kind: 'test' } }).text()
    expect(t).toContain('只有验收测试')
  })
})
