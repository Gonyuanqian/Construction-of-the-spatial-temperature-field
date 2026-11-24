import { getJson } from './client'
export interface RegionInput { province_code: string; city_code: string; district_code?: string }
export interface RegionInfo extends RegionInput { province_name: string; city_name: string; district_name?: string }
export interface RegionOption { code: string; name: string }
export interface RegionCatalog { province: RegionOption; cities: (RegionOption & { districts: RegionOption[] })[]; source_url: string; verified_at: string }
export const regionApi = { list: () => getJson<RegionCatalog>('/api/user/regions') }
export function regionText(value: RegionInfo | null | undefined) { return value ? [value.province_name, value.city_name, value.district_name].filter(Boolean).join(' · ') : '待补充地区' }
