import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import { makeVolumePayload } from '../test/fixtures'
import VolumeScene from './VolumeScene.vue'
import { buildVolumeSpec } from './volumeView'

/**
 * 与页①/页③ 同一套环境夹具：tokens 读不到就抛错的调色板，
 * 以及 jsdom 里没有的 ResizeObserver。
 */
function installEnvironment(): void {
  const root = document.documentElement
  root.style.setProperty('--paper', '#F7F6F2')
  root.style.setProperty('--ink', '#211F1C')
  root.style.setProperty('--ink-muted', '#5C5850')
  root.style.setProperty('--steel', '#DEDCD6')
  root.style.setProperty('--leaf', '#14532D')
  root.style.setProperty('--leaf-soft', '#E7EFE9')
  root.style.setProperty('--net', '#0B0F0D')
  root.style.setProperty('--layer-top', '#C44E52')
  root.style.setProperty('--layer-mid', '#4C72B0')
  root.style.setProperty('--layer-low', '#55A868')
  root.style.setProperty('--bar', '#D98C2B')
  root.style.setProperty('--size-chart-axis', '12px')
  root.style.setProperty('--size-chart-title', '14px')
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
}

/**
 * 挂载并等一帧。
 *
 * `unavailable` 是在 `onMounted` 里置上的，而 ref 的改动走 Vue 的异步刷新 ——
 * 不 `await nextTick()` 就读到的是**首帧**的 DOM：那时候那句说明还没渲染出来，
 * 剖切刀也还挂在页面上。浏览器里不需要等（Vue 在同一个微任务里刷完，微任务
 * 跑在绘制之前，所以用户看不到那一瞬），但 jsdom 里断言是同步的，必须显式等。
 */
async function mountScene() {
  const payload = makeVolumePayload()
  const w = mount(VolumeScene, {
    // `cutY` 由页级给（剖切刀已经搬到 `VolumeView`），这一层只把它写进裁剪面。
    props: { payload, spec: buildVolumeSpec(payload, 4), picked: null, cutY: 3.5 },
  })
  await nextTick()
  return w
}

describe('没有 WebGL 的机器（Review Focus 4）', () => {
  beforeEach(() => {
    installEnvironment()
    vi.restoreAllMocks()
  })

  it('说清楚画不出来、并说明二维视图不受影响，而不是白屏或抛错', async () => {
    // jsdom 没有 canvas/WebGL（规格书 §8.2），所以这条路在这里是**真的**在跑，
    // 不是被 mock 出来的。它在真实世界里的对应物是：旧显卡、禁用硬件加速的
    // 浏览器、远程桌面。白屏是最坏的一种「正常」—— 用户不知道是坏了他这台机器，
    // 还是系统本来就这样。
    const w = await mountScene()
    expect(w.text()).toContain('WebGL')
    expect(w.text()).toContain('二维断面视图不受影响')
  })

  it('把「画不出来」这件事报给页级 —— 剖切刀挂不挂由它定', async () => {
    // 这一条原先是「画不出来时不挂剖切刀」。控件已经搬到 `VolumeView`
    // （只有页级知道这一块的版面），于是**那条不变量跟着控件搬过去了** ——
    // 见 `VolumeView.test.ts` 的「场景没报『画得出来』之前不挂」。
    //
    // 搬的理由不是「测试写在哪边都能跑」，而是**性质该由拥有它的那一层来守**：
    // 这一层现在只负责把结果报上去，`ready` 带一个布尔，`false` 就是画不出来。
    const w = await mountScene()
    expect(w.emitted('ready'), '没把结果报上去').toBeTruthy()
    expect(w.emitted('ready')![0]).toEqual([false])
  })

  it('挂载不抛错', async () => {
    // `mountScene` 是 async 的，于是「`expect(() => mountScene()).not.toThrow()`」
    // 是**永真**的：异步函数抛出去的东西变成一个 rejected promise，
    // `toThrow` 那一层看不见 —— 里面同步炸掉也照样绿。等它落地才算数。
    await expect(mountScene()).resolves.toBeTruthy()
  })
})

describe('视角按钮（2026-10-09 用户裁定「旋转/缩放/平移按钮可以做」）', () => {
  beforeEach(installEnvironment)

  it('默认不画：页③ 那一档与改动前逐字相同', async () => {
    const w = await mountScene()
    expect(w.findAll('[data-view-act]'), '默认档上冒出了视角按钮').toEqual([])
  })

  it('开了就画满九颗，而且在没有 WebGL 的机器上一律灰着', async () => {
    // ⚠️ 判据是 `showViewControls` 一个，**不是** `showViewControls && sceneReady`。
    // 绑上 `sceneReady` 的话这一条在 jsdom 里永远红 —— 而它红了之后，
    // 唯一的选择就是把判据改回单条件，于是「九颗都在」这件事在自动测试里
    // 再也没人看着（那条路正是三处属性名写错也不报错的地方）。
    // 「建不起来」由 `disabled` 说：「这一组在，只是现在用不了」。
    const payload = makeVolumePayload()
    const w = mount(VolumeScene, {
      props: {
        payload, spec: buildVolumeSpec(payload, 4), picked: null, cutY: 3.5,
        showViewControls: true,
      },
    })
    await nextTick()

    const btns = w.findAll('[data-view-act]')
    expect(btns).toHaveLength(9)
    expect(btns.map((b) => b.attributes('data-view-act'))).toEqual([
      'yaw-left', 'yaw-right', 'zoom-in', 'zoom-out',
      'pan-left', 'pan-right', 'pan-up', 'pan-down', 'reset',
    ])
    // 没有 WebGL ⇒ 相机没建起来 ⇒ 九颗都按不动。
    for (const b of btns) {
      expect(b.attributes('disabled'), `${b.attributes('data-view-act')} 不是灰的`).toBeDefined()
    }
  })
})
