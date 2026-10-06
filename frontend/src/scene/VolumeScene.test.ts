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
    props: { payload, spec: buildVolumeSpec(payload, 4), picked: null },
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

  it('画不出来时不挂剖切刀（一个对自己无效的控件比没有更难看）', async () => {
    expect((await mountScene()).find('input[type="range"]').exists()).toBe(false)
  })

  it('挂载不抛错', async () => {
    // `mountScene` 是 async 的，于是「`expect(() => mountScene()).not.toThrow()`」
    // 是**永真**的：异步函数抛出去的东西变成一个 rejected promise，
    // `toThrow` 那一层看不见 —— 里面同步炸掉也照样绿。等它落地才算数。
    await expect(mountScene()).resolves.toBeTruthy()
  })
})
