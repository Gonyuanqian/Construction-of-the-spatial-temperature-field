import type { RegionCatalog, RegionInput } from '../api/regions'

export const WEATHER_COLUMNS = ['背景温度', '背景湿度', '背景光照强度', '省份', '城市'] as const
export interface WeatherDemoRow { bg_temp: number; bg_rh: number; bg_light: number; location: RegionInput; region: string }

/** RFC 4180 fields, including BOM, CRLF and quoted names; no spreadsheet formulas. */
function csvRows(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = [], value = '', quoted = false, closed = false
  for (let i=0; i<text.length; i++) {
    const c=text[i]
    if (quoted) {
      if (c === '"' && text[i+1] === '"') { value+='"'; i++ }
      else if (c === '"') { quoted=false; closed=true }
      else value+=c
    } else if (c === '"') {
      if (value || closed) throw new Error('CSV 引号格式无效。')
      quoted=true
    } else if (c === ',' || c === '\r' || c === '\n') {
      row.push(value); value=''; closed=false
      if (c !== ',') {
        if (row.some(v=>v.trim())) rows.push(row)
        row=[]; if (c === '\r' && text[i+1] === '\n') i++
      }
    } else {
      if (closed) throw new Error('CSV 引号后的分隔符无效。')
      value+=c
    }
  }
  if (quoted) throw new Error('CSV 引号未闭合。')
  row.push(value); if (row.some(v=>v.trim())) rows.push(row)
  return rows
}

export function parseWeatherCsv(text: string, catalog: RegionCatalog): WeatherDemoRow[] {
  if (text.length > 2*1024*1024) throw new Error('演示 CSV 不能超过 2 MB。')
  const rows=csvRows(text.replace(/^\uFEFF/, ''))
  const header=rows.shift()?.map(v=>v.trim()) ?? []
  if (header.length !== 5 || new Set(header).size !== 5 || WEATHER_COLUMNS.some(key=>!header.includes(key)))
    throw new Error(`CSV 只能包含五列：${WEATHER_COLUMNS.join('、')}。`)
  if (!rows.length || rows.length > 2000) throw new Error('演示文件需包含 1 至 2000 行数据。')
  return rows.map((row, i) => {
    const fail=(reason: string): never=>{throw new Error(`第 ${i+2} 行：${reason}`)}
    if (row.length !== 5) return fail('列数应为 5。')
    const cell=(key: typeof WEATHER_COLUMNS[number])=>row[header.indexOf(key)]!.trim()
    const numeric=(key: typeof WEATHER_COLUMNS[number])=> {
      const raw=cell(key), n=Number(raw)
      if (!raw || !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw) || !Number.isFinite(n)) return fail(`${key}需填写有限数值。`)
      return n
    }
    const bg_temp=numeric('背景温度'), bg_rh=numeric('背景湿度'), bg_light=numeric('背景光照强度')
    if (bg_rh < 0 || bg_rh > 100 || bg_light < 0) return fail('湿度需为 0–100，光照不能为负。')
    if (![catalog.province.name,catalog.province.code].includes(cell('省份'))) return fail('省份不在当前地区库中。')
    const city=catalog.cities.find(city=>[city.name,city.code].includes(cell('城市')))
    if (!city) return fail('城市不在当前省份中。')
    return {bg_temp,bg_rh,bg_light,location:{province_code:catalog.province.code,city_code:city.code},region:`${catalog.province.name} ${city.name}`}
  })
}
