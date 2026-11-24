<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { regionApi, regionText, type RegionCatalog, type RegionInfo } from '../api/regions'
import { locationAt, selectedPoint, searchLocations, type Coordinate, type LocationMapData, type MonitoringLocation } from '../live/monitoringLocation'
import ModalDialog from './ModalDialog.vue'
import Icon from './Icon.vue'
import MonitoringLocationMap from './MonitoringLocationMap.vue'

const props=defineProps<{open: boolean; modelValue?: MonitoringLocation | RegionInfo | null}>()
const emit=defineEmits<{close: []; confirm: [location: MonitoringLocation]}>()
const catalog=ref<RegionCatalog|null>(null),map=ref<LocationMapData|null>(null)
const draft=ref<MonitoringLocation|null>(null),cityCode=ref(''),districtCode=ref(''),focusCode=ref('')
const query=ref(''),searchOpen=ref(false),searched=ref(false),loading=ref(false),error=ref(''),mapHint=ref('')
const districts=computed(()=>catalog.value?.cities.find(c=>c.code===cityCode.value)?.districts??[])
const results=computed(()=>catalog.value?searchLocations(catalog.value,query.value):[])
let generation=0,alive=true
function choose(region: RegionInfo) {
  if (!catalog.value || !map.value) return
  const point=selectedPoint(catalog.value,map.value,region)
  if (!point) {mapHint.value='该地区暂时没有地图位置，请在地图上选点。';return}
  draft.value=point;cityCode.value=region.city_code;districtCode.value=region.district_code??''
  focusCode.value=region.district_code??region.city_code;mapHint.value='';searchOpen.value=false;searched.value=false
}
async function load() {
  const mine=++generation;loading.value=true;error.value='';mapHint.value='';query.value='';searchOpen.value=false;searched.value=false
  draft.value=null;cityCode.value='';districtCode.value='';focusCode.value=''
  try {
    const [regions,geography]=await Promise.all([regionApi.list(),map.value?Promise.resolve(map.value):fetch('/maps/jilin-districts.json').then(async response=>{
      if (!response.ok) throw new Error('地图暂时无法读取，请重试。')
      const value=await response.json() as LocationMapData
      if(value.type!=='FeatureCollection'||value.coordinate_system!=='GCJ-02'||!Array.isArray(value.features)||!value.features.length)throw new Error('地图数据格式无效，请重试。')
      return value
    })])
    if (!alive || mine!==generation || !props.open) return
    catalog.value=regions;map.value=geography
    if (props.modelValue) {
      const city=regions.cities.find(c=>c.code===props.modelValue?.city_code)
      const district=city?.districts.find(d=>d.code===props.modelValue?.district_code)
      if (city) {
        choose({province_code:regions.province.code,province_name:regions.province.name,city_code:city.code,city_name:city.name,...(district?{district_code:district.code,district_name:district.name}:{})})
        if ('longitude' in props.modelValue) {
          const point=props.modelValue as MonitoringLocation
          const checked=point.coordinate_system==='GCJ-02'?locationAt(regions,geography,[point.longitude,point.latitude]):null
          if (checked && checked.city_code===city.code && (!district || checked.district_code===district.code)) draft.value={...draft.value!,longitude:checked.longitude,latitude:checked.latitude}
        }
      }
    }
  } catch(e) {if(alive&&mine===generation)error.value=e instanceof Error?e.message:'地点列表暂时无法读取，请重试。'}
  finally {if(alive&&mine===generation)loading.value=false}
}
function changeRegion(city: string,district='') {
  const selected=catalog.value?.cities.find(c=>c.code===city)
  if (!selected || !catalog.value) {draft.value=null;cityCode.value='';districtCode.value='';focusCode.value='';return}
  const child=selected.districts.find(d=>d.code===district)
  choose({province_code:catalog.value.province.code,province_name:catalog.value.province.name,city_code:selected.code,city_name:selected.name,...(child?{district_code:child.code,district_name:child.name}:{})})
}
function pick(point: Coordinate) {
  if (!catalog.value || !map.value) return
  const selection=locationAt(catalog.value,map.value,point)
  if (!selection) {mapHint.value='请在吉林省行政区范围内选择位置。';return}
  draft.value=selection;cityCode.value=selection.city_code;districtCode.value=selection.district_code??'';mapHint.value=''
}
function search() {
  searched.value=true;searchOpen.value=true
  if(results.value.length===1)choose(results.value[0]!)
}
function confirm() {if(draft.value&&!loading.value&&!error.value)emit('confirm',{...draft.value})}
watch(()=>props.open,open=>{if(open)void load();else{generation++;loading.value=false;searchOpen.value=false}},{immediate:true})
onUnmounted(()=>{alive=false;generation++})
</script>
<template>
  <ModalDialog v-if="open" label="选择监测地点" location @close="emit('close')">
    <section class="location-picker">
      <header class="picker-heading"><Icon name="location"/><div><h2>选择监测地点</h2><p>搜索地点，或选择省市区后在地图上确认。</p></div><button type="button" class="picker-close" aria-label="关闭地点选择" @click="emit('close')">×</button></header>
      <p v-if="error" class="picker-error" role="alert">{{error}} <button type="button" @click="load">重试</button></p>
      <form class="place-search" role="search" @submit.prevent="search">
        <div class="search-field"><Icon name="search"/><input v-model="query" aria-label="搜索监测地点" placeholder="搜索城市、区县" :disabled="loading || !!error" autocomplete="off" @input="searchOpen=true;searched=false" @focus="searchOpen=!!query.trim()" @keydown.esc.stop="searchOpen=false" /></div>
        <button type="submit" class="primary" :disabled="loading || !!error || !query.trim()">搜索</button>
        <div v-if="searchOpen && query.trim()" class="search-results"><template v-if="results.length"><button v-for="result in results" :key="result.district_code??result.city_code" type="button" @click="choose(result);query='' "><Icon name="location"/><span>{{regionText(result)}}</span><Icon name="arrowRight"/></button></template><p v-else role="status">{{searched?'未找到匹配地点，请选择市、区县或在地图上选点。':'当前支持吉林省城市、区县名称搜索。'}}</p></div>
      </form>
      <div class="region-fields"><label>省份<select aria-label="省份" :disabled="loading || !!error"><option value="220000">吉林省</option></select></label><label>城市<select aria-label="城市" :value="cityCode" :disabled="loading || !!error" @change="changeRegion(($event.target as HTMLSelectElement).value)"><option value="">请选择城市</option><option v-for="city in catalog?.cities" :key="city.code" :value="city.code">{{city.name}}</option></select></label><label>区县<select aria-label="区县" :value="districtCode" :disabled="loading || !!error || !cityCode" @change="changeRegion(cityCode,($event.target as HTMLSelectElement).value)"><option value="">全市范围</option><option v-for="district in districts" :key="district.code" :value="district.code">{{district.name}}</option></select></label></div>
      <div v-if="loading" class="map-loading" role="status">正在加载地点与地图…</div>
      <MonitoringLocationMap v-else-if="map && !error" :data="map" :selection="draft" :focus-code="focusCode" @pick="pick"/>
      <div v-else class="map-loading">地图暂不可用</div>
      <div class="selected-place" aria-live="polite"><Icon name="location"/><span>{{draft?`已选地点：${regionText(draft)}`:'请选择监测地点'}}</span></div>
      <p class="picker-hint" :class="{invalid:mapHint}" :role="mapHint?'status':undefined">{{mapHint || '点击地图或拖动标记调整位置；可使用方向键微调标记。'}}</p>
      <footer><button type="button" @click="emit('close')">取消</button><button type="button" class="primary confirm-location" :disabled="!draft || loading || !!error" @click="confirm"><Icon name="check"/>确认地点</button></footer>
    </section>
  </ModalDialog>
</template>
<style scoped>
.location-picker{height:min(780px,calc(100dvh - 36px));min-height:560px;display:flex;flex-direction:column;gap:16px;padding:24px 28px;background:linear-gradient(135deg,var(--card),var(--paper));box-sizing:border-box;}.picker-heading{display:flex;align-items:flex-start;gap:14px;padding-bottom:16px;border-bottom:1px solid var(--edge);flex-shrink:0;}.picker-heading>.icon{--icon-size:34px;color:var(--edge);margin-top:3px;}.picker-heading h2{margin:0;font-size:25px;line-height:1.3;}.picker-heading p{margin:7px 0 0;color:var(--ink-muted);font-size:13px;}.picker-close{margin-left:auto;flex-shrink:0;font-size:27px;line-height:1;width:32px;height:32px;min-height:0;padding:0;border:0;background:transparent;color:var(--ink);}.place-search{display:flex;gap:12px;position:relative;flex-shrink:0;}.search-field{display:flex;align-items:center;gap:12px;flex:1;min-width:0;padding:0 14px;border:1px solid var(--interact);border-radius:6px;background:var(--card);}.search-field .icon{--icon-size:20px;color:var(--ink-muted);}.search-field input{width:100%;min-width:0;height:43px;padding:0;border:0;background:transparent;color:var(--ink);font:inherit;}.search-field input::placeholder{color:var(--ink-muted);}.place-search>button{width:90px;border-radius:6px;}.primary{background:var(--interact);border:1px solid var(--edge);color:var(--on-face);}.region-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;flex-shrink:0;}.region-fields label{display:grid;gap:7px;font-size:14px;min-width:0;}.region-fields select{width:100%;height:43px;min-width:0;padding:0 12px;border:var(--rule);border-color:var(--interact);border-radius:6px;color:var(--ink);background:var(--card);font:inherit;}.location-picker>.location-map,.map-loading{flex:1;min-height:180px;}.map-loading{display:grid;place-items:center;border:var(--rule);border-radius:8px;color:var(--ink-muted);}.selected-place{display:flex;gap:10px;align-items:center;min-height:40px;padding:7px 14px;border:1px solid var(--interact);border-radius:6px;font-size:14px;flex-shrink:0;}.selected-place .icon{--icon-size:21px;color:var(--edge);flex-shrink:0;}.picker-hint{margin:-7px 0 0;color:var(--ink-muted);font-size:12px;flex-shrink:0;}.picker-hint.invalid,.picker-error{color:var(--bar);}.picker-error{font-size:13px;margin:0;}.picker-error button{padding:2px 8px;}.location-picker footer{display:flex;justify-content:flex-end;gap:14px;padding-top:18px;border-top:1px solid var(--edge);flex-shrink:0;}.location-picker footer button{display:inline-flex;justify-content:center;align-items:center;gap:10px;min-width:120px;height:44px;border-radius:6px;}.location-picker .confirm-location{min-width:160px;}.search-results{position:absolute;top:calc(100% + 6px);left:0;right:102px;z-index:3;max-height:240px;overflow:auto;background:var(--card);border:1px solid var(--interact);border-radius:6px;box-shadow:var(--shadow);}.search-results button{width:100%;display:flex;gap:10px;align-items:center;border:0;border-radius:0;background:transparent;text-align:left;padding:12px;font-size:13px;}.search-results button:hover{background:var(--leaf-soft);}.search-results .icon{--icon-size:17px;color:var(--edge);flex-shrink:0;}.search-results .icon:last-child{margin-left:auto;}.search-results p{padding:14px;margin:0;color:var(--ink-muted);font-size:13px;}button:disabled{opacity:.5;}
@media(max-height:740px){.location-picker{height:calc(100dvh - 36px);gap:11px;padding:18px 24px;}.picker-heading{padding-bottom:10px;}.picker-heading h2{font-size:22px;}.location-picker footer{padding-top:12px;}.location-picker :deep(.location-map>svg){min-height:180px;}}
@media(max-width:600px){.location-picker{padding:18px 16px;gap:12px;}.picker-heading{gap:9px;}.picker-heading h2{font-size:22px;}.picker-heading p{font-size:11px;}.region-fields{gap:8px;}.region-fields select{padding-inline:5px;font-size:13px;}.selected-place{padding-inline:8px;font-size:12px;}.place-search>button{width:65px;}.search-results{right:0;}.location-picker footer button{min-width:90px;}.location-picker .confirm-location{min-width:130px;}}
</style>
