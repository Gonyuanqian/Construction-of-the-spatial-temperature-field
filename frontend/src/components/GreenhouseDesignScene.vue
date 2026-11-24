<script setup lang="ts">
import {computed,onMounted,onUnmounted,onActivated,onDeactivated,ref,watch} from 'vue'
import * as THREE from 'three'
import {OrbitControls} from 'three/examples/jsm/controls/OrbitControls.js'
import {buildDesignModel,disposeDesignModel} from '../greenhouse/designScene'
import {bearingName} from '../greenhouse/orientation'
import type {DesignSpec,DesignPreview} from '../api/greenhouseDesigns'
import type {ControlDevice,DeviceKind} from '../api/greenhouseControl'
import {buildControlOverlay} from '../greenhouse/controlScene'
import {zoneLabel} from '../greenhouse/control'

const props=defineProps<{
 spec:DesignSpec
 layout:DesignPreview
 topView?:boolean
 control?:{geometryKey:string;devices:ControlDevice[];film:boolean;labels:boolean;focused:DeviceKind|null;selectedId:string|null}
}>()
const emit=defineEmits<{unavailable:[];select:[device:ControlDevice]}>()
const host=ref<HTMLDivElement>(),error=ref(''),labelHost=ref<HTMLDivElement>(),deviceLabelHost=ref<HTMLDivElement>(),compass=ref<HTMLSpanElement>()
let renderer:THREE.WebGLRenderer|undefined,scene:THREE.Scene,camera:THREE.PerspectiveCamera,controls:OrbitControls,observer:ResizeObserver,frame=0,live=true
let model:ReturnType<typeof buildDesignModel>|undefined
let overlay:ReturnType<typeof buildControlOverlay>|undefined
const projected = new THREE.Vector3()
let coverOpacity = 0
const metrics=ref({length:0,width:0,height:0})
const displayedDevices=computed(()=>{
 const control=props.control
 if(!control?.labels)return []
 const selected=control.devices.find(d=>d.id===control.selectedId)
 const focused=control.devices.find(d=>d.kind===control.focused)
 const candidates=[selected??focused,...control.devices.filter(d=>d.enabled&&d.state.running)]
 const seen=new Set<string>()
 return candidates.filter((device):device is ControlDevice=>{
  if(!device)return false
  const group=device.kind+':'+device.zone_key
  if(seen.has(group))return false
  seen.add(group)
  return true
 }).slice(0,6)
})
function fit(reset=false){
 if(!host.value||!renderer||!model)return
 const w=host.value.clientWidth,h=host.value.clientHeight;if(!w||!h)return
 renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()
 const center=model.bounds.getCenter(new THREE.Vector3()),direction=reset?(props.topView?new THREE.Vector3(0,1,.0001):new THREE.Vector3(-1,.7,-1.1)).normalize():camera.position.clone().sub(controls.target).normalize()
 camera.position.copy(center).add(direction);camera.lookAt(center);camera.updateMatrixWorld(true)
 const rotation=new THREE.Matrix4().extractRotation(camera.matrixWorld).invert(),tanV=Math.tan(THREE.MathUtils.degToRad(camera.fov)/2),tanH=tanV*camera.aspect
 let distance=.5
 const box=model.bounds
 for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){const q=new THREE.Vector3(x,y,z).sub(center).applyMatrix4(rotation);distance=Math.max(distance,q.z+Math.abs(q.x)/(tanH*.86),q.z+Math.abs(q.y)/(tanV*.86))}
 controls.target.copy(center);camera.position.copy(center).addScaledVector(direction,distance*1.02);camera.updateMatrixWorld(true);controls.update()
}
function rebuild(){
 if(!renderer||!host.value)return
 overlay?.dispose();overlay=undefined
 if(model){scene.remove(model.root);disposeDesignModel(model.root)}
 const css=getComputedStyle(document.documentElement),color=(name:string)=>css.getPropertyValue(name).trim()
 scene.background=new THREE.Color(color('--card'))
 model=buildDesignModel(props.spec,props.layout,{ground:color('--card-2'),frame:color('--design-frame'),cover:color('--design-cover'),soil:color('--design-soil'),path:color('--design-path'),plant:color('--design-plant'),plantLight:color('--design-plant-light'),pipe:color('--edge'),lamp:color('--control-amber')},!props.control)
 coverOpacity=model.covering.opacity
 if(props.control){
  overlay=buildControlOverlay(props.spec,props.layout,model,{frame:color('--design-frame'),water:color('--edge'),lamp:color('--control-amber')})
  scene.add(overlay.root)
  syncDevices()
 }
 scene.add(model.root);metrics.value={length:model.length,width:model.width,height:model.height};camera.far=Math.max(model.width,model.length,model.height)*50;fit(true)
}
function syncDevices(){
 if(!props.control||!model)return
 model.covering.opacity=props.control.film?coverOpacity:0
 overlay?.update(props.control.devices)
}
function resetView(){fit(true)}
defineExpose({resetView})
function annotations(){
 if(!model||!host.value)return
 const width=host.value.clientWidth,height=host.value.clientHeight
 for(const node of labelHost.value?.querySelectorAll<HTMLElement>('[data-anchor]')??[]){
  const key=node.dataset.anchor as keyof typeof model.dimensions,p=model.dimensions[key].clone().project(camera)
  node.style.left=Math.min(width-55,Math.max(55,(p.x+1)*width/2))+'px';node.style.top=Math.min(height-22,Math.max(25,(-p.y+1)*height/2))+'px';node.style.visibility=p.z>1||p.z< -1?'hidden':'visible'
 }
 const devices=displayedDevices.value
 for(const node of deviceLabelHost.value?.querySelectorAll<HTMLElement>('[data-device]')??[]){
  const device=devices.find(d=>d.id===node.dataset.device)
  const anchor=device&&overlay?.anchorFor(device)
  if(!anchor){node.style.visibility='hidden';continue}
  projected.copy(anchor).project(camera)
  const outside=projected.z>1||projected.z< -1||Math.abs(projected.x)>1||Math.abs(projected.y)>1
  const side=node.offsetWidth/2+6
  node.style.left=Math.min(width-side,Math.max(side,(projected.x+1)*width/2))+'px'
  node.style.top=Math.max(node.offsetHeight+10,(-projected.y+1)*height/2)+'px'
  node.style.visibility=outside?'hidden':'visible'
 }
 if(compass.value){const a=props.spec.location.opening_azimuth*Math.PI/180,center=controls.target.clone(),north=center.clone().add(new THREE.Vector3(Math.sin(a),0,-Math.cos(a)));const p=center.project(camera),n=north.project(camera);compass.value.style.transform=`rotate(${Math.atan2(n.x-p.x,n.y-p.y)*180/Math.PI}deg)`}
}
function animate(time=performance.now()){
 if(!live||!renderer)return
 controls.update()
 overlay?.animate(time/1000)
 renderer.render(scene,camera)
 annotations()
 frame=requestAnimationFrame(animate)
}
function unavailable(){
 live=false
 cancelAnimationFrame(frame)
 error.value='当前浏览器无法显示三维预览，请使用二维平面。'
 emit('unavailable')
}
onMounted(()=>{try{
 if(!host.value)return
 renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;host.value.prepend(renderer.domElement)
 renderer.domElement.addEventListener('webglcontextlost',unavailable)
 scene=new THREE.Scene();scene.add(new THREE.HemisphereLight(0xffffff,0x607080,2));const light=new THREE.DirectionalLight(0xffffff,2.7);light.position.set(8,15,-8);scene.add(light)
 camera=new THREE.PerspectiveCamera(36,1,.01,1000);controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.maxPolarAngle=Math.PI*.49
 observer=new ResizeObserver(()=>fit());observer.observe(host.value);rebuild();animate()
 }catch{unavailable()}})
watch([
 ()=>props.control?.geometryKey??props.spec,
 ()=>props.control?null:props.layout,
 ()=>props.topView,
],rebuild)
watch([()=>props.control?.devices,()=>props.control?.film],syncDevices)
onActivated(()=>{live=true;if(renderer&&!frame)animate()})
onDeactivated(()=>{live=false;cancelAnimationFrame(frame);frame=0})
onUnmounted(()=>{
 live=false
 cancelAnimationFrame(frame)
 observer?.disconnect();controls?.dispose();overlay?.dispose()
 if(model)disposeDesignModel(model.root)
 renderer?.domElement.removeEventListener('webglcontextlost',unavailable)
 renderer?.dispose();renderer?.domElement.remove()
})
</script>
<template><div ref="host" class="design-scene" :role="control?'group':'img'" :aria-label="control?'三维棚内设备模拟场景':'棚体、植株、灌溉设备和补光灯的三维预览'">
 <p v-if="error" role="status" class="scene-error">{{error}}</p>
 <template v-else><div class="scene-compass"><span>北 N</span><span ref="compass" class="north-arrow">↑</span></div>
 <div ref="labelHost" class="dimension-labels"><span data-anchor="length">棚长 {{metrics.length.toFixed(1)}} m</span><span data-anchor="width">棚宽 {{metrics.width.toFixed(1)}} m</span><span data-anchor="height">{{spec.structure.type==='multi_span'?'总高':'拱高'}} {{metrics.height.toFixed(1)}} m</span><span data-anchor="entrance" class="entrance-label">前端开口 · {{bearingName(spec.location.opening_azimuth)}}</span></div>
 <div v-if="control" ref="deviceLabelHost" class="device-labels">
  <button v-for="device in displayedDevices" :key="device.id" type="button" :data-device="device.id"
    :class="{running:device.enabled&&device.state.running,light:device.kind==='lighting'}"
    @click="emit('select',device)">
   <strong>{{device.name}} · {{zoneLabel(device.zone_key)}}</strong>
   <span>{{!device.enabled?'已停用':device.state.running?'模拟运行':'已关闭'}}<template v-if="device.state.running&&device.kind==='lighting'&&device.state.brightness_percent"> · {{device.state.brightness_percent}}%</template></span>
  </button>
 </div></template>
 </div></template>
<style scoped>
.design-scene{height:100%;min-height:360px;width:100%;position:relative;overflow:hidden}.design-scene :deep(canvas){display:block;width:100%;height:100%;touch-action:none}.scene-error{padding:28px;color:var(--ink-muted)}.scene-compass{position:absolute;left:14px;top:12px;display:grid;place-items:center;font-size:12px;color:var(--ink);pointer-events:none;gap:2px}.north-arrow{font-size:27px;line-height:1;transform-origin:center}.dimension-labels{position:absolute;inset:0;pointer-events:none}.dimension-labels>span{position:absolute;transform:translate(-50%,-50%);white-space:nowrap;font-size:12px;background:color-mix(in srgb,var(--card) 75%,transparent);padding:3px 5px;border-radius:3px;color:var(--ink);font-variant-numeric:tabular-nums}.dimension-labels>.entrance-label{background:var(--design-frame);color:var(--paper);font-size:11px}
.device-labels{position:absolute;inset:0;pointer-events:none}
.device-labels button{position:absolute;visibility:hidden;transform:translate(-50%,-100%);pointer-events:auto;display:grid;gap:3px;text-align:left;font-size:11px;padding:5px 8px;white-space:nowrap;max-width:min(200px,75%);border-color:var(--edge-line);background:var(--card)}
.device-labels strong{overflow:hidden;text-overflow:ellipsis}
.device-labels button.running{border-color:var(--edge);color:var(--edge)}
.device-labels button.running.light{border-color:var(--control-amber);color:var(--control-amber)}
</style>
