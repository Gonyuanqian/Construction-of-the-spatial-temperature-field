<script setup lang="ts">
import {computed,defineAsyncComponent,onUnmounted,reactive,ref,watch} from 'vue'
import {useRouter} from 'vue-router'
import {bearingName} from '../greenhouse/orientation'
import {designsApi,newDesign,type DesignSpec,type DesignRecord,type DesignPreview} from '../api/greenhouseDesigns'
import {session} from '../api/session'
import type {MonitoringLocation} from '../live/monitoringLocation'
import {regionText} from '../api/regions'
import Icon from '../components/Icon.vue'
import DesignInspectionPanel from '../components/DesignInspectionPanel.vue'
import MonitoringLocationDialog from '../components/MonitoringLocationDialog.vue'
import GreenhousePlantingPlan from '../components/GreenhousePlantingPlan.vue'
import ModalDialog from '../components/ModalDialog.vue'
const GreenhouseDesignScene=defineAsyncComponent(()=>import('../components/GreenhouseDesignScene.vue').then(m=>m.default))
defineOptions({name:'GreenhouseDesignView'})
const router=useRouter(),draft=reactive(newDesign()),record=ref<DesignRecord|null>(null),items=ref<DesignRecord[]>([])
const preview=ref<DesignPreview|null>(null),previewSpec=ref<DesignSpec|null>(null),error=ref(''),previewError=ref(''),message=ref('')
const saving=ref(false),loading=ref(false),previewing=ref(false),locationOpen=ref(false),topView=ref(false),selected=ref(-1),saved=ref('')
const deleteTarget=ref<DesignRecord|null>(null),deleting=ref(false),deleteError=ref('')
let alive=true,generation=0,ownerGeneration=0,timer:ReturnType<typeof setTimeout>|undefined
const clone=<T,>(v:T):T=>JSON.parse(JSON.stringify(v))
const dirty=computed(()=>JSON.stringify(draft)!==saved.value)
const busy=computed(()=>saving.value||loading.value||deleting.value)
const width=computed(()=>draft.structure.type==='multi_span'?draft.structure.span_width_m*draft.structure.span_count:draft.structure.width_m)
const location=computed(()=>draft.location.city_code&&draft.location.longitude!==null&&draft.location.latitude!==null?draft.location as MonitoringLocation:null)
const currentPreview=computed(()=>previewSpec.value&&JSON.stringify(previewSpec.value)===JSON.stringify(draft))
const modelSupported=computed(()=>preview.value?.model.monitoring_supported&&currentPreview.value)
const cropFields=[{key:'band_width_m',label:'栽培带宽 / m',factor:1,step:.05,min:.2,max:10},{key:'plant_spacing_m',label:'植株间距 / cm',factor:100,step:1,min:5,max:200},{key:'row_spacing_m',label:'中心行距 / cm',factor:100,step:1,min:5,max:500},{key:'front_passage_m',label:'前端通道宽 / m',factor:1,step:.05,min:0,max:20},{key:'rear_passage_m',label:'后端通道宽 / m',factor:1,step:.05,min:0,max:20},{key:'aisle_width_m',label:'带间通道宽 / m',factor:1,step:.05,min:.1,max:5},{key:'side_margin_m',label:'侧边预留 / m',factor:1,step:.05,min:0,max:5}] as const
function cropInput(key:Exclude<keyof DesignSpec['planting'],'cultivar'>,event:Event,factor:number){draft.planting[key]=Number((event.target as HTMLInputElement).value)/factor}
async function generate(){
 const mine=++generation,body=clone(draft);previewing.value=true;previewError.value=''
 try{const result=await designsApi.preview(body);if(alive&&mine===generation){preview.value=result;previewSpec.value=body}}
 catch(e){if(alive&&mine===generation)previewError.value=e instanceof Error?e.message:'布局暂时无法生成。'}
 finally{if(alive&&mine===generation)previewing.value=false}
}
watch(draft,()=>{generation++;clearTimeout(timer);previewing.value=true;timer=setTimeout(()=>void generate(),350);message.value=''},{deep:true,flush:'sync'})
async function load(){const mine=ownerGeneration;loading.value=true;error.value='';try{const result=await designsApi.list();if(alive&&mine===ownerGeneration)items.value=result.items}catch(e){if(alive&&mine===ownerGeneration)error.value=e instanceof Error?e.message:'方案列表读取失败。'}finally{if(alive&&mine===ownerGeneration)loading.value=false}}
function canDiscard(){return !dirty.value||window.confirm('当前方案有未保存修改，是否放弃这些修改？')}
function loadSpec(spec:DesignSpec){
 Object.assign(draft,clone(spec),{lighting:spec.lighting?clone(spec.lighting):newDesign().lighting})
 saved.value=JSON.stringify(draft)
}
function setDraft(plan:DesignRecord|null){
 record.value=plan;loadSpec(plan?.spec??newDesign());selected.value=-1
}
async function choose(id:string){if(!canDiscard())return;error.value='';if(!id){setDraft(null);return}const mine=ownerGeneration;loading.value=true;try{const result=await designsApi.get(id);if(alive&&mine===ownerGeneration)setDraft(result)}catch(e){if(alive&&mine===ownerGeneration)error.value=e instanceof Error?e.message:'方案读取失败。'}finally{if(alive&&mine===ownerGeneration)loading.value=false}}
async function save(apply=false){
 if(busy.value)return;saving.value=true;error.value='';message.value='';const mine=ownerGeneration,body=clone(draft)
 try{
  const result=record.value?await designsApi.update(record.value.id,record.value.revision,body):await designsApi.create(body)
  if(!alive||mine!==ownerGeneration)return
  record.value=result;loadSpec(result.spec);items.value=[result,...items.value.filter(v=>v.id!==result.id)];message.value='方案已保存。'
  if(apply){const selection=await designsApi.activate(result.id,result.revision);if(alive&&mine===ownerGeneration)await router.push({path:'/live',query:{applyDesign:selection.id,designRevision:selection.revision}})}
 }catch(e){if(alive&&mine===ownerGeneration)error.value=e instanceof Error?e.message:'保存失败，请重试。'}finally{if(alive&&mine===ownerGeneration)saving.value=false}
}
function askDelete(){
 if(busy.value||!record.value)return
 deleteError.value='';deleteTarget.value=record.value
}
async function confirmDelete(){
 const plan=deleteTarget.value,mine=ownerGeneration
 if(!plan||deleting.value)return
 deleting.value=true;deleteError.value=''
 try{
  await designsApi.remove(plan.id,plan.revision)
  if(!alive||mine!==ownerGeneration)return
  items.value=items.value.filter(item=>item.id!==plan.id)
  setDraft(null)
  deleteTarget.value=null;error.value='';message.value='方案已删除。'
 }catch(e){
  if(alive&&mine===ownerGeneration)deleteError.value=e instanceof Error?e.message:'删除失败，请重试。'
 }finally{
  if(alive&&mine===ownerGeneration)deleting.value=false
 }
}
function confirmLocation(value:MonitoringLocation){Object.assign(draft.location,value);locationOpen.value=false}
function manual(){if(!preview.value||!currentPreview.value)return;draft.irrigation.sprinklers=clone(preview.value.sprinklers);draft.irrigation.placement='manual';selected.value=draft.irrigation.sprinklers.length?0:-1}
function movePoint(point:{x:number;y:number}){if(draft.irrigation.placement!=='manual'||selected.value<0)return;const p=draft.irrigation.sprinklers[selected.value];if(p){p.x=point.x;p.y=point.y}}
const azimuth=computed(()=>Number(draft.location.opening_azimuth))
const manualPoint=computed(()=>draft.irrigation.sprinklers[selected.value])
watch(()=>session.user.value?.id,()=>{ownerGeneration++;generation++;setDraft(null);items.value=[];preview.value=null;previewSpec.value=null;error.value='';message.value='';saving.value=false;deleting.value=false;deleteTarget.value=null;deleteError.value='';void load();clearTimeout(timer);void generate()},{immediate:true})
onUnmounted(()=>{alive=false;generation++;ownerGeneration++;clearTimeout(timer)})
</script>
<template>
 <section class="greenhouse-design-page">
  <header class="design-heading"><div><h2>温室设计</h2><p>{{draft.name||'未命名温室'}} · {{record?`版本 ${record.revision}`:'方案草稿'}} <span v-if="dirty" class="design-tag">未保存修改</span></p></div><div class="design-actions"><button type="button" :disabled="busy" @click="save(false)"><Icon name="file"/>保存草稿</button><button type="button" class="design-primary" :disabled="busy||!modelSupported||!!preview?.notices.length" @click="save(true)">保存并用于监测</button></div></header>
  <div class="design-selector">
   <label class="scheme-name">方案名称<input v-model="draft.name" maxlength="120" :disabled="busy" required></label>
   <label>我的方案<select :value="record?.id??''" :disabled="busy" @change="choose(($event.target as HTMLSelectElement).value)"><option value="">新方案草稿</option><option v-for="item in items" :key="item.id" :value="item.id">{{item.spec.name}} · v{{item.revision}}</option></select></label>
   <button type="button" :disabled="busy" @click="choose('')">新建方案</button>
   <button type="button" class="design-delete" :disabled="busy||!record" @click="askDelete"><Icon name="trash"/>删除方案</button>
   <button v-if="record" type="button" :disabled="busy" @click="choose(record.id)">重新载入</button>
   <button type="button" :disabled="busy" @click="load">刷新列表</button>
   <span class="initial-values-note">初始参数为示例值，请按现场情况调整。</span>
  </div>
  <p v-if="error" role="alert" class="design-error">{{error}}</p><p v-if="message" role="status" class="design-message">{{message}}</p>
  <div class="design-columns">
   <fieldset class="design-inputs" :disabled="busy">
    <section class="design-panel location-panel">
     <h3><span><b>01</b>位置与朝向</span><button type="button" class="location-button" aria-label="选择监测地点" @click="locationOpen=true"><Icon name="location"/>{{location?regionText(location):'选择地点'}}</button></h3>
     <div class="design-fields">
      <label>经度 / °<input :value="draft.location.longitude" @input="draft.location.longitude=($event.target as HTMLInputElement).value===''?null:Number(($event.target as HTMLInputElement).value)" type="number" min="-180" max="180" step="any" placeholder="待选择"></label>
      <label>纬度 / °<input :value="draft.location.latitude" @input="draft.location.latitude=($event.target as HTMLInputElement).value===''?null:Number(($event.target as HTMLInputElement).value)" type="number" min="-90" max="90" step="any" placeholder="待选择"></label>
      <label>海拔 / m<input :value="draft.location.altitude_m" @input="draft.location.altitude_m=($event.target as HTMLInputElement).value===''?null:Number(($event.target as HTMLInputElement).value)" type="number" min="-500" max="9000" step="any" placeholder="待确认"></label>
      <label>前端开口方位<div class="bearing-input"><input v-model.number="draft.location.opening_azimuth" type="number" min="0" max="359.99" step="1" aria-label="前端开口方位 / °"><span>{{bearingName(azimuth)}} · °</span></div></label>
      <p class="full design-note">以真北为 0°，顺时针计角；坐标系 GCJ-02。</p>
     </div><div class="location-rear">后端开口：{{bearingName((azimuth+180)%360)}} · {{(azimuth+180)%360}}° <span>（自动）</span></div>
    </section>
    <section class="design-panel structure-panel"><h3><span><b>02</b>温室结构</span></h3>
     <div class="design-fields">
      <div class="full greenhouse-types"><span>温室类型</span><label><input v-model="draft.structure.type" type="radio" value="arch" name="design-greenhouse-type">小拱棚</label><label><input v-model="draft.structure.type" type="radio" value="multi_span" name="design-greenhouse-type">连栋温室</label></div>
      <div class="full structure-dimensions"><label>长度 / m<input v-model.number="draft.structure.length_m" type="number" min=".5" max="200" step=".1"></label><label>宽度 / m<input v-if="draft.structure.type==='arch'" v-model.number="draft.structure.width_m" type="number" min=".5" max="100" step=".1"><output v-else>{{width.toFixed(2)}}</output></label><label>{{draft.structure.type==='arch'?'拱高':'起拱高度'}} / m<input v-model.number="draft.structure.arch_height_m" type="number" min=".3" max="20" step=".1"></label></div>
      <template v-if="draft.structure.type==='multi_span'"><label>单跨跨度 / m<input v-model.number="draft.structure.span_width_m" type="number" min=".5" max="20" step=".1"></label><label>连栋数量<input v-model.number="draft.structure.span_count" type="number" min="1" max="10" step="1"></label><label>檐高 / m<input v-model.number="draft.structure.eave_height_m" type="number" min=".1" max="15" step=".1"></label></template>
      <label class="full covering-field">覆盖材料<select v-model="draft.structure.covering"><option value="film_shade">薄膜 + 遮阳网</option><option value="film">薄膜</option><option value="shade_net">遮阳网</option><option value="polycarbonate">聚碳酸酯板</option><option value="glass">玻璃</option></select></label>
      <p class="full design-note">{{draft.structure.type==='multi_span'?'总宽 = 跨度 × 栋数；总高 = 檐高 + 起拱高度。':'连栋类型可配置跨度、栋数与檐高。'}}</p>
     </div>
    </section>
    <section class="design-panel"><h3><span><b>03</b>作物与种植布局</span></h3><div class="design-fields"><label class="full">人参品种<input v-model="draft.planting.cultivar" maxlength="120" placeholder="选择或输入品种名称"></label><label v-for="field in cropFields.slice(0,5)" :key="field.key">{{field.label}}<input type="number" :value="Number((draft.planting[field.key]*field.factor).toFixed(4))" :min="field.min" :max="field.max" :step="field.step" @input="cropInput(field.key,$event,field.factor)"></label><details class="full design-advanced"><summary>带间通道与侧边预留</summary><div class="design-fields"><label v-for="field in cropFields.slice(5)" :key="field.key">{{field.label}}<input type="number" :value="draft.planting[field.key]" :min="field.min" :max="field.max" :step="field.step" @input="cropInput(field.key,$event,field.factor)"></label></div></details></div></section>
    <section class="design-panel">
     <h3><span><b>04</b>设备布局</span></h3>
     <div class="design-fields">
      <label class="design-checkbox"><input v-model="draft.irrigation.drip_enabled" type="checkbox">滴灌</label>
      <label class="design-checkbox"><input v-model="draft.irrigation.sprinkler_enabled" type="checkbox">喷灌</label>
      <label>滴头间距 / cm<input :value="draft.irrigation.emitter_spacing_m*100" type="number" min="5" max="200" step="1" @input="draft.irrigation.emitter_spacing_m=Number(($event.target as HTMLInputElement).value)/100"></label>
      <label>喷头间距 / m<input v-model.number="draft.irrigation.sprinkler_spacing_m" type="number" min=".5" max="20" step=".1"></label>
      <label>喷头安装高度 / m<input v-model.number="draft.irrigation.installation_height_m" type="number" min=".05" max="15" step=".1"></label>
      <details class="full design-advanced"><summary>喷灌覆盖设置</summary><label>标称覆盖半径 / m<input v-model.number="draft.irrigation.coverage_radius_m" type="number" min=".1" max="20" step=".1"></label></details>
      <p class="full design-note">滴灌管线沿种植行布置，滴头间距与株距分别保存。</p>
      <button type="button" :aria-pressed="draft.irrigation.placement==='auto'" @click="draft.irrigation.placement='auto';selected=-1">自动布置</button>
      <button type="button" :disabled="!currentPreview||!draft.irrigation.sprinkler_enabled" :aria-pressed="draft.irrigation.placement==='manual'" @click="manual">手动调整</button>
      <template v-if="draft.irrigation.placement==='manual'">
       <label class="full">选择喷头<select v-model.number="selected"><option v-for="(_,n) in draft.irrigation.sprinklers" :key="n" :value="n">喷头 {{n+1}}</option></select></label>
       <label v-if="manualPoint">横向 x / m<input v-model.number="manualPoint.x" type="number" min="0" :max="width" step=".1"></label>
       <label v-if="manualPoint">纵向 y / m<input v-model.number="manualPoint.y" type="number" min="0" :max="draft.structure.length_m" step=".1"></label>
       <p class="full design-note">也可在二维图中选中喷头后，点击新位置调整。</p>
      </template>
      <div class="full lighting-heading">
       <label class="design-checkbox"><input v-model="draft.lighting.enabled" type="checkbox"><Icon name="sunlight"/>补光灯</label>
       <span v-if="draft.lighting.enabled&&currentPreview">{{preview?.lights?.length??0}} 盏</span>
      </div>
      <template v-if="draft.lighting.enabled">
       <label>补光灯纵向间距 / m<input v-model.number="draft.lighting.spacing_m" type="number" min=".5" max="20" step=".1"></label>
       <label>补光灯安装高度 / m<input v-model.number="draft.lighting.mounting_height_m" type="number" min=".15" max="35" step=".05"></label>
       <p class="full design-note">灯具沿种植带中心自动布置，安装高度从地面量起。</p>
      </template>
     </div>
    </section>
   </fieldset>
   <div class="design-previews"><section class="design-panel scene-panel"><div class="design-panel-heading"><h3><Icon name="cube"/>三维棚体预览</h3><div><button type="button" :aria-pressed="!topView" @click="topView=false">三维</button><button type="button" :aria-pressed="topView" @click="topView=true">俯视</button></div></div><GreenhouseDesignScene v-if="preview&&previewSpec" :spec="previewSpec" :layout="preview" :top-view="topView"/><p v-else class="preview-empty">正在生成棚体几何预览…</p><p class="design-note preview-caption"><Icon name="rotate"/>拖动旋转 · 滚轮缩放<span>几何预览</span></p></section>
    <section class="design-panel planting-panel"><div class="design-panel-heading"><h3>种植与设备布局</h3><span v-if="previewing" role="status">更新布局中…</span></div><p v-if="previewError" role="alert" class="design-error">{{previewError}} 当前图形保留上一有效配置。</p><template v-if="preview&&previewSpec"><GreenhousePlantingPlan :spec="previewSpec" :layout="preview" :selected="selected" :manual="draft.irrigation.placement==='manual'" @select="selected=$event" @move="movePoint"/><p v-for="notice in preview.notices" :key="notice" class="design-error">{{notice}}</p></template></section>

   </div>
   <aside class="design-results"><DesignInspectionPanel :design-id="record?.id??null" :revision="record?.revision??null" :dirty="dirty"/>
    <section class="design-panel scheme-info-panel"><h3><Icon name="file"/>方案信息</h3><dl><div><dt>棚型</dt><dd>{{draft.structure.type==='arch'?'小拱棚':'连栋温室'}}</dd></div><div><dt>种植带</dt><dd>{{currentPreview?preview?.beds.length:'待更新'}} 条</dd></div><div><dt>占地</dt><dd>{{currentPreview?preview?.area_m2.toFixed(2):'待更新'}} m²</dd></div><div><dt>预计株数</dt><dd>{{currentPreview?preview?.plant_count.toLocaleString():'待更新'}}</dd></div><div><dt>版本</dt><dd>{{record?`v${record.revision}`:'草稿'}}</dd></div></dl><p class="design-note">种植数量为几何排布结果，未计入出苗率等生产因素。</p></section>
   </aside>
  </div>
  <p class="design-footer">方案参数调整后，请保存新版本并重新检验。AI 结果始终对应发起时的保存版本。</p>
  <details class="design-model-note"><summary>模型适用说明</summary><p>{{preview?.model.detail}}当前监测仅读取地点与尺寸，其余设计参数暂不参与温度预测。</p></details>
  <MonitoringLocationDialog :open="locationOpen" :model-value="location" @close="locationOpen=false" @confirm="confirmLocation"/>
  <ModalDialog v-if="deleteTarget" label="删除温室方案" :busy="deleting" @close="deleteTarget=null">
   <div class="design-delete-dialog">
    <h3>删除温室方案</h3>
    <p>确定删除「{{deleteTarget.spec.name}}」吗？</p>
    <p class="design-note">删除后，该方案会从温室设计和温室控制的列表移除。若已应用于监测，保存的方案关联也会解除。</p>
    <p v-if="dirty" class="design-note">当前未保存的修改也会被丢弃。</p>
    <p v-if="deleteError" role="alert" class="design-error">{{deleteError}}</p>
    <footer>
     <button type="button" autofocus :disabled="deleting" @click="deleteTarget=null">取消</button>
     <button type="button" class="design-delete-confirm" :disabled="deleting" @click="confirmDelete">{{deleting?'删除中…':'确认删除'}}</button>
    </footer>
   </div>
  </ModalDialog>
 </section>
</template>
<style scoped>
.lighting-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; padding-top:10px; border-top:var(--rule); }
.lighting-heading .icon { color:var(--control-amber); --icon-size:16px; }
.lighting-heading > span { color:var(--control-amber); font-size:12px; }
.greenhouse-design-page{color:var(--ink);padding:0 0 24px;min-width:0;--design-gap:14px}
.greenhouse-design-page .design-delete:not(:disabled){color:var(--management-danger);border-color:color-mix(in srgb,var(--management-danger) 60%,var(--steel))}
.design-delete-dialog h3{margin:0 0 16px;font-size:18px}
.design-delete-dialog p{overflow-wrap:anywhere}
.design-delete-dialog footer{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}
.design-delete-dialog button{min-height:36px;padding:6px 12px;border:1px solid var(--steel);border-radius:var(--radius);background:var(--card-2);color:var(--ink);font:inherit;cursor:pointer}
.design-delete-dialog .design-delete-confirm{background:var(--management-danger);border-color:var(--management-danger);color:#fff}
.design-delete-dialog button:disabled{opacity:.5;cursor:default}
.design-heading{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:0 0 16px;flex-wrap:wrap}.design-heading h2{font-size:28px;margin:0;font-weight:var(--w-title)}.design-heading p{margin:4px 0 0;color:var(--ink-muted);font-size:14px}.design-actions{display:flex;gap:10px;flex-wrap:wrap}
.greenhouse-design-page button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:6px 12px;font:inherit;font-size:13px;border:1px solid var(--steel);border-radius:var(--radius);background:var(--card-2);color:var(--ink);cursor:pointer}.greenhouse-design-page button:not(:disabled):hover{border-color:var(--edge)}.greenhouse-design-page button.design-primary,.greenhouse-design-page button[aria-pressed=true]{background:var(--interact);border-color:var(--interact);color:var(--on-face)}.greenhouse-design-page button:disabled{opacity:.5;cursor:default}.design-actions button{min-height:40px;padding:8px 16px;font-size:14px}.design-tag{border:1px solid var(--steel);border-radius:4px;padding:1px 5px;font-size:12px}
.design-selector{display:flex;align-items:end;gap:8px;flex-wrap:wrap;margin-bottom:16px;padding-bottom:14px;border-bottom:var(--rule)}.design-selector label{display:grid;gap:4px;font-size:12px;color:var(--ink-muted)}.design-selector label.scheme-name{width:190px}.design-selector select{width:190px}.initial-values-note{font-size:12px;color:var(--ink-muted);margin-bottom:9px}
.greenhouse-design-page input,.greenhouse-design-page select{background:var(--card-2);color:var(--ink);border:1px solid color-mix(in srgb,var(--ink-muted) 65%,var(--card));border-radius:4px;padding:7px 9px;min-height:36px;min-width:0;width:100%;font:inherit;font-size:14px;font-variant-numeric:tabular-nums}.greenhouse-design-page input::placeholder{color:var(--ink-muted);opacity:.75}
.design-columns{display:grid;grid-template-columns:minmax(290px,29fr) minmax(340px,54fr) minmax(230px,23fr);gap:var(--design-gap);align-items:stretch;grid-auto-rows:auto}.design-inputs,.design-previews,.design-results{display:contents}.design-inputs{border:0;padding:0;margin:0;min-width:0}.design-inputs>.design-panel:nth-child(1){grid-area:1/1/2/2}.design-inputs>.design-panel:nth-child(2){grid-area:2/1/3/2}.design-inputs>.design-panel:nth-child(3){grid-area:3/1/4/2}.design-inputs>.design-panel:nth-child(4){grid-area:4/1/5/2}.scene-panel{grid-area:1/2/3/3}.planting-panel{grid-area:3/2/5/3}.ai-design-panel{grid-area:1/3/3/4}.scheme-info-panel{grid-area:3/3/5/4}
.design-panel{background:var(--card);border:1px solid color-mix(in srgb,var(--edge) 45%,var(--steel));border-radius:var(--radius);min-width:0;padding:0 13px 13px;overflow:hidden}.design-panel h3{font-size:17px;font-weight:var(--w-strong);margin:0 -13px 13px;padding:11px 13px;min-height:49px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--steel);background:color-mix(in srgb,var(--card-2) 60%,var(--card))}.design-panel h3>span:first-child{display:flex;align-items:center;gap:9px}.design-panel h3 b{color:var(--edge);font-size:18px;font-weight:var(--w-strong)}.design-panel h3:has(>.icon):before,.ai-design-panel h3:before,.planting-panel h3:before{content:'';width:3px;height:17px;flex:none;background:var(--edge)}
.design-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px 12px}.design-fields label{display:grid;align-content:start;gap:5px;font-size:13px;color:var(--ink)}.design-fields output{padding:7px 9px;min-height:36px;display:block;border:1px solid var(--steel);border-radius:4px;color:var(--ink)}.full{grid-column:1/-1}.design-fields .design-checkbox{display:flex;align-items:center;gap:7px;color:var(--ink)}.design-checkbox input,.greenhouse-types input{width:16px;height:16px;min-height:0;padding:0;margin:0;accent-color:var(--interact)}.design-note{font-size:12px;color:var(--ink-muted);line-height:1.65;margin:2px 0}
.location-panel h3{justify-content:space-between}.greenhouse-design-page .location-button{background:transparent;border:0;min-height:24px;padding:0;max-width:54%;font-size:12px;color:var(--ink-muted);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.location-button :deep(.icon){flex:none}.location-rear{border-top:var(--rule);margin-top:12px;padding-top:9px;font-size:13px}.location-rear span{color:var(--ink-muted);font-size:12px}.bearing-input{position:relative}.bearing-input input{padding-right:58px}.bearing-input>span{position:absolute;right:9px;top:8px;font-size:13px;color:var(--ink-muted);pointer-events:none}.greenhouse-types{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:13px}.greenhouse-types>span{color:var(--ink-muted)}.greenhouse-types label{display:flex;align-items:center;gap:5px;white-space:nowrap}.structure-dimensions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.design-fields .covering-field{display:grid;grid-template-columns:70px minmax(0,1fr);align-items:center;gap:8px}.design-advanced{border-top:var(--rule);padding-top:9px;font-size:12px;color:var(--ink-muted)}.design-advanced summary{cursor:pointer;min-height:22px}.design-advanced>label,.design-advanced>.design-fields{margin-top:9px}
.scene-panel,.planting-panel{display:flex;flex-direction:column}.design-panel-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 -13px 6px;padding:0 13px;border-bottom:var(--rule);min-height:49px;background:color-mix(in srgb,var(--card-2) 60%,var(--card))}.design-panel-heading h3{margin:0;padding:10px 0;border:0;background:transparent;min-height:48px}.design-panel-heading>div{display:flex;gap:6px}.design-panel-heading button{font-size:12px;padding:3px 12px;min-height:28px}.design-panel-heading>span{font-size:12px;color:var(--ink-muted)}.scene-panel :deep(.design-scene){flex:1;min-height:360px;height:auto}.preview-empty{display:grid;place-content:center;min-height:360px;flex:1;color:var(--ink-muted)}.preview-caption{display:flex;align-items:center;justify-content:center;gap:6px;padding-top:8px}.preview-caption>span{margin-left:auto;font-size:11px}.preview-caption :deep(.icon){--icon-size:14px}.planting-panel :deep(.planting-plan){display:flex;flex-direction:column;justify-content:flex-start}
.ai-design-panel{display:flex;flex-direction:column}.ai-design-panel h3{flex-wrap:nowrap}.ai-design-panel h3 small{margin-left:auto;font-size:13px;font-weight:var(--w-body);color:var(--ink-muted)}.ai-planned{display:flex;align-items:center;gap:9px;padding:11px 12px;background:var(--card-2);border-radius:4px;font-size:15px;font-weight:var(--w-strong);margin:0}.ai-design-panel ol{padding:0;list-style:none;margin:0 0 16px;flex:1;display:flex;flex-direction:column}.ai-design-panel li{display:flex;align-items:flex-start;gap:9px;padding:17px 0;flex:1;border-bottom:var(--rule);font-size:15px}.ai-design-panel li>b{display:inline-grid;place-content:center;width:23px;height:23px;flex:none;border-radius:50%;background:var(--card-2);font-size:12px}.ai-design-panel small{display:block;color:var(--ink-muted);font-size:12px;margin-top:4px}.inspection-pending{width:12px;height:12px;flex:none;border:1px solid var(--ink-muted);border-radius:50%;margin:5px 0 0 auto}.ai-design-panel>button{width:100%;margin-bottom:12px;min-height:40px;font-size:15px;background:var(--card-2)}
.scheme-info-panel{display:flex;flex-direction:column;align-self:start}.scheme-info-panel dl{margin:0;display:flex;flex-direction:column}.scheme-info-panel dl>div{display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:var(--rule);font-size:14px}.scheme-info-panel dt{color:var(--ink-muted);min-width:64px}.scheme-info-panel dd{margin:0;font-variant-numeric:tabular-nums}.scheme-info-panel>.design-note{margin-top:12px}.design-footer{font-size:12px;color:var(--ink-muted);margin:14px 0 0;padding:8px 12px;background:var(--card);border-radius:4px}.design-model-note{color:var(--ink-muted);font-size:12px;margin-top:10px}.design-model-note summary{cursor:pointer}.design-model-note p{margin-top:8px}.design-error{color:var(--training-warning);background:var(--training-warning-soft);padding:9px 12px;border-radius:var(--radius);font-size:13px}.design-message{font-size:13px;color:var(--leaf)}.greenhouse-design-page :deep(.icon){--icon-size:18px}.greenhouse-design-page button:focus-visible,.greenhouse-design-page input:focus-visible,.greenhouse-design-page select:focus-visible{outline:2px solid var(--edge);outline-offset:2px}
@media(max-width:1190px){.design-columns{grid-template-columns:290px minmax(0,1fr)}.ai-design-panel{grid-area:5/1/6/2}.scheme-info-panel{grid-area:5/2/6/3}.scene-panel :deep(.design-scene){min-height:330px}.initial-values-note{width:100%;margin:0}}
@media(max-width:850px){.design-columns{display:flex;flex-direction:column}.design-inputs,.design-previews,.design-results{display:grid;gap:var(--design-gap)}.design-actions{width:100%}.design-actions button{flex:1}.design-heading h2{font-size:24px}.design-selector label.scheme-name,.design-selector label:not(.scheme-name){width:calc(50% - 5px)}.design-selector select{width:100%}.design-panel h3{font-size:16px}.scene-panel :deep(.design-scene){height:360px;flex:none}.design-fields{gap:12px}.scheme-info-panel dl>div{padding:12px 0}}
@media(pointer:coarse){.greenhouse-design-page input:not([type=radio]):not([type=checkbox]),.greenhouse-design-page select{min-height:42px;font-size:16px}.greenhouse-design-page button{min-height:42px}.greenhouse-types label,.design-fields .design-checkbox{min-height:36px}.bearing-input>span{top:10px}}
</style>
