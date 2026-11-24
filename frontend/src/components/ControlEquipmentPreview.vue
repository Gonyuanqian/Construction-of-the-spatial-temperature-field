<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import type { ControlDevice, ControlOverview, DeviceKind } from '../api/greenhouseControl'
import ControlFloorplan from './ControlFloorplan.vue'
import Icon from './Icon.vue'
import { kinds, kindIcons, kindLabels } from '../greenhouse/control'

const props = defineProps<{
  overview: ControlOverview
  focused: DeviceKind | null
  selectedId: string | null
}>()
const emit = defineEmits<{ focus: [kind: DeviceKind]; select: [device: ControlDevice] }>()
const mode = ref<'3d' | '2d'>('3d')
const film = ref(true)
const labels = ref(true)
const unavailable = ref(false)
const scene = ref<{resetView: () => void}>()

function fallback() {
  unavailable.value = true
  mode.value = '2d'
}
const Scene = defineAsyncComponent({
  loader: () => import('./GreenhouseDesignScene.vue'),
  onError(_error, _retry, fail) {
    fallback()
    fail()
  },
  errorComponent: { render: () => null },
})
</script>

<template>
  <section class="control-panel equipment-preview" aria-label="棚内设备布局">
    <header class="panel-heading">
      <h2><Icon name="cube"/>棚内设备布局</h2>
      <div class="view-switch" role="group" aria-label="设备展示方式">
        <button :aria-pressed="mode==='3d'" :disabled="unavailable" @click="mode='3d'">三维视图</button>
        <button :aria-pressed="mode==='2d'" @click="mode='2d'">二维平面</button>
      </div>
    </header>
    <template v-if="mode==='3d'">
      <div class="scene-options">
        <label><input v-model="film" type="checkbox">显示棚膜</label>
        <label><input v-model="labels" type="checkbox">设备标签</label>
        <button @click="scene?.resetView()"><Icon name="reset"/>重置视角</button>
      </div>
      <div class="control-viewport">
        <Scene ref="scene" :spec="props.overview.spec" :layout="props.overview.layout" :control="{
          geometryKey: overview.design_id + ':' + overview.design_revision,
          devices: overview.devices, film, labels, focused, selectedId,
        }" @unavailable="fallback" @select="emit('select', $event)"/>
      </div>
      <div class="scene-footer">
        <span class="muted">拖动旋转 · 滚轮缩放</span>
        <div role="group" aria-label="设备图例">
          <button v-for="kind in kinds" :key="kind" :aria-pressed="focused===kind"
            @click="emit('focus', kind)"><Icon :name="kindIcons[kind]"/>{{kindLabels[kind].slice(0,2)}}</button>
        </div>
      </div>
      <p class="muted scene-note">设备位置和运行效果为模拟示意，A/B 对应棚宽的两侧。</p>
    </template>
    <template v-else>
      <p v-if="unavailable" class="muted" role="status">当前环境无法显示三维视图，已切换到二维平面。</p>
      <ControlFloorplan :overview="overview" :focused="focused" embedded @select="emit('focus', $event)"/>
    </template>
  </section>
</template>

<style scoped>
.equipment-preview { display:flex; flex-direction:column; min-width:0; }
.equipment-preview .panel-heading { flex-wrap:wrap; }
.panel-heading h2 svg { color:var(--edge); }
.view-switch, .scene-options, .scene-footer, .scene-footer>div {
  display:flex; align-items:center; flex-wrap:wrap; gap:8px;
}
.view-switch button, .scene-options button, .scene-footer button { font-size:12px; }
.view-switch button { padding:6px 10px; }
.view-switch button[aria-pressed=true] { background:var(--nav-blue); border-color:var(--nav-blue); color:var(--on-face); }
.scene-options { padding:12px 0; gap:12px; font-size:12px; }
.scene-options label { display:flex; align-items:center; gap:5px; color:var(--ink-muted); }
.scene-options button { margin-left:auto; padding:5px 9px; }
.control-viewport { flex:1; position:relative; min-height:365px; border:1px solid var(--edge-line); border-radius:5px; overflow:hidden; }
.control-viewport :deep(.design-scene) { position:absolute; inset:0; }
.scene-footer { justify-content:space-between; padding-top:10px; font-size:12px; }
.scene-footer button { padding:4px 5px; border-color:transparent; background:transparent; }
.scene-footer button[aria-pressed=true] { color:var(--edge); border-color:var(--edge-line); }
.scene-footer button svg { color:var(--edge); width:16px; height:16px; }
.scene-footer button:last-child svg { color:var(--control-amber); }
.scene-note { font-size:11px; margin:9px 0 0; }
@media (max-width:640px) {
  .control-viewport { min-height:320px; }
  .control-viewport :deep(.design-scene) { min-height:0; }
}
</style>
