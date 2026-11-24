import type { WeatherQueryResult } from '../api/weather'
import type { MonitoringLocation } from '../live/monitoringLocation'
export const testMonitoringLocation: MonitoringLocation={province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市',longitude:127,latitude:42,coordinate_system:'GCJ-02'}
export function makePeriodWeatherQuery(point=testMonitoringLocation): WeatherQueryResult {
  const now=Date.now(),start=Math.floor(now/900_000)*900_000,end=start+900_000
  return {query_id:'11111111-1111-4111-8111-111111111111',source_fingerprint:`${point.longitude},${point.latitude}`,provider:'qweather',data_kind:'current',construction_ready:true,location:point,
    requested_coordinates:{longitude:point.longitude,latitude:point.latitude,coordinate_system:'GCJ-02'},query_coordinates:{longitude:point.longitude,latitude:point.latitude,coordinate_system:'GCJ-02'},
    field_time:new Date(start).toISOString(),period_start:new Date(start).toISOString(),period_end:new Date(end).toISOString(),light_policy:'period_end_proxy',
    observed_at:new Date(now-300_000).toISOString(),light_time:new Date(end).toISOString(),fetched_at:new Date(now).toISOString(),expires_at:new Date(end).toISOString(),cached:false,
    weather:{bg_temp:9.6,bg_rh:61,bg_light:33000},weather_units:{bg_temp:'°C',bg_rh:'%',bg_light:'lux'},
    light_conversion:{source_value:300,source_unit:'W/m²',target_value:33000,target_unit:'lux',factor:110,estimated:true,method:'daylight_constant_v1'},attributions:[]}
}
export function makeWeatherQuery(point=testMonitoringLocation):WeatherQueryResult{
  const {period_start,period_end,...base}=makePeriodWeatherQuery(point)
  return {...base,monitoring_mode:'single_shot',field_time:new Date().toISOString(),expires_at:new Date(Date.now()+900_000).toISOString(),
    light_policy:'single_shot_nearest_forecast',light_lead_seconds:Math.round((Date.parse(base.light_time!)-Date.now())/1000)}
}
