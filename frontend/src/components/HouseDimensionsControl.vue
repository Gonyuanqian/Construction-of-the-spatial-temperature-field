<script setup lang="ts">
import {computed,nextTick,onMounted,onUnmounted,reactive,ref,useId,watch} from 'vue'
import Icon from './Icon.vue'
import {DIMENSION_LIMITS,REFERENCE_DIMENSIONS,validDimensions,type HouseDimensions} from '../live/houseDimensions'
const props=defineProps<{modelValue:HouseDimensions;busy?:boolean}>()
const emit=defineEmits<{confirm:[dimensions:HouseDimensions]}>()
const open=ref(false),root=ref<HTMLElement>(),trigger=ref<HTMLButtonElement>(),input=ref<HTMLInputElement>()
const draft=reactive({...props.modelValue}),id=useId()
const valid=computed(()=>validDimensions(draft))
watch(()=>props.modelValue,value=>Object.assign(draft,value))
async function toggle(){open.value=!open.value;if(open.value){Object.assign(draft,props.modelValue);await nextTick();input.value?.focus()}}
function close(event?:KeyboardEvent){if(!event||event.key==='Escape'){if(open.value){event?.stopPropagation();open.value=false;trigger.value?.focus()}}}
function outside(event:PointerEvent){if(!root.value?.contains(event.target as Node))open.value=false}
function confirm(){if(!valid.value||props.busy)return;emit('confirm',{...draft});close()}
onMounted(()=>{document.addEventListener('pointerdown',outside);document.addEventListener('keydown',close)})
onUnmounted(()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',close)})
</script>
<template>
 <div ref="root" class="dimensions-control">
  <button ref="trigger" type="button" class="dimensions-trigger" aria-label="棚体尺寸" :aria-expanded="open" :aria-controls="id" aria-haspopup="dialog" @click="toggle"><Icon name="ruler"/><span>棚体尺寸</span></button>
  <form v-if="open" :id="id" class="dimensions-panel" role="dialog" aria-label="棚体尺寸设置" @submit.prevent="confirm">
   <div class="dimensions-heading"><strong>棚体尺寸</strong><button type="button" aria-label="关闭棚体尺寸设置" @click="close()">×</button></div>
   <p class="note">选择同类拱形棚体，设置实际长、宽、高。</p>
   <div class="presets"><button type="button" @click="Object.assign(draft,REFERENCE_DIMENSIONS)">基准棚体</button><button type="button" @click="Object.assign(draft,{length_m:8,width_m:3,height_m:1.8})">8 × 3 × 1.8 m</button></div>
   <label>棚长 / m<input ref="input" v-model.number="draft.length_m" type="number" step="any" :min="DIMENSION_LIMITS.length_m.min" :max="DIMENSION_LIMITS.length_m.max" required /></label>
   <label>棚宽 / m<input v-model.number="draft.width_m" type="number" step="any" :min="DIMENSION_LIMITS.width_m.min" :max="DIMENSION_LIMITS.width_m.max" required /></label>
   <label>棚高 / m<input v-model.number="draft.height_m" type="number" step="any" :min="DIMENSION_LIMITS.height_m.min" :max="DIMENSION_LIMITS.height_m.max" required /></label>
   <p class="note">原型估算：参考横截面映射，沿长度均匀展开。应用后更新温度场。</p>
   <p v-if="busy" class="note" role="status">正在构场，完成后可应用新尺寸。</p>
   <button class="dimensions-apply" type="submit" :disabled="busy||!valid">应用并构场</button>
  </form>
 </div>
</template>
<style scoped>
.dimensions-control{position:relative;}.dimensions-trigger{display:flex;align-items:center;justify-content:center;gap:5px;min-height:32px;width:100%;padding:6px 8px;white-space:nowrap;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);color:var(--ink-muted);font:inherit;font-size:12px;cursor:pointer;}.dimensions-trigger :deep(.icon){--icon-size:15px;}
.dimensions-panel{position:absolute;top:calc(100% + 8px);left:0;width:286px;max-width:calc(100vw - 32px);z-index:75;padding:16px;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);box-shadow:var(--shadow);color:var(--ink);font-size:13px;}
.dimensions-heading{display:flex;justify-content:space-between;align-items:center;font-size:15px;}.dimensions-heading button{border:0;background:transparent;color:var(--ink-muted);font-size:22px;cursor:pointer;}.dimensions-panel label{display:grid;gap:5px;margin:12px 0;}.dimensions-panel input{width:100%;padding:8px;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);color:var(--ink);font:inherit;}.dimensions-panel .note{white-space:normal;font-size:12px;line-height:1.6;}.presets{display:flex;flex-wrap:wrap;gap:6px;}.presets button{font-size:12px;}.dimensions-apply{width:100%;padding:8px;border:1px solid var(--edge);border-radius:var(--radius);color:var(--edge);background:var(--card);cursor:pointer;}.dimensions-apply:disabled{opacity:.5;cursor:default;}button:focus-visible,input:focus-visible{outline:2px solid var(--edge);outline-offset:3px;}@media(max-width:640px){.dimensions-panel{left:auto;right:0;}}
</style>
