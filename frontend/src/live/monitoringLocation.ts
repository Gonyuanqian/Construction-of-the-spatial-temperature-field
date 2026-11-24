import type { RegionCatalog, RegionInfo } from '../api/regions'

export type Coordinate = [number, number]
export interface MonitoringLocation extends RegionInfo {
  longitude: number
  latitude: number
  coordinate_system: 'GCJ-02'
}
export interface DistrictFeature {
  type: 'Feature'
  properties: { code: string; name: string; city_code: string; city_name: string; center: Coordinate }
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: Coordinate[][] | Coordinate[][][] }
}
export interface LocationMapData {
  type: 'FeatureCollection'
  coordinate_system: 'GCJ-02'
  source_url: string
  cities: { code: number; center: Coordinate }[]
  features: DistrictFeature[]
}
export function polygons(feature: DistrictFeature): Coordinate[][][] {
  return feature.geometry.type === 'Polygon'
    ? [feature.geometry.coordinates as Coordinate[][]] : feature.geometry.coordinates as Coordinate[][][]
}
function inRing(point: Coordinate, ring: Coordinate[]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i]!, b = ring[j]!
    const cross = (point[0]-a[0])*(b[1]-a[1])-(point[1]-a[1])*(b[0]-a[0])
    if (Math.abs(cross) < 1e-10 && point[0] >= Math.min(a[0],b[0]) && point[0] <= Math.max(a[0],b[0]) && point[1] >= Math.min(a[1],b[1]) && point[1] <= Math.max(a[1],b[1])) return true
    if ((a[1] > point[1]) !== (b[1] > point[1]) && point[0] < (b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0]) inside = !inside
  }
  return inside
}
export function districtAt(data: LocationMapData, point: Coordinate) {
  return data.features.find(feature => polygons(feature).some(rings => inRing(point, rings[0]!) && !rings.slice(1).some(ring => inRing(point, ring))))
}
export function selectedPoint(catalog: RegionCatalog, data: LocationMapData, region: RegionInfo): MonitoringLocation | null {
  const point = region.district_code
    ? data.features.find(f => f.properties.code === region.district_code)?.properties.center
    : data.cities.find(c => String(c.code) === region.city_code)?.center
  if (!point || !catalog.cities.some(c => c.code === region.city_code)) return null
  return { ...region, longitude: point[0], latitude: point[1], coordinate_system: 'GCJ-02' }
}
export function locationAt(catalog: RegionCatalog, data: LocationMapData, point: Coordinate): MonitoringLocation | null {
  if (!point.every(Number.isFinite)) return null
  const feature = districtAt(data, point)
  const city = catalog.cities.find(c => c.code === feature?.properties.city_code)
  const district = city?.districts.find(d => d.code === feature?.properties.code)
  return city && district ? { province_code: catalog.province.code, province_name: catalog.province.name,
    city_code: city.code, city_name: city.name, district_code: district.code, district_name: district.name,
    longitude: Number(point[0].toFixed(6)), latitude: Number(point[1].toFixed(6)), coordinate_system: 'GCJ-02' } : null
}
export function searchLocations(catalog: RegionCatalog, query: string): RegionInfo[] {
  const value = query.trim().replace(/\s+/g, '')
  if (!value) return []
  const matches: RegionInfo[] = []
  for (const city of catalog.cities) {
    const base = { province_code: catalog.province.code, province_name: catalog.province.name, city_code: city.code, city_name: city.name }
    if (`${catalog.province.name}${city.name}`.includes(value)) matches.push(base)
    for (const district of city.districts) {
      if (`${catalog.province.name}${city.name}${district.name}`.includes(value)) matches.push({ ...base, district_code: district.code, district_name: district.name })
    }
  }
  return matches.slice(0, 12)
}
export function sameRegion(a: RegionInfo | null | undefined, b: RegionInfo | null | undefined) {
  return !!a && !!b && a.province_code === b.province_code && a.city_code === b.city_code && (a.district_code ?? '') === (b.district_code ?? '')
}
export function validStoredLocation(value: unknown): value is MonitoringLocation {
  if (!value || typeof value !== 'object') return false
  const p = value as MonitoringLocation
  return p.province_code === '220000' && /^22\d{4}$/.test(p.city_code) && typeof p.city_name === 'string' && typeof p.province_name === 'string'
    && (!p.district_code || /^22\d{4}$/.test(p.district_code)) && p.coordinate_system === 'GCJ-02'
    && Number.isFinite(p.longitude) && Number.isFinite(p.latitude) && p.longitude >= -180 && p.longitude <= 180 && p.latitude >= -90 && p.latitude <= 90
}
