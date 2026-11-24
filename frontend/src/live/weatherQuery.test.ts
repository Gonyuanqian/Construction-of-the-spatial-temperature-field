import {expect,it,vi} from 'vitest'
import {fieldMatchesQuery,savedSingleMatchesLocation,savedSingleQuery} from './weatherQuery'
import {makeWeatherQuery,makePeriodWeatherQuery} from '../test/weatherQueryFixture'
import {makeLiveStatus} from '../test/fixtures'
it('同地区的旧时刻或不同输入构场不能冒充新查询结果',()=>{
  const query=makeWeatherQuery(),saved=makeLiveStatus({time:query.field_time,weather:query.weather,weather_source:{provider:'qweather',source_fingerprint:query.source_fingerprint}})
  expect(fieldMatchesQuery(saved,query)).toBe(true)
  expect(fieldMatchesQuery({...saved,time:'2026-07-23T12:00:00+08:00'},query)).toBe(false)
  expect(fieldMatchesQuery({...saved,weather:{...query.weather,bg_temp:25}},query)).toBe(false)
  expect(fieldMatchesQuery(saved,null)).toBe(false)
  expect(fieldMatchesQuery({...saved,weather_source:{provider:'qweather',source_fingerprint:'other-grid-or-revision'}},query)).toBe(false)
  expect(fieldMatchesQuery({...saved,weather_source:null},query)).toBe(false)
})
it('周期内保持同一份近似场，到周期结束才失效',()=>{
  vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-10T07:30:00Z'))
  try{
    const query={...makePeriodWeatherQuery(),observed_at:'2026-11-10T07:15:00Z'}
    const saved=makeLiveStatus({time:query.field_time,weather:query.weather,weather_source:{provider:'qweather',source_fingerprint:query.source_fingerprint}})
    vi.setSystemTime(new Date('2026-11-10T07:44:59Z'));expect(fieldMatchesQuery(saved,query)).toBe(true)
    vi.setSystemTime(new Date('2026-11-10T07:45:00Z'));expect(fieldMatchesQuery(saved,query)).toBe(false)
  }finally{vi.useRealTimers()}
})
it('单次快照不因时间推进而失效，恢复时仍保留原时刻且不能冒充其他选点',()=>{
 const query=makeWeatherQuery(),point={...query.location,...query.requested_coordinates}
 const saved=makeLiveStatus({state:'ready',time:query.field_time,location:query.location,weather:query.weather,
  weather_source:{provider:'qweather',data_kind:'current',monitoring_mode:'single_shot',source_fingerprint:query.source_fingerprint,
   field_time:query.field_time,observed_at:query.observed_at,light_time:query.light_time!,fetched_at:query.fetched_at,
   requested_coordinates:query.requested_coordinates,query_coordinates:query.query_coordinates}})
 vi.useFakeTimers();try{
  vi.setSystemTime(Date.now()+86_400_000)
  expect(fieldMatchesQuery(saved,query)).toBe(true)
  expect(savedSingleMatchesLocation(saved,point)).toBe(true)
  expect(savedSingleMatchesLocation(saved,{...point,longitude:point.longitude+1})).toBe(false)
  expect(savedSingleQuery(saved)?.fetched_at).toBe(query.fetched_at)
  expect(savedSingleQuery(saved)?.query_id).toBe('')
  vi.setSystemTime(Date.parse(query.field_time!)-86_400_000)
  expect(fieldMatchesQuery(saved,query)).toBe(true)
 }finally{vi.useRealTimers()}
})
