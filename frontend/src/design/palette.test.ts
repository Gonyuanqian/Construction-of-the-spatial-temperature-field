import { describe, expect, it } from 'vitest'

import { readPalette } from './palette'

describe('readPalette', () => {
  it('从元素的 CSS 变量读出七个色，读不到就抛（不静默给个默认灰）', () => {
    const el = document.createElement('div')
    el.style.setProperty('--paper', '#F7F6F2')
    el.style.setProperty('--ink', '#211F1C')
    el.style.setProperty('--ink-muted', '#5C5850')
    el.style.setProperty('--steel', '#DEDCD6')
    el.style.setProperty('--leaf', '#14532D')
    el.style.setProperty('--leaf-soft', '#E7EFE9')
    el.style.setProperty('--net', '#0B0F0D')
    expect(readPalette(el)).toEqual({
      paper: '#F7F6F2', ink: '#211F1C', inkMuted: '#5C5850',
      steel: '#DEDCD6', leaf: '#14532D', leafSoft: '#E7EFE9', net: '#0B0F0D',
    })
  })

  it('缺一个变量就抛错，不拿个默认色顶上去', () => {
    // 默认色是最坏的一种兜底：图表照画，颜色是错的，而且没人知道。
    const el = document.createElement('div')
    expect(() => readPalette(el)).toThrow(/--paper/)
  })
})
