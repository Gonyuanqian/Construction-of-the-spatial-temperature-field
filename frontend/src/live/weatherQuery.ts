import type {LiveStatus} from '../api/types'
import type {WeatherQueryResult} from '../api/weather'
import {sameRegion,validStoredLocation,type MonitoringLocation} from './monitoringLocation'

/** Only display a saved field beside the query whose valid time and inputs it used. */
export function fieldMatchesQuery(saved:LiveStatus,queried:WeatherQueryResult|null) {
  if(!queried || queried.data_kind!=='current' || !queried.construction_ready || Date.parse(saved.time??'')!==Date.parse(queried.field_time??queried.observed_at??''))return false
  const observedTime=Date.parse(queried.observed_at??''),lightTime=Date.parse(queried.light_time??''),now=Date.now()
  if(!Number.isFinite(observedTime)||!Number.isFinite(lightTime))return false
  if(queried.monitoring_mode==='single_shot'){
    // A saved single result is independent of the browser's wall clock.
  }else if(observedTime>now)return false
  else if(queried.period_start&&queried.period_end){
    const start=Date.parse(queried.period_start),end=Date.parse(queried.period_end)
    if(!Number.isFinite(start)||!Number.isFinite(end)||now<start||now>=end||lightTime<start||lightTime>end)return false
  }else if(now-observedTime>1_800_000||Math.abs(now-lightTime)>900_000)return false
  if(saved.weather_source?.data_kind==='forecast')return false
  if(saved.weather_source?.source_fingerprint!==queried.source_fingerprint)return false
  const observed=saved.weather
  if(!observed)return false
  return observed.bg_temp===queried.weather.bg_temp && observed.bg_light===queried.weather.bg_light
    && (observed.bg_rh==null || observed.bg_rh===queried.weather.bg_rh)
}
export function savedSingleMatchesLocation(saved:LiveStatus,point:MonitoringLocation){
  const source=saved.weather_source
  if(source?.monitoring_mode!=='single_shot'||!sameRegion(saved.location,point))return false
  const exact=source.requested_coordinates,grid=source.query_coordinates
  if(exact)return Number.isFinite(exact.latitude)&&Number.isFinite(exact.longitude)&&Math.abs(exact.latitude-point.latitude)<.000001&&Math.abs(exact.longitude-point.longitude)<.000001
  return !!grid&&Math.abs(grid.latitude-Number(point.latitude.toFixed(2)))<.000001&&Math.abs(grid.longitude-Number(point.longitude.toFixed(2)))<.000001
}
export function savedSingleLocation(saved:LiveStatus):MonitoringLocation|null{
  if(saved.weather_source?.monitoring_mode!=='single_shot'||!saved.location)return null
  const coordinate=saved.weather_source.requested_coordinates??saved.weather_source.query_coordinates
  const point=coordinate?{...saved.location,...coordinate}:null
  return validStoredLocation(point)?point:null
}
/** Display-only reconstruction; an old saved snapshot never becomes a construction ticket. */
export function savedSingleQuery(saved:LiveStatus|null):WeatherQueryResult|null{
  const source=saved?.weather_source
  if(!saved?.weather||!saved.location||source?.monitoring_mode!=='single_shot'||!source.fetched_at||!source.observed_at||!source.light_time)return null
  const coordinates=source.query_coordinates??source.requested_coordinates
  if(!coordinates)return null
  return {query_id:'',source_fingerprint:source.source_fingerprint,provider:'qweather',data_kind:'current',monitoring_mode:'single_shot',
    construction_ready:true,location:saved.location,requested_coordinates:source.requested_coordinates??coordinates,query_coordinates:coordinates,
    field_time:source.field_time??saved.time,observed_at:source.observed_at,light_time:source.light_time,fetched_at:source.fetched_at,
    expires_at:source.fetched_at,cached:true,weather:saved.weather,weather_units:{bg_temp:'°C',bg_rh:'%',bg_light:'lux'},
    light_conversion:saved.light_conversion??null,light_lead_seconds:source.light_lead_seconds,attributions:source.attributions??[]}
}
