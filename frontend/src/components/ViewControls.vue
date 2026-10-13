<script setup lang="ts">
/**
 * 「旋转 / 缩放 / 平移」那九枚按钮。
 * 2026-10-12 从 `VolumeScene.vue` 里**原样抽出来**：页③ 上它压在画布右上角，
 * 页⑤ 上它要住进右栏的「三维视图控制」那张卡 —— 同一组按钮、两种摆法，
 * 所以摆法归调用它的那一层，这里只管按钮本身。
 *
 * ⚠️ **它不认识相机**：按下去只把命令名交给 `run`（算术在
 * `scene/orbit.ts`，调用者是 `VolumeScene`）。这一层因此不需要 Three，
 * 也不需要 jsdom 能跑 canvas。
 */
import type { ViewCmd } from '../scene/viewCmd'

defineProps<{
  /** 相机动作。`VolumeScene` 通过 `defineExpose` 出来的那个 `nudge`。 */
  run: (cmd: ViewCmd) => void
  /** 场景画出来没有。没画出来时九枚一律禁用 —— 按不动的按钮比没有更坏。 */
  ok: boolean
}>()
</script>

<template>
  <div class="view-ctl-group" role="group" aria-label="视角">
    <div class="ctl-row">
      <span class="ctl-tag">旋转</span>
      <button type="button" data-view-act="yaw-left" :disabled="!ok" title="绕竖直轴左转" @click="run('yaw-left')">左转</button>
      <button type="button" data-view-act="yaw-right" :disabled="!ok" title="绕竖直轴右转" @click="run('yaw-right')">右转</button>
    </div>
    <div class="ctl-row">
      <span class="ctl-tag">缩放</span>
      <button type="button" data-view-act="zoom-in" :disabled="!ok" title="相机靠近棚体" @click="run('zoom-in')">拉近</button>
      <button type="button" data-view-act="zoom-out" :disabled="!ok" title="相机远离棚体" @click="run('zoom-out')">推远</button>
    </div>
    <div class="ctl-row">
      <span class="ctl-tag">平移</span>
      <button type="button" data-view-act="pan-left" :disabled="!ok" title="画面向左移" @click="run('pan-left')">左</button>
      <button type="button" data-view-act="pan-right" :disabled="!ok" title="画面向右移" @click="run('pan-right')">右</button>
      <button type="button" data-view-act="pan-up" :disabled="!ok" title="画面向上移" @click="run('pan-up')">上</button>
      <button type="button" data-view-act="pan-down" :disabled="!ok" title="画面向下移" @click="run('pan-down')">下</button>
    </div>
    <div class="ctl-row">
      <button type="button" data-view-act="reset" :disabled="!ok" title="回到自动取景" @click="run('reset')">复位</button>
    </div>
  </div>
</template>

<style scoped>
/* ⚠️ 这些规则**从 `VolumeScene.vue` 搬过来**，一个字都没改：
   两处摆法共用同一组按钮，样式分两处写迟早会漂成两种长相。
   ⚠️ 定位与那层底（`position: absolute` / `background` / `box-shadow`）**留在
   `VolumeScene.vue` 的 `.view-ctl` 上** —— 那是「压在画布角上」这个摆法的事，
   页⑤ 把它放进卡片里时不该带着它。这里只管行与按钮。
   ⚠️ **根元素的类名是 `view-ctl-group`，不是 `view-ctl`**：Vue 3 会把父组件的
   scope id 也打在子组件的**根元素**上，于是 `VolumeScene.vue` 里那条
   `position: absolute` 的 `.view-ctl` 会连带命中这里 —— 外面一层已经是
   `position: absolute`，里面再套一层绝对定位，那一组按钮会缩成一个点。
   jsdom 不做布局，这件事**任何自动测试都看不见**。
   ⚠️ 这里**不许**出现分段控件那个类名（`guards.test.ts` 的「一层 .seg 不裁焦点环」
   那条守卫按源码文本扫所有 .vue，名单里精确钉着 ModeSwitch / FieldView / LiveView
   三个文件名）。
   ⚠️ 上面这句解释**也不能把那三行字连原样写出来** —— 守卫扫的是源码文本，
   连注释一起扫，写出来就等于给名单添了第四个文件（这条注释第一版就是这么红的）。 */
.ctl-row { display: flex; align-items: center; gap: 4px; }
.ctl-row + .ctl-row { margin-top: 4px; }
.ctl-tag { font-size: var(--size-label); color: var(--ink-muted); width: 2.6em; }
button {
  font: inherit;
  font-size: var(--size-note);
  cursor: pointer;
  padding: 2px 8px;
  color: var(--ink);
  background: transparent;
  border: var(--rule);
  border-radius: var(--radius);
}
/* 场景没建起来时（没有 WebGL）九颗都灰着。灰而不是消失，是让「这一组存在、
   只是现在用不了」看得出来。 */
button:disabled { cursor: default; opacity: 0.4; }
</style>
