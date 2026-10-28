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
import { ref } from 'vue'
import type { ViewCmd } from '../scene/viewCmd'
import Icon from './Icon.vue'

withDefaults(defineProps<{
  /** 相机动作。`VolumeScene` 通过 `defineExpose` 出来的那个 `nudge`。 */
  run: (cmd: ViewCmd) => void
  /** 场景画出来没有。没画出来时九枚一律禁用 —— 按不动的按钮比没有更坏。 */
  ok: boolean
  /** panel 用于实时页卡片；toolbar 保留画布上的紧凑摆法。 */
  layout?: 'toolbar' | 'panel'
}>(), { layout: 'toolbar' })
const activeMode = ref<'rotate' | 'zoom' | 'pan'>('rotate')
const emit = defineEmits<{ mode: [value: 'rotate' | 'zoom' | 'pan'] }>()
const modes = [
  { key: 'rotate', label: '旋转', icon: 'rotate' },
  { key: 'zoom', label: '缩放', icon: 'zoom' },
  { key: 'pan', label: '平移', icon: 'move' },
] as const
function selectMode(mode: 'rotate' | 'zoom' | 'pan') {
  activeMode.value = mode
  emit('mode', mode)
}
</script>

<template>
  <div v-if="layout === 'panel'" class="view-ctl-group panel" role="group" aria-label="三维视图控制">
    <div class="panel-head">
      <Icon name="eye" class="panel-eye" />
      <strong>三维视图控制</strong>
    </div>
    <div class="panel-grid">
      <button v-for="mode in modes" :key="mode.key" type="button" class="mode-tile"
              :class="{ selected: activeMode === mode.key }" :aria-pressed="activeMode === mode.key"
              :disabled="!ok" @click="selectMode(mode.key)">
        <Icon :name="mode.icon" />
        <span>{{ mode.label }}</span>
      </button>
    </div>
    <div class="panel-footer">
      <span class="help-cube"><Icon name="cube" /></span>
      <p class="panel-help">{{ activeMode === 'rotate' ? '拖动鼠标旋转三维模型' : activeMode === 'zoom' ? '上下拖动鼠标缩放三维模型' : '拖动鼠标平移三维模型' }}</p>
      <button type="button" class="compact-reset" data-view-act="reset" :disabled="!ok"
              title="回到自动取景" aria-label="复位视图" @click="run('reset')"><Icon name="reset" /></button>
    </div>
  </div>

  <div v-else class="view-ctl-group" role="group" aria-label="视角">
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
.panel-head { position: relative; }
.panel-head::after { content: ''; position: absolute; right: 0; bottom: -1px; width: 7px; height: 2px; background: var(--interact); }
.panel-grid .mode-tile { min-width: 0; min-height: 84px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; border: 1px solid var(--interact); color: var(--ink-muted); background: transparent; font-size: var(--size-label); }
.mode-tile :deep(.icon) { --icon-size: 26px; color: var(--nav-blue); }
.panel-grid .mode-tile.selected { color: var(--ink); border-color: var(--edge); background: var(--card-2); }
.mode-tile.selected :deep(.icon) { color: var(--edge); }
.panel-grid .mode-tile:hover:not(:disabled) { border-color: var(--edge); color: var(--ink); }
.panel-footer { display: flex; align-items: center; gap: 12px; margin-top: 20px; }
.help-cube { display: flex; align-items: center; justify-content: center; width: 48px; height: 48px; flex: none; border: 1px solid var(--interact); border-radius: var(--radius); color: var(--edge); }
.help-cube :deep(.icon) { --icon-size: 30px; }
.panel-footer .panel-help { margin: 0; flex: 1; }
.compact-reset { display: flex; align-items: center; justify-content: center; padding: 5px; color: var(--ink-muted); }

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

/* 实时页的方框控件：图标和分类名在上，原有方向动作保留在卡片内。 */
.panel-head {
  display: flex; align-items: center; gap: var(--gap-s);
  padding-bottom: var(--gap-s); margin-bottom: var(--gap-m);
  border-bottom: var(--rule);
  color: var(--ink);
}
.panel-eye { --icon-size: 22px; color: var(--edge); }
.panel-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--gap-s); }
.control-tile {
  min-width: 0; min-height: 112px; padding: var(--gap-s) 4px;
  display: flex; flex-direction: column; align-items: center; gap: var(--gap-s);
  border: 1px solid var(--steel); border-radius: var(--radius);
  color: var(--ink-muted);
}
.tile-icon { --icon-size: 22px; color: var(--interact); }
.control-tile > strong { color: var(--ink); font-weight: var(--w-strong); }
.action-row {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px; width: 100%; margin-top: auto;
}
.action-row button {
  min-width: 0; padding: 3px 1px; font-size: var(--size-note);
  color: var(--ink-muted); background: transparent; border: 1px solid var(--steel);
  white-space: nowrap;
}
.action-row button:hover:not(:disabled), .reset-action:hover:not(:disabled) {
  border-color: var(--edge); color: var(--ink);
}
.reset-action {
  display: flex; align-items: center; justify-content: center; gap: var(--gap-s);
  width: 100%; margin-top: var(--gap-s); padding: var(--gap-s);
  color: var(--ink-muted); background: transparent; border: 1px solid var(--steel);
}
.reset-action :deep(.icon) { --icon-size: 18px; }
.panel-help {
  display: flex; align-items: center; gap: var(--gap-m);
  margin: var(--gap-m) 0 0; color: var(--ink-muted); font-size: var(--size-note);
}
.panel-help :deep(.icon) { --icon-size: 28px; flex: none; color: var(--edge); }
</style>
