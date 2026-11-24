<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Icon from './Icon.vue'
import { ICON_PATHS } from '../design/icons'
import { polygons, type Coordinate, type LocationMapData, type MonitoringLocation } from '../live/monitoringLocation'

const props = defineProps<{ data: LocationMapData; selection: MonitoringLocation | null; focusCode?: string }>()
const emit = defineEmits<{ pick: [point: Coordinate] }>()
const svg = ref<SVGSVGElement | null>(null)
const viewport = ref({ x: 0, y: 0, width: 1000, height: 420 })
const rad = Math.PI / 180
function mercator([lon,lat]: Coordinate): Coordinate { return [lon*rad, -Math.log(Math.tan(Math.PI/4+lat*rad/2))] }
const projected = props.data.features.flatMap(f => polygons(f).flatMap(rings => rings.flat().map(mercator)))
const minX = Math.min(...projected.map(p=>p[0])), maxX = Math.max(...projected.map(p=>p[0]))
const minY = Math.min(...projected.map(p=>p[1])), maxY = Math.max(...projected.map(p=>p[1]))
const scale = Math.min(940/(maxX-minX),370/(maxY-minY))
const ox = (1000-(maxX-minX)*scale)/2, oy = (420-(maxY-minY)*scale)/2
function project(point: Coordinate): Coordinate { const p=mercator(point); return [(p[0]-minX)*scale+ox,(p[1]-minY)*scale+oy] }
function unproject(point: Coordinate): Coordinate { return [((point[0]-ox)/scale+minX)/rad,(2*Math.atan(Math.exp(-((point[1]-oy)/scale+minY)))-Math.PI/2)/rad] }
const paths = props.data.features.map(feature => ({ feature, path: polygons(feature).flatMap(rings => rings.map(ring => ring.map((point,i) => `${i?'L':'M'}${project(point).map(v=>v.toFixed(2)).join(',')}`).join(' ')+'Z')).join(' ') }))
const marker = computed(() => props.selection ? project([props.selection.longitude,props.selection.latitude]) : null)
const zoom = computed(() => 1000/viewport.value.width)
const viewBox = computed(() => `${viewport.value.x} ${viewport.value.y} ${viewport.value.width} ${viewport.value.height}`)
function focus() {
  const matches = props.data.features.filter(f => f.properties.code === props.focusCode || f.properties.city_code === props.focusCode)
  if (!matches.length) { viewport.value={x:0,y:0,width:1000,height:420}; return }
  const points=matches.flatMap(f=>polygons(f).flatMap(rings=>rings.flat().map(project)))
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1])
  const width=Math.min(1000,Math.max(150,(Math.max(...xs)-Math.min(...xs))*1.35,(Math.max(...ys)-Math.min(...ys))*1000/420*1.35))
  viewport.value={x:(Math.max(...xs)+Math.min(...xs)-width)/2,y:(Math.max(...ys)+Math.min(...ys)-width*420/1000)/2,width,height:width*420/1000}
}
watch(() => props.focusCode, focus, { immediate: true })
function zoomBy(factor: number, center?: Coordinate) {
  const old=viewport.value, width=Math.min(1000,Math.max(100,old.width/factor)), height=width*420/1000
  const p=center??[old.x+old.width/2,old.y+old.height/2]
  viewport.value={x:p[0]-(p[0]-old.x)*width/old.width,y:p[1]-(p[1]-old.y)*height/old.height,width,height}
}
function svgPoint(event: {clientX: number; clientY: number}): Coordinate | null {
  const matrix=svg.value?.getScreenCTM()
  if (!matrix || !svg.value) return null
  const p=svg.value.createSVGPoint();p.x=event.clientX;p.y=event.clientY
  const q=p.matrixTransform(matrix.inverse());return [q.x,q.y]
}
let gesture: {id: number; x: number; y: number; origin: typeof viewport.value; marker: boolean; moved: boolean} | null=null
function start(event: PointerEvent, pin=false) {
  if (event.button!==0) return
  gesture={id:event.pointerId,x:event.clientX,y:event.clientY,origin:{...viewport.value},marker:pin,moved:false}
  svg.value?.setPointerCapture?.(event.pointerId)
}
function move(event: PointerEvent) {
  if (!gesture || gesture.id!==event.pointerId || !svg.value) return
  if (Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y)>4) gesture.moved=true
  if (gesture.marker) { const p=svgPoint(event);if(p) emit('pick',unproject(p));return }
  const rect=svg.value.getBoundingClientRect(), pixelScale=Math.min(rect.width/gesture.origin.width,rect.height/gesture.origin.height)
  if (pixelScale>0) viewport.value={...gesture.origin,x:gesture.origin.x-(event.clientX-gesture.x)/pixelScale,y:gesture.origin.y-(event.clientY-gesture.y)/pixelScale}
}
function end(event: PointerEvent) {
  if (!gesture || gesture.id!==event.pointerId) return
  if (!gesture.moved && !gesture.marker) { const p=svgPoint(event);if(p) emit('pick',unproject(p)) }
  svg.value?.releasePointerCapture?.(event.pointerId);gesture=null
}
function wheel(event: WheelEvent) { const p=svgPoint(event);if(p) zoomBy(event.deltaY<0?1.2:1/1.2,p) }
function nudge(event: KeyboardEvent) {
  const directions: Record<string,Coordinate>={ArrowLeft:[-5,0],ArrowRight:[5,0],ArrowUp:[0,-5],ArrowDown:[0,5]}
  const delta=directions[event.key],p=marker.value
  if (delta && p) {event.preventDefault();emit('pick',unproject([p[0]+delta[0]/zoom.value,p[1]+delta[1]/zoom.value]))}
}
</script>
<template>
  <div class="location-map">
    <span class="map-caption">吉林省行政区地图</span>
    <svg ref="svg" class="map-canvas" :viewBox="viewBox" role="img" aria-label="吉林省监测地点地图，可点击选点并拖动缩放" @pointerdown="start($event)" @pointermove="move" @pointerup="end" @pointercancel="gesture=null" @wheel.prevent="wheel">
      <path v-for="item in paths" :key="item.feature.properties.code" :d="item.path" fill-rule="evenodd" class="district" :class="{chosen: selection?.district_code ? selection.district_code===item.feature.properties.code : selection?.city_code===item.feature.properties.city_code}"><title>{{item.feature.properties.city_name}} · {{item.feature.properties.name}}</title></path>
      <template v-if="!selection"><g v-for="city in data.cities" :key="`city-${city.code}`" :transform="`translate(${project(city.center).join(',')}) scale(${1/zoom})`" class="map-label"><text text-anchor="middle">{{data.features.find(f=>f.properties.city_code===String(city.code))?.properties.city_name}}</text></g></template>
      <g v-for="item in data.features.filter(f=>f.properties.city_code===selection?.city_code && f.properties.code!==selection?.district_code)" :key="`label-${item.properties.code}`" :transform="`translate(${project(item.properties.center).join(',')}) scale(${1/zoom})`" class="map-label"><text text-anchor="middle">{{item.properties.name}}</text></g>
      <g v-if="marker" :transform="`translate(${marker.join(',')}) scale(${1/zoom})`" class="map-marker" tabindex="0" role="button" aria-label="监测地点标记，可拖动或使用方向键微调" @pointerdown.stop="start($event,true)" @keydown="nudge"><circle r="30" class="marker-halo"/><path :d="ICON_PATHS.location" transform="translate(-18,-42) scale(1.5)"/><text y="22" text-anchor="middle">{{selection?.district_name || selection?.city_name}}</text></g>
    </svg>
    <div class="map-tools"><button type="button" aria-label="放大地图" :disabled="zoom>=10" @click="zoomBy(1.5)"><Icon name="plus"/></button><button type="button" aria-label="缩小地图" :disabled="zoom<=1" @click="zoomBy(1/1.5)">−</button><button type="button" aria-label="重置地图" @click="focus"><Icon name="reset"/></button></div>
    <a class="map-source" href="https://datav.aliyun.com/portal/school/atlas/area_selector" target="_blank" rel="noopener noreferrer">边界数据：DataV.GeoAtlas</a>
  </div>
</template>
<style scoped>
.location-map {position:relative;min-height:0;overflow:hidden;border:1px solid var(--interact);border-radius:8px;background:radial-gradient(ellipse at center,color-mix(in srgb,var(--edge) 10%,var(--card)),var(--paper));}
.map-canvas {display:block;width:100%;height:100%;min-height:230px;touch-action:none;cursor:grab;user-select:none;}.map-canvas:active{cursor:grabbing;}.district{fill:color-mix(in srgb,var(--interact) 12%,var(--card));stroke:color-mix(in srgb,var(--edge) 45%,var(--steel));stroke-width:.8;vector-effect:non-scaling-stroke;}.district:hover{fill:color-mix(in srgb,var(--interact) 28%,var(--card));}.district.chosen{fill:color-mix(in srgb,var(--edge) 22%,var(--card));stroke:var(--edge);stroke-width:1.2;}.map-caption{position:absolute;top:12px;left:12px;z-index:1;padding:5px 10px;border:var(--rule);border-radius:5px;background:var(--card);color:var(--ink-muted);font-size:11px;pointer-events:none;}.map-label{pointer-events:none;fill:var(--ink-muted);font-size:14px;}.map-marker{cursor:move;fill:var(--ink);font-size:16px;font-weight:var(--w-strong);}.map-marker path{fill:var(--edge);stroke:var(--card);stroke-width:1.2;}.marker-halo{fill:var(--edge);opacity:.1;}.map-marker text{paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round;}.map-tools{position:absolute;right:14px;bottom:32px;display:grid;gap:0;border:1px solid var(--interact);border-radius:6px;overflow:hidden;}.map-tools button{display:grid;place-items:center;width:34px;height:34px;min-height:0;padding:6px;border:0;border-radius:0;background:var(--card);color:var(--ink);font-size:22px;}.map-tools button+button{border-top:var(--rule);}.map-tools :deep(.icon){--icon-size:18px;}.map-source{position:absolute;right:8px;bottom:5px;font-size:10px;color:var(--ink-muted);text-decoration:none;}
</style>
