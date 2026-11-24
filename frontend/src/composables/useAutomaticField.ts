import { nextTick, onUnmounted, ref, watch, type Ref } from 'vue'
import { weatherApi, type AutomaticFieldResult, type WeatherQueryResult } from '../api/weather'
import {sameDimensions,type HouseDimensions} from '../live/houseDimensions'

/** Server-held query → published G/F → immutable saved field; discard old-location replies. */
export function useAutomaticField(query: Ref<WeatherQueryResult|null>, enabled: Ref<boolean>,dimensions?:Ref<HouseDimensions>) {
  const data=ref<AutomaticFieldResult|null>(null),loading=ref(false),error=ref(''),blocked=ref('')
  let alive=true,generation=0
  let pending:Promise<void>=Promise.resolve()
  async function run(snapshot:WeatherQueryResult|null){
    const mine=++generation
    error.value='';blocked.value='';loading.value=false
    if(!snapshot){data.value=null;return}
    if(!enabled.value)return
    if(snapshot.data_kind!=='current' || !snapshot.construction_ready){
      data.value=null;blocked.value=snapshot.detail??'等待实况温湿度与本周期光照近似值，暂不构场。';return
    }
    if(data.value?.live.weather_source?.source_fingerprint!==snapshot.source_fingerprint)data.value=null
    loading.value=true
    try{
      const selected=dimensions?{...dimensions.value}:undefined
      const result=await (selected?weatherApi.construct(snapshot.query_id,selected):weatherApi.construct(snapshot.query_id))
      if(selected && (!result.live.prototype || !sameDimensions(result.live.dimensions,selected)))throw new Error('构场结果与所选棚体尺寸不一致。')
      if(alive&&mine===generation&&enabled.value)data.value=result
    }catch(e){if(alive&&mine===generation)error.value=e instanceof Error?e.message:'自动构场失败，请刷新重试。'}
    finally{if(alive&&mine===generation)loading.value=false}
  }
  watch(query,snapshot=>{pending=run(snapshot)},{immediate:true})
  async function settled(){await nextTick();await pending;await nextTick()}
  watch(enabled,value=>{if(!value){generation++;loading.value=false}})
  if(dimensions)watch(dimensions,()=>{generation++;data.value=null;loading.value=false;error.value='';blocked.value=''},{flush:'sync'})
  onUnmounted(()=>{alive=false;generation++})
  return {data,loading,error,blocked,settled}
}
