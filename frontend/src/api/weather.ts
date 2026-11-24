import type { Greenhouse } from './accounts'
import type { VolumePayload, LiveStatus } from './types'
import { getJson, postJson } from './client'
import type { RegionInput, RegionInfo } from './regions'
import type { MonitoringLocation } from '../live/monitoringLocation'
import type { ExternalWeatherObservation } from './types'
import type { HouseDimensions } from '../live/houseDimensions'
export interface WeatherQueryResult {
  query_id: string; source_fingerprint: string
  provider: 'qweather'; data_kind: 'current' | 'forecast'; location: RegionInfo
  requested_coordinates: { latitude: number; longitude: number; coordinate_system: 'GCJ-02' }
  query_coordinates: { latitude: number; longitude: number; coordinate_system: 'GCJ-02' }
  observed_at?: string; light_time?: string|null; forecast_time?: string
  field_time?: string; period_start?: string; period_end?: string; light_policy?: string; light_fetched_at?: string
  monitoring_mode?: 'single_shot'; light_lead_seconds?: number
  construction_ready: boolean; detail?: string
  fetched_at: string; expires_at: string; cached: boolean
  weather: ExternalWeatherObservation
  weather_units: { bg_temp: string; bg_rh: string; bg_light: string }
  light_conversion: { source_value: number; source_unit: string; target_value: number; target_unit: string; factor: number; estimated: boolean; method: string } | null
  attributions: string[]
}
export interface WeatherSummary {
  source: 'virtual_weather_prediction'; time: string; mean: number | null; vmin: number; vmax: number
  stage1_mode: 'history_1h' | 'current_only'; humidity_source: 'observed_external' | 'predicted_external'
  background_humidity_used: number; node_temperatures: number[]; warnings: string[]
  training_bounds?: Record<string, [number,number]>
  model_id: number; package_id: string; external_schema: 'two' | 'full'
}
export interface WeatherFrame {
  id: string; greenhouse_id: string; weather_model_id: string; observed_at: string
  bg_temp: number; bg_light: number; bg_rh: number | null; summary: WeatherSummary
  location?: RegionInfo | null; archive_snapshot?: Greenhouse | null
}
export interface AutomaticFieldResult extends WeatherFrame { live: LiveStatus }
export interface WeatherInput { greenhouse_id?: string; location: RegionInput; timestamp: string; bg_temp: number; bg_light: number; bg_rh?: number }
export interface ProfileSelection { archive: Greenhouse; selection_mode: 'single' | 'explicit' }
const base = (id: string) => `/api/user/greenhouses/${encodeURIComponent(id)}`
export const weatherApi = {
  construct: (query_id: string, dimensions?: HouseDimensions) => postJson<AutomaticFieldResult>('/api/live/weather/construct', dimensions ? {query_id,dimensions} : {query_id}),
  prototype:()=>getJson<{ready:boolean;detail?:string;reference_id?:string;reference_dimensions:HouseDimensions}>('/api/live/prototype'),
  query: (point: MonitoringLocation) => postJson<WeatherQueryResult>('/api/live/weather/query', {
    location: {province_code:point.province_code,city_code:point.city_code,...(point.district_code?{district_code:point.district_code}:{})},
    latitude:point.latitude,longitude:point.longitude,coordinate_system:point.coordinate_system,
  }),
  houses: () => getJson<Greenhouse[]>('/api/user/greenhouses'),
  match: (greenhouse_id?: string) => postJson<ProfileSelection>('/api/user/weather/match', greenhouse_id ? { greenhouse_id } : {}),
  frames: (id: string, offset = 0, regionCode?: string) => getJson<WeatherFrame[]>(`${base(id)}/frames?limit=20&offset=${offset}${regionCode ? `&region_code=${encodeURIComponent(regionCode)}` : ''}`),
  submit: (input: WeatherInput) => postJson<WeatherFrame>('/api/user/weather', input),
  field: (id: string, frame: string) => getJson<{ summary: WeatherSummary; field: VolumePayload }>(`${base(id)}/frames/${encodeURIComponent(frame)}/field`),
}
