import { expect, it } from 'vitest'
import { parseWeatherCsv } from './weatherCsv'
import { testRegionCatalog } from '../test/archiveFixture'
const header='背景温度,背景湿度,背景光照强度,省份,城市'
it('只读取五列并保留零值，支持 BOM 和带引号字段',()=>{
  const rows=parseWeatherCsv('\uFEFF'+header+'\r\n0,70.5,0,"吉林省","白山市"\r\n',testRegionCatalog)
  expect(rows).toEqual([{bg_temp:0,bg_rh:70.5,bg_light:0,location:{province_code:'220000',city_code:'220600'},region:'吉林省 白山市'}])
})
it.each([
  header+',timestamp\n25,60,100,吉林省,白山市,2026-11-06',
  header+'\n,60,100,吉林省,白山市',
  header+'\n25,101,100,吉林省,白山市',
  header+'\n25,60,-1,吉林省,白山市',
  header+'\n25,60,100,辽宁省,白山市',
  header+'\n25,60,100,吉林省,不存在市',
  header+'\n=1+1,60,100,吉林省,白山市',
  header+'\n25,60,100,吉林省,"白山市',
])('无效演示输入在提交前拒绝：%s',input=>{expect(()=>parseWeatherCsv(input,testRegionCatalog)).toThrow()})
it('保留所有顺序与数值，不自动采样或插值',()=>{
  const rows=parseWeatherCsv(header+'\n25.1234,60.4321,12345.6789,220000,220600\n26,61,0,吉林省,白山市',testRegionCatalog)
  expect(rows.map(r=>[r.bg_temp,r.bg_rh,r.bg_light])).toEqual([[25.1234,60.4321,12345.6789],[26,61,0]])
})
