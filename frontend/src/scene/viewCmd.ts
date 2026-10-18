/**
 * 相机动作的名字（九个）。2026-10-12 从 `VolumeScene.vue` 里搬出来 ——
 * `components/ViewControls.vue` 与 `VolumeScene.vue` 两边都要它，
 * 而 SFC 的 `<script setup>` 导不出类型，于是它落在自己一个模块里。
 *
 * ⚠️ **只有名字，没有算术**：算的是 `scene/orbit.ts`，这一层与那一层的调用者
 * （`VolumeScene`）都不许在这里长第二份。
 */
export type ViewCmd =
  | 'yaw-left' | 'yaw-right'
  | 'zoom-in' | 'zoom-out'
  | 'pan-left' | 'pan-right' | 'pan-up' | 'pan-down'
  | 'reset'
