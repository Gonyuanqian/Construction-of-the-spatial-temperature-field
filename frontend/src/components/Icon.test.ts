import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import Icon from './Icon.vue'
import { ICON_PATHS } from '../design/icons'

/**
 * 页⑤ 精修（2026-10-16）新立的一枚通用图标件。
 *
 * 全站原先只有一枚内联 svg（标题条右边那个档案盒），形状直接写在模板里。
 * 这一轮一下要用五枚（叶片 / 脉搏 / 立方体 / 时钟 / 齿轮），于是先立一个件：
 * **名字进、形状出**。形状表放在 `design/icons.ts` 而不是模板里，是因为
 * `design/copy.ts` 的导航清单要**按名字**点图标 —— 形状藏在模板里的写法，
 * 得在模板里再写一遍 switch 才知道哪一项配哪一枚。
 *
 * 名字表从 `ICON_PATHS` **现取**，不在这里抄一份：抄一份的话，谁往表里加了
 * 第六个名字而忘了加用例，屏上就是一处谁也说不清的空白，而一条都不会红。
 */
describe('图标', () => {
  it('表里每一个名字都画得出东西', () => {
    const names = Object.keys(ICON_PATHS) as (keyof typeof ICON_PATHS)[]
    expect(names.length, '一个图标都没有').toBeGreaterThan(0)
    for (const name of names) {
      const w = mount(Icon, { props: { name } })
      expect(w.find('svg').exists(), `${name} 没画出 svg`).toBe(true)
      const d = w.get('path').attributes('d') ?? ''
      expect(d.length, `${name} 的路径是空的`).toBeGreaterThan(10)
      expect(d.trim().slice(0, 1), `${name} 写的不是路径数据`).toMatch(/[Mm]/)
    }
  })

  it('画的是**线框**：不填充，描边走 currentColor', () => {
    // 十六进制色只许出现在 tokens.css 与 charts/scale.ts（`guards.test.ts`
    // 那条全仓守卫）。`currentColor` 还意味着默认 / 悬停 / 选中三态的亮暗
    // 由**文字颜色**带着走 —— 左栏那三态要的正是这件事。
    const w = mount(Icon, { props: { name: 'leaf' } })
    const svg = w.get('svg')
    expect(svg.attributes('fill')).toBe('none')
    expect(svg.attributes('stroke')).toBe('currentColor')
  })

  it('对读屏隐形：图标是装饰，名字由旁边那行文字给', () => {
    const w = mount(Icon, { props: { name: 'gear' } })
    const svg = w.get('svg')
    expect(svg.attributes('aria-hidden')).toBe('true')
    // 真矢量：有 viewBox 才谈得上「跟着字号缩放」，图片与图标字体都没有。
    expect(svg.attributes('viewBox')).toBe('0 0 24 24')
  })
})
