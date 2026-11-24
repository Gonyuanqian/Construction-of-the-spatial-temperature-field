<script setup lang="ts">
import {computed,ref,useId} from 'vue'
import type {ControlOverview,DeviceKind} from '../api/greenhouseControl'
import Icon from './Icon.vue'
import {ICON_PATHS} from '../design/icons'
import {kinds,kindIcons} from '../greenhouse/control'
const props=defineProps<{overview:ControlOverview;focused:DeviceKind|null;embedded?:boolean}>()
const emit=defineEmits<{select:[kind:DeviceKind]}>()
const filter=ref('all'),pattern='control-plants-'+useId().replaceAll(':','')
const L=computed(()=>props.overview.spec.structure.length_m),W=computed(()=>props.overview.spec.structure.width_m)
const scale=computed(()=>Math.min(800/L.value,350/W.value)),width=computed(()=>L.value*scale.value),height=computed(()=>W.value*scale.value)
const x=(y:number)=>100+(800-width.value)/2+y*scale.value,y=(x:number)=>95+x*scale.value
const show=(kind:DeviceKind)=>props.overview.devices.some(d=>d.kind===kind)&&(filter.value==='all'||filter.value===kind)
const rows=computed(()=>props.overview.layout.rows.filter((_,i)=>i%Math.max(1,Math.ceil(props.overview.layout.rows.length/80))===0))
const lamps=computed(()=>props.overview.layout.beds.flatMap(b=>[.18,.42,.66,.88].map(n=>({x:x(b.y+b.length*n),y:y(b.x+b.width/2)}))))
</script>
<template>
 <section class="floor-panel" :class="{'control-panel':!embedded}" :aria-label="embedded?'棚内设备二维平面':'棚内设备布局'">
  <header class="panel-heading"><h2 v-if="!embedded">棚内设备布局</h2><select v-model="filter" aria-label="布局设备筛选"><option value="all">全部设备</option><option v-for="k in kinds" :key="k" :value="k">{{{drip:'滴灌',sprinkler:'喷灌',ventilation:'通风',lighting:'补光'}[k]}}</option></select></header>
  <div class="floor-art"><svg viewBox="0 0 1000 560" role="img" aria-label="根据保存方案生成的种植带和设备符号示意">
   <defs><pattern :id="pattern" width="20" height="17" patternUnits="userSpaceOnUse"><path d="M10 14C1 12 1 3 9 7C11-1 20 3 15 10Z" class="plant-mark"/></pattern></defs>
   <path :d="`M${x(0)} 62H${x(L)} M${x(0)} 54v16 M${x(L)} 54v16`" class="measure"/><text :x="x(L/2)" y="47" text-anchor="middle">{{L}} m</text>
   <path :d="`M${x(0)-32} 95V${y(W)} M${x(0)-40} 95h16 M${x(0)-40} ${y(W)}h16`" class="measure"/><text :x="x(0)-46" :y="y(W/2)" text-anchor="end">{{W}} m</text>
   <rect :x="x(0)" :y="y(0)" :width="width" :height="height" rx="7" class="house-floor"/>
   <g v-for="(b,i) in overview.layout.beds" :key="i"><rect :x="x(b.y)" :y="y(b.x)" :width="b.length*scale" :height="b.width*scale" class="bed"/><rect :x="x(b.y)" :y="y(b.x)" :width="b.length*scale" :height="b.width*scale" :fill="`url(#${pattern})`"/></g>
   <g v-if="show('drip')" class="device-mark drip" :class="{highlight:focused==='drip'}" role="button" tabindex="0" aria-label="查看滴灌设备" @click="emit('select','drip')" @keydown.enter="emit('select','drip')"><line v-for="(r,i) in rows" :key="i" :x1="x(r.y_start)" :x2="x(r.y_end)" :y1="y(r.x)" :y2="y(r.x)"/></g>
   <g v-if="show('sprinkler')" class="device-mark spray" :class="{highlight:focused==='sprinkler'}" role="button" tabindex="0" aria-label="查看喷灌设备" @click="emit('select','sprinkler')" @keydown.enter="emit('select','sprinkler')"><g v-for="(p,i) in overview.layout.sprinklers.slice(0,40)" :key="i"><circle :cx="x(p.y)" :cy="y(p.x)" :r="Math.min(overview.spec.irrigation.coverage_radius_m*scale,60)"/><circle :cx="x(p.y)" :cy="y(p.x)" r="4" class="nozzle"/></g></g>
   <g v-if="show('lighting')" class="device-mark lamps" :class="{highlight:focused==='lighting'}" role="button" tabindex="0" aria-label="查看补光设备" @click="emit('select','lighting')" @keydown.enter="emit('select','lighting')"><rect v-for="(p,i) in lamps" :key="i" :x="p.x-11" :y="p.y-4" width="22" height="8" rx="2"/></g>
   <g v-if="show('ventilation')" class="device-mark fans" role="button" tabindex="0" aria-label="查看通风设备" @click="emit('select','ventilation')" @keydown.enter="emit('select','ventilation')"><g v-for="dx in [x(0),x(L)]" :key="dx" :transform="`translate(${dx-14},${y(W/2)-14}) scale(1.2)`"><circle cx="12" cy="12" r="14" class="fan-face"/><path :d="ICON_PATHS.fan"/></g></g>
   <path :d="`M${x(L/2)-23} ${y(W)}v32h46v-32 M${x(L/2)} ${y(W)}v32`" class="door"/><text :x="x(L/2)" :y="y(W)+54" text-anchor="middle">入口示意</text>
  </svg></div>
  <div class="floor-legend"><button v-for="k in kinds" :key="k" :aria-pressed="focused===k" @click="emit('select',k)"><Icon :name="kindIcons[k]"/>{{{drip:'滴灌',sprinkler:'喷灌',ventilation:'通风',lighting:'补光'}[k]}}</button></div>
  <p class="muted floor-note">点击图例查看设备。符号位置为示意，A/B 为控制分组。</p>
 </section>
</template>
<style scoped>
section:not(.control-panel)>.panel-heading{padding:12px 0 0;border:0;justify-content:flex-end}
.floor-panel{display:flex;flex-direction:column;min-width:0}.floor-art{flex:1;display:grid;align-items:center;min-height:290px;padding:5px 0}.floor-art svg{display:block;width:100%;max-height:480px}text{fill:var(--ink);font-family:var(--font-cn);font-size:20px}.measure{stroke:var(--design-frame);fill:none;stroke-width:1.5}.house-floor{fill:var(--design-path);fill-opacity:.28;stroke:var(--design-frame);stroke-width:6}.bed{fill:var(--design-soil);stroke:var(--design-plant);stroke-width:1}.plant-mark{fill:var(--design-plant);stroke:var(--design-plant-light);stroke-width:.6}.device-mark{cursor:pointer;outline:none}.device-mark:focus-visible{filter:drop-shadow(0 0 4px var(--edge))}.drip line{stroke:var(--edge);stroke-width:2.8}.spray circle{fill:none;stroke:var(--edge);stroke-width:1.5;stroke-dasharray:6 4;opacity:.5}.spray .nozzle{fill:var(--edge);opacity:1;stroke-dasharray:none}.lamps rect{fill:var(--control-amber);stroke:var(--on-face);stroke-width:1}.fans path{fill:none;stroke:var(--ink);stroke-width:1.4}.fan-face{fill:var(--card);stroke:var(--design-frame);stroke-width:1}.door{fill:none;stroke:var(--design-frame);stroke-width:2}.highlight{filter:drop-shadow(0 0 3px var(--edge))}.floor-legend{border-top:1px solid var(--edge-line);padding-top:14px;display:flex;justify-content:center;gap:12px;flex-wrap:wrap}.floor-legend button{display:flex;gap:7px;align-items:center;border:0;background:none;font-size:13px;padding:3px}.floor-legend svg{width:20px;height:20px;color:var(--edge)}.floor-legend button:last-child svg{color:var(--control-amber)}.floor-legend [aria-pressed=true]{color:var(--edge)}.floor-note{text-align:center;font-size:11px;margin:12px 0 0}
</style>
