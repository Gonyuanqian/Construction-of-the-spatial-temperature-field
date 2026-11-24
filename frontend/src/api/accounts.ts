import { getJson, postJson, writeJson } from './client'
import type { Account } from './session'
import type { RegionInfo } from './regions'
export type AccountEdit = Pick<Account, 'display_name' | 'role' | 'enabled'>
export const accountApi = {
  get: (id: string) => getJson<Account>(`/api/admin/users/${encodeURIComponent(id)}`),
  list: (limit = 20, offset = 0) => getJson<{ items: Account[]; total: number }>(`/api/admin/users?limit=${limit}&offset=${offset}`),
  create: (body: { username: string; display_name: string; password: string; role: Account['role'] }) => postJson<Account>('/api/admin/users', body),
  update: (id: string, body: AccountEdit) => writeJson<Account>('PATCH', `/api/admin/users/${encodeURIComponent(id)}`, body),
  password: (id: string, password: string) => postJson(`/api/admin/users/${encodeURIComponent(id)}/password`, { password }),
}
export interface Greenhouse {
  id: string; name: string; geometry_key: string; enabled: boolean
  weather_model_id: string | null; weather_model_name: string | null
  model_status: 'DRAFT' | 'PUBLISHED' | 'DISABLED' | null
  external_schema: 'two' | 'full' | null
  /** Only legacy historical snapshots may contain geographic archive fields. */
  location?: RegionInfo | null; location_text?: string
  length_m: number | null; width_m: number | null; height_m: number | null
  ready: boolean; unavailable_reason: string; geometry_compatible: boolean; revision: number
}
export interface GreenhouseEdit { name: string; length_m: number; width_m: number; height_m: number; enabled: boolean }
export interface WeatherDeployment {
  id: string; name: string; model_id: number; package_id: string
  external_schema: 'two' | 'full'; status: 'DRAFT' | 'PUBLISHED' | 'DISABLED'
  g_training_job_id?: string | null; g_name?: string | null; field_model_name?: string
}
export const greenhouseApi = {
  list: () => getJson<Greenhouse[]>('/api/admin/greenhouses'),
  create: (body: GreenhouseEdit) => postJson<Greenhouse>('/api/admin/greenhouses', body),
  update: (id: string, body: GreenhouseEdit) => writeJson<Greenhouse>('PATCH', `/api/admin/greenhouses/${id}`, body),
  models: () => getJson<WeatherDeployment[]>('/api/admin/weather-models'),
  bind: (id: string, weather_model_id: string) => writeJson<Greenhouse>('PUT', `/api/admin/greenhouses/${id}/weather-model`, { weather_model_id }),
}
