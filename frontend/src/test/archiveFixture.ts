import type { Greenhouse } from '../api/accounts'
import type { RegionCatalog, RegionInfo } from '../api/regions'
export const testRegion: RegionInfo = { province_code: '220000', province_name: '吉林省', city_code: '220600', city_name: '白山市' }
export const testRegionCatalog: RegionCatalog = { province: { code: '220000', name: '吉林省' }, source_url: '', verified_at: '2026-11-04', cities: [{ code: '220600', name: '白山市', districts: [{ code: '220621', name: '抚松县' }, { code: '220622', name: '靖宇县' }] }, { code: '220200', name: '吉林市', districts: [] }] }
export const testArchive: Greenhouse = { id: 'h1', name: '白山市默认人参棚', location: testRegion, location_text: '', geometry_key: 'ginseng_arch_v1', length_m: 18, width_m: 2.1, height_m: 1.3017, enabled: true, weather_model_id: 'm1', weather_model_name: '气象模型', model_status: 'PUBLISHED', external_schema: 'two', revision: 0, ready: true, geometry_compatible: true, unavailable_reason: '' }
