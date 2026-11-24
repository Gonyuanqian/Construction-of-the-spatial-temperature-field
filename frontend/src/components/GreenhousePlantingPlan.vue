<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,useId} from 'vue'
import type {DesignSpec,DesignPreview} from '../api/greenhouseDesigns'
import {bearingName} from '../greenhouse/orientation'
const props=defineProps<{spec:DesignSpec;layout:DesignPreview;selected?:number;manual?:boolean}>()
const emit=defineEmits<{select:[index:number];move:[point:{x:number;y:number}]}>()
const root=ref<HTMLDivElement>(),available=ref(650),showCoverage=ref(true),id=useId().replaceAll(':',''),arrow=`plan-arrow-${id}`,clip=`plan-bound-${id}`
let observer:ResizeObserver|undefined
onMounted(()=>{if(root.value&&typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(entries=>{const value=entries[0]?.contentRect.width;if(value)available.value=value});observer.observe(root.value)}})
onUnmounted(()=>observer?.disconnect())
const W=computed(()=>props.spec.structure.type==='multi_span'?props.spec.structure.span_width_m*props.spec.structure.span_count:props.spec.structure.width_m),L=computed(()=>props.spec.structure.length_m)
const narrow=computed(()=>available.value<480),left=computed(()=>narrow.value?38:52),right=computed(()=>narrow.value?42:62)
const scale=computed(()=>Math.min((available.value-left.value-right.value)/L.value,300/W.value)),plotW=computed(()=>L.value*scale.value),plotH=computed(()=>W.value*scale.value)
const offset=computed(()=>left.value+(available.value-left.value-right.value-plotW.value)/2),plotY=78
const px=(y:number)=>offset.value+y*scale.value,py=(x:number)=>plotY+x*scale.value
const figureHeight=computed(()=>plotY+plotH.value+72),front=computed(()=>props.spec.planting.front_passage_m),rear=computed(()=>props.spec.planting.rear_passage_m)
const plantMarks=computed(()=>{const total=props.layout.plant_count,step=Math.max(1,Math.ceil(total/1500)),points:{x:number;y:number}[]=[];for(const row of props.layout.rows){const spacing=(row.y_end-row.y_start)/Math.max(1,row.plant_count);for(let i=0;i<row.plant_count&&points.length<1500;i+=step)points.push({x:row.x,y:row.y_start+(i+.5)*spacing})}return points})
const firstRows=computed(()=>props.layout.rows.slice(0,2)),firstBed=computed(()=>props.layout.beds[0])
function move(event:MouseEvent){if(!props.manual||props.selected===undefined||props.selected<0)return;const svg=event.currentTarget as SVGSVGElement,point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;const inverse=svg.getScreenCTM()?.inverse();if(!inverse)return;const p=point.matrixTransform(inverse);emit('move',{x:Number(((p.y-plotY)/scale.value).toFixed(2)),y:Number(((p.x-offset.value)/scale.value).toFixed(2))})}
</script>
<template><div ref="root" class="planting-plan">
 <div class="plan-tools"><label><input v-model="showCoverage" type="checkbox">显示喷灌覆盖</label><span class="plan-north">北 N <b :style="{transform:`rotate(${(270-spec.location.opening_azimuth+360)%360}deg)`}">↑</b></span></div>
 <svg :viewBox="`0 0 ${available} ${figureHeight}`" :style="{height:figureHeight+'px'}" role="img" aria-label="种植带、通道、灌溉设备及补光灯位置示意" @click="move">
  <title>种植与设备布局，横向为棚长，纵向为棚宽，植株位置抽样显示</title>
  <defs><marker :id="arrow" viewBox="0 0 8 8" markerWidth="6" markerHeight="6" refX="4" refY="4" orient="auto-start-reverse"><path d="M0 0L8 4L0 8Z" class="arrow-head"/></marker><clipPath :id="clip"><rect :x="px(0)-8" :y="plotY-8" :width="plotW+16" :height="plotH+16"/></clipPath></defs>
  <line :x1="px(0)" :x2="px(L)" y1="30" y2="30" class="dimension" :marker-start="`url(#${arrow})`" :marker-end="`url(#${arrow})`"/><text :x="px(L/2)" y="17" text-anchor="middle" class="total-length">棚长 {{L.toFixed(1)}} m</text>
  <text :x="px(0)" y="59">前端 · {{bearingName(spec.location.opening_azimuth)}}</text><text :x="px(L)" y="59" text-anchor="end">后端 · {{bearingName((spec.location.opening_azimuth+180)%360)}}</text>
  <line :x1="px(0)-25" :x2="px(0)-25" :y1="plotY" :y2="plotY+plotH" class="dimension" :marker-start="`url(#${arrow})`" :marker-end="`url(#${arrow})`"/><text :transform="`translate(${px(0)-35},${plotY+plotH/2}) rotate(-90)`" text-anchor="middle">棚宽 {{W.toFixed(1)}} m</text>
  <rect :x="px(0)" :y="plotY" :width="plotW" :height="plotH" class="ground"/>
  <rect :x="px(0)" :y="plotY" :width="Math.min(front,L)*scale" :height="plotH" class="passage"/><rect :x="px(Math.max(0,L-rear))" :y="plotY" :width="Math.min(rear,L)*scale" :height="plotH" class="passage"/>
  <g v-for="(b,index) in layout.beds" :key="index"><rect :x="px(b.y)" :y="py(b.x)" :width="b.length*scale" :height="b.width*scale" class="bed"/>
   <template v-if="!narrow&&b.width*scale>20"><line :x1="px(L)+12" :x2="px(L)+12" :y1="py(b.x)" :y2="py(b.x+b.width)" class="dimension" :marker-start="`url(#${arrow})`" :marker-end="`url(#${arrow})`"/><text :x="px(L)+20" :y="py(b.x+b.width/2)-3" class="band-label"><tspan :x="px(L)+20">带宽</tspan><tspan :x="px(L)+20" dy="14">{{b.width.toFixed(2)}} m</tspan></text></template>
  </g>
  <circle v-for="(p,n) in plantMarks" :key="n" :cx="px(p.y)" :cy="py(p.x)" :r="narrow?1.2:1.65" class="plant"/>
  <g v-if="spec.irrigation.drip_enabled"><line v-for="(r,n) in layout.rows" :key="n" :x1="px(r.y_start)" :x2="px(r.y_end)" :y1="py(r.x)" :y2="py(r.x)" class="pipe"/></g>
  <g :clip-path="`url(#${clip})`"><g v-for="(p,n) in layout.sprinklers" :key="n"><circle v-if="showCoverage" :cx="px(p.y)" :cy="py(p.x)" :r="spec.irrigation.coverage_radius_m*scale" class="coverage"/><circle :cx="px(p.y)" :cy="py(p.x)" :r="selected===n?6:4" class="nozzle" @click.stop="emit('select',n)"/></g></g>
  <rect v-for="light in layout.lights" :key="`${light.x}:${light.y}`"
        :x="px(light.y)-5" :y="py(light.x)-2" width="10" height="4" rx="1" class="lamp-position" />
  <g v-if="!narrow&&firstBed&&firstRows.length>1" class="spacing-labels">
   <text :x="px(L*.27)" :y="plotY-5" text-anchor="middle">株距 {{(spec.planting.plant_spacing_m*100).toFixed(0)}} cm</text><line :x1="px(L*.27)" :x2="px(L*.27)" :y1="plotY" :y2="py(firstRows[0]!.x)-5" class="leader"/>
   <line :x1="px(L*.27)" :x2="px(L*.27+spec.planting.plant_spacing_m)" :y1="py(firstRows[0]!.x)" :y2="py(firstRows[0]!.x)" class="dimension" :marker-start="`url(#${arrow})`" :marker-end="`url(#${arrow})`"/>
   <text :x="px(L*.65)" :y="plotY-5" text-anchor="middle">中心行距 {{(spec.planting.row_spacing_m*100).toFixed(0)}} cm</text><line :x1="px(L*.65)" :x2="px(L*.65)" :y1="plotY" :y2="py(firstRows[0]!.x)-5" class="leader"/>
   <line :x1="px(L*.65)" :x2="px(L*.65)" :y1="py(firstRows[0]!.x)" :y2="py(firstRows[1]!.x)" class="dimension" :marker-start="`url(#${arrow})`" :marker-end="`url(#${arrow})`"/>
  </g>
  <line :x1="px(0)" :x2="px(Math.min(front,L))" :y1="plotY+plotH+16" :y2="plotY+plotH+16" class="dimension"/><line :x1="px(Math.max(0,L-rear))" :x2="px(L)" :y1="plotY+plotH+16" :y2="plotY+plotH+16" class="dimension"/>
  <text :x="px(0)" :y="plotY+plotH+34">前通道 {{front.toFixed(2)}} m</text><text :x="px(L)" :y="plotY+plotH+34" text-anchor="end">后通道 {{rear.toFixed(2)}} m</text>
  <text :x="px(L/2)" :y="figureHeight-7" text-anchor="middle" class="usable-length">有效种植长度 {{layout.usable_length_m.toFixed(2)}} m</text>
 </svg>
 <div class="plan-legend"><span class="legend-bed">种植带</span><span class="legend-pipe">滴灌管线</span><span class="legend-nozzle">喷头</span><span class="legend-coverage">标称覆盖范围</span><span v-if="layout.lights?.length" class="legend-lamp">补光灯</span></div>
 <p class="plan-note">{{narrow?`株距 ${(spec.planting.plant_spacing_m*100).toFixed(0)} cm · 中心行距 ${(spec.planting.row_spacing_m*100).toFixed(0)} cm · `:''}}植株抽样显示；喷灌覆盖未考虑水压与遮挡。</p>
 </div></template>
<style scoped>
.lamp-position{fill:var(--control-amber);stroke:var(--paper);stroke-width:.6;pointer-events:none}
.plan-legend .legend-lamp:before{height:4px;background:var(--control-amber)}
.planting-plan{width:100%;min-width:0;padding:8px 0 4px}.planting-plan svg{display:block;width:100%;overflow:visible}.plan-tools{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;color:var(--ink-muted);margin-bottom:4px}.plan-tools label{display:flex;align-items:center;gap:6px;cursor:pointer}.plan-tools input{accent-color:var(--interact)}.plan-north{display:flex;align-items:center;gap:7px;color:var(--ink)}.plan-north b{font-size:22px;display:inline-block;line-height:1;font-weight:var(--w-body)}
.ground{fill:var(--design-soil);stroke:var(--design-frame);stroke-width:1.5}.passage{fill:var(--design-path)}.bed{fill:var(--design-plant);fill-opacity:.35;stroke:var(--design-plant);stroke-width:.7}.plant{fill:var(--design-plant-light)}.pipe{stroke:var(--edge);stroke-width:1;stroke-opacity:.8}.coverage{fill:none;stroke:var(--edge);stroke-width:1;stroke-dasharray:5 4;opacity:.4;pointer-events:none}.nozzle{fill:var(--edge);stroke:var(--paper);stroke-width:1;cursor:pointer}.dimension{fill:none;stroke:var(--design-frame);stroke-width:1}.arrow-head{fill:var(--design-frame)}.leader{stroke:var(--design-frame);stroke-width:.8;stroke-dasharray:2 3;opacity:.8}text{font-family:var(--font-cn);font-size:12px;fill:var(--ink)}.total-length,.usable-length{font-size:14px;font-weight:var(--w-strong)}.band-label{font-size:11px}.spacing-labels text{paint-order:stroke;stroke:var(--card);stroke-width:5px;stroke-linejoin:round}
.plan-legend{display:flex;justify-content:center;gap:14px;flex-wrap:wrap;padding:10px 7px;border:1px solid var(--steel);border-radius:4px;color:var(--ink-muted);font-size:12px;margin-top:12px}.plan-legend span{display:flex;align-items:center;gap:6px}.plan-legend span:before{content:'';display:inline-block;width:14px;height:3px;background:var(--edge)}.plan-legend .legend-bed:before{height:10px;background:var(--design-plant)}.plan-legend .legend-nozzle:before{width:9px;height:9px;border-radius:50%}.plan-legend .legend-coverage:before{height:11px;width:11px;border:1px dashed var(--edge);background:transparent;border-radius:50%}.plan-note{font-size:11px;color:var(--ink-muted);text-align:center;margin:9px 0 0}
</style>
