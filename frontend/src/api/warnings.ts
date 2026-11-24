import { getJson, postJson, writeJson } from './client'

export type WarningCategory = 'temperature' | 'device'
export interface TemperatureLimits { low: number; high: number }
export interface WarningSettings { saved: boolean; temperature: TemperatureLimits | null }
export interface WarningEvent {
  id: string
  category: WarningCategory
  design_id: string | null
  greenhouse_name: string
  device_name: string | null
  alert_type: 'high' | 'low' | 'expired' | 'skipped' | 'failed'
  source: string
  operation: string | null
  result: {detail?: string; reason?: string; task_id?: string} | null
  trigger_frame_id: string | null
  event_time: string
  last_seen_at: string | null
  threshold_value: number | null
  trigger_value: number | null
  extreme_value: number | null
  ended_at: string | null
  end_reason: 'recovered' | 'rule_changed' | null
  acknowledged_at: string | null
  acknowledged_by: string | null
}
export interface WarningGreenhouse { id: string; name: string; archived: boolean }
export interface WarningList { items: WarningEvent[]; total: number; greenhouses: WarningGreenhouse[] }

const base = '/api/user/alerts'
const path = (item: WarningEvent) => `${base}/${item.category}/${encodeURIComponent(item.id)}`
export const warningsApi = {
  list: (filters: Record<string, string>) => getJson<WarningList>(`${base}?${new URLSearchParams(filters)}`),
  acknowledge: (item: WarningEvent) => postJson<WarningEvent>(path(item) + '/acknowledge', {}),
  settings: () => getJson<WarningSettings>(base + '/settings'),
  saveSettings: (temperature: TemperatureLimits | null, initialize = false) =>
    writeJson<WarningSettings>('PUT', base + '/settings' + (initialize ? '?initialize=true' : ''), { temperature }),
}
