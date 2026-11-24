import { onUnmounted, ref, watch, type Ref } from 'vue'
import { weatherApi, type WeatherQueryResult } from '../api/weather'
import type { MonitoringLocation } from '../live/monitoringLocation'

/** One explicit selection/rebuild → one weather query. No expiry/visibility polling. */
export function useSingleWeatherQuery(location:Ref<MonitoringLocation|null>,enabled:Ref<boolean>){
  const data=ref<WeatherQueryResult|null>(null),loading=ref(false),error=ref('')
  let alive=true,generation=0
  watch(location,()=>{generation++;data.value=null;loading.value=false;error.value=''}, {flush:'sync'})
  async function refresh(){
    if(!alive||!enabled.value||!location.value)return
    const point={...location.value},mine=++generation
    loading.value=true;error.value=''
    try{const result=await weatherApi.query(point);if(alive&&mine===generation)data.value=result}
    catch(e){if(alive&&mine===generation)error.value=e instanceof Error?e.message:'气象查询失败，请重新构场。'}
    finally{if(alive&&mine===generation)loading.value=false}
  }
  onUnmounted(()=>{alive=false;generation++})
  return {data,loading,error,refresh}
}
