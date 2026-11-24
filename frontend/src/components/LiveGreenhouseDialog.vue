<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { designsApi, type DesignRecord } from '../api/greenhouseDesigns'
import { useAsync } from '../composables/useAsync'
import { monitoringConfig } from '../live/designSelection'
import { sameDimensions, type HouseDimensions } from '../live/houseDimensions'
import { sameRegion, type MonitoringLocation } from '../live/monitoringLocation'
import ModalDialog from './ModalDialog.vue'

const props=defineProps<{
  location: MonitoringLocation | null
  dimensions: HouseDimensions
  busy?: boolean
  applying?: boolean
  error?: string
}>()
const emit=defineEmits<{close: []; apply: [plan: DesignRecord]; 'clear-error': []}>()
const {data,loading,error:listError,run:loadList}=useAsync(designsApi.list)
const {data:activeDesign,run:loadActive}=useAsync(designsApi.active)
const selectedId=ref('')
const plans=computed(()=>data.value?.items??[])
const selected=computed(()=>plans.value.find(plan=>plan.id===selectedId.value))
const issue=computed(()=>selected.value?monitoringConfig(selected.value.spec).issue:'')
const region=computed(()=>[selected.value?.spec.location.province_name,selected.value?.spec.location.city_name].filter(Boolean).join(' · ')||'地点未设置')
const dimensionsText=computed(()=>{
  const structure=selected.value?.spec.structure
  return structure?`${structure.length_m} × ${structure.width_m} × ${structure.arch_height_m} m`:''
})
const current=computed(()=>{
  const plan=activeDesign.value?.selection,point=props.location
  if(!plan||!point)return null
  const config=monitoringConfig(plan.spec)
  return config.issue===null&&sameDimensions(config.dimensions,props.dimensions)&&sameRegion(config.location,point)
    &&config.location.longitude===point.longitude&&config.location.latitude===point.latitude?plan:null
})

async function load(){
  emit('clear-error')
  await Promise.all([loadList(),loadActive()])
  if(!plans.value.some(plan=>plan.id===selectedId.value))selectedId.value=current.value?.id??''
}
function apply(){
  if(selected.value&&!issue.value&&!loading.value&&!props.busy&&!props.applying)emit('apply',selected.value)
}
onMounted(load)
</script>

<template>
  <ModalDialog label="选择温室棚体" :busy="applying" @close="emit('close')">
    <form class="live-greenhouse-picker" @submit.prevent="apply">
      <h3>选择温室棚体</h3>
      <p v-if="current" class="picker-note">当前方案 {{ current.spec.name }} · v{{ current.revision }}</p>
      <p v-if="loading" class="picker-note" role="status">正在读取温室方案…</p>
      <p v-else-if="listError" class="picker-error" role="alert">{{ listError }}</p>
      <p v-else-if="!plans.length" class="picker-note">还没有保存的方案。请先在温室设计中保存一份方案。</p>
      <template v-else>
        <label>
          温室方案
          <select v-model="selectedId" :disabled="applying" @change="emit('clear-error')">
            <option value="" disabled>请选择温室方案</option>
            <option v-for="plan in plans" :key="plan.id" :value="plan.id">{{ plan.spec.name }} · v{{ plan.revision }}</option>
          </select>
        </label>
        <dl v-if="selected" class="picker-summary">
          <div><dt>监测地点</dt><dd>{{ region }}</dd></div>
          <div><dt>长 × 宽 × 高</dt><dd>{{ dimensionsText }}</dd></div>
        </dl>
        <p v-if="issue" class="picker-note">{{ issue }}</p>
      </template>
      <p v-if="error" class="picker-error" role="alert">{{ error }}</p>
      <footer>
        <RouterLink v-if="(!loading&&!listError&&!plans.length)||issue" to="/greenhouse-design">前往温室设计</RouterLink>
        <button v-if="listError||error" type="button" :disabled="loading||applying" @click="load">刷新方案</button>
        <button type="button" :disabled="applying" @click="emit('close')">取消</button>
        <button type="submit" class="picker-apply" :disabled="!selected||!!issue||loading||!!listError||busy||applying">{{ applying?'正在应用…':'应用并构场' }}</button>
      </footer>
    </form>
  </ModalDialog>
</template>

<style scoped>
.live-greenhouse-picker{font-size:14px;overflow-wrap:anywhere}
.live-greenhouse-picker h3{margin:0 0 16px;font-size:20px}
.live-greenhouse-picker label{display:grid;gap:8px;margin:14px 0}
.live-greenhouse-picker select,.live-greenhouse-picker button{min-height:36px;padding:6px 10px;border:1px solid var(--steel);border-radius:var(--radius);background:var(--card-2);color:var(--ink);font:inherit}
.live-greenhouse-picker select{width:100%}
.live-greenhouse-picker button{cursor:pointer}
.live-greenhouse-picker button:disabled{opacity:.5;cursor:default}
.live-greenhouse-picker footer{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap;margin-top:20px}
.live-greenhouse-picker a{margin-inline-end:auto;color:var(--edge)}
.picker-summary{margin:0;padding:4px 12px;border:var(--rule);border-radius:var(--radius)}
.picker-summary>div{display:flex;gap:12px;justify-content:space-between;padding:8px 0}
.picker-summary>div+div{border-top:var(--rule)}
.picker-summary dt,.picker-note{color:var(--ink-muted)}
.picker-summary dd{margin:0;text-align:end}
.picker-error{color:var(--bar)}
.live-greenhouse-picker .picker-apply{border-color:var(--edge);color:var(--edge);background:color-mix(in srgb,var(--edge) 9%,var(--card))}
</style>
