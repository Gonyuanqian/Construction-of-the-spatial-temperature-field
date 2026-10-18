/**
 * 视角按钮从 `VolumeScene` 里抽出来之后，**它自己不许再碰相机** ——
 * 按下去只把命令名交给 `run`。这样页③ 与页⑤ 才能用同一组按钮、
 * 两种摆法（页③ 压在画布角上，页⑤ 住进右栏那张卡）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ViewControls from './ViewControls.vue'

function mountCtl(ok = true) {
  const cmds: string[] = []
  const w = mount(ViewControls, { props: { ok, run: (c: string) => cmds.push(c) } })
  return { w, cmds }
}

describe('ViewControls', () => {
  it('九枚按钮，次序固定', () => {
    const { w } = mountCtl()
    expect(w.findAll('[data-view-act]').map((b) => b.attributes('data-view-act')))
      .toEqual(['yaw-left', 'yaw-right', 'zoom-in', 'zoom-out',
               'pan-left', 'pan-right', 'pan-up', 'pan-down', 'reset'])
  })

  it('按下去的是一串命令名，不是相机动作', () => {
    const { w, cmds } = mountCtl()
    const first = w.findAll('[data-view-act]')[0]!
    return first.trigger('click').then(() => { expect(cmds).toEqual(['yaw-left']) })
  })

  it('场景没画出来时九枚全灰 —— 灰而不是消失', () => {
    // 与 `VolumeScene` 里那条注释同一个意思：让「这一组存在、只是现在用不了」
    // 看得出来。整组消失是另一种说法，那一种更坏。
    const { w } = mountCtl(false)
    expect(w.findAll('[data-view-act]').every((b) => b.attributes('disabled') !== undefined))
      .toBe(true)
  })

  it('根元素不许叫 .view-ctl —— 那个名字上挂着父组件那条绝对定位', () => {
    // ⚠️ 起因不是「名字好看不好看」：Vue 3 把父组件的 scope id 也打在
    // 子组件的**根元素**上，于是 `VolumeScene.vue` 里 `.view-ctl`
    // （`position: absolute` / 底色 / 阴影）会**连带命中**这里。
    // 外面一层已经是绝对定位，里面再套一层，这一组按钮就缩成一个点 ——
    // 而 jsdom 不做布局，这件事在自动测试里**一点声音都没有**。
    // 顺带把 `guards.test.ts` 那条扫 `.seg` 的守卫挡在门外（它钉着三个文件名）。
    expect(mountCtl().w.html()).not.toContain('class="seg"')
    expect(mountCtl().w.html()).toContain('class="view-ctl-group"')
  })
})
