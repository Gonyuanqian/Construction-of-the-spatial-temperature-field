import { onUnmounted, ref, watch, type Ref } from 'vue'
import { weatherApi, type WeatherQueryResult } from '../api/weather'
import type { MonitoringLocation } from '../live/monitoringLocation'

/** Paid upstream data is refreshed on confirmation/expiry, only while this view is visible. */
export function useWeatherQuery(location: Ref<MonitoringLocation|null>, enabled: Ref<boolean>) {
  const data=ref<WeatherQueryResult|null>(null),loading=ref(false),error=ref('')
  let alive=true,generation=0,timer:ReturnType<typeof setTimeout>|undefined
  function cancelTimer(){if(timer)clearTimeout(timer);timer=undefined}
  function visible(){return enabled.value && document.visibilityState!=='hidden'}
  function schedule(){
    cancelTimer()
    if(!visible()||!data.value)return
    const expires=Date.parse(data.value.expires_at)
    if(Number.isFinite(expires))timer=setTimeout(()=>void refresh(),Math.max(1_000,expires-Date.now()))
  }
  async function refresh(){
    if(!alive||!visible()||!location.value)return
    const point={...location.value},mine=++generation
    loading.value=true;error.value='';cancelTimer()
    try {
      const result=await weatherApi.query(point)
      if(!alive||mine!==generation||!enabled.value)return
      data.value=result;schedule()
    }catch(e){if(alive&&mine===generation)error.value=e instanceof Error?e.message:'气象查询失败，请点击刷新重试。'}
    finally{if(alive&&mine===generation)loading.value=false}
  }
  watch(location,()=>{
    generation++;data.value=null;error.value='';loading.value=false;cancelTimer()
    if(location.value&&visible())void refresh()
  },{immediate:true})
  function resume(){
    if(!visible()){generation++;loading.value=false;cancelTimer();return}
    // Obtain a fresh, short-lived construction ticket on return; server cache avoids a paid refetch.
    if(location.value)void refresh()
    else schedule()
  }
  watch(enabled,resume)
  document.addEventListener('visibilitychange',resume)
  onUnmounted(()=>{alive=false;generation++;cancelTimer();document.removeEventListener('visibilitychange',resume)})
  return {data,loading,error,refresh}
}
