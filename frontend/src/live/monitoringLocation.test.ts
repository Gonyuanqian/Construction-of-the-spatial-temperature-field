import {expect,it} from 'vitest'
import {locationAt,searchLocations,districtAt,sameRegion} from './monitoringLocation'
import {testRegionCatalog,testRegion} from '../test/archiveFixture'
import {testLocationMap} from '../test/locationMapFixture'
it('搜索支持市县组合，空查询不默认命中一个地点',()=>{
  expect(searchLocations(testRegionCatalog,'白山市 抚松')).toEqual([expect.objectContaining({district_code:'220621'})])
  expect(searchLocations(testRegionCatalog,'')).toEqual([])
  expect(searchLocations(testRegionCatalog,'北京')).toEqual([])
})
it('点选按实际多边形确定区县，区外和孔洞不会被最近中心误选',()=>{
  expect(locationAt(testRegionCatalog,testLocationMap,[127,42])).toEqual(expect.objectContaining({district_code:'220621'}))
  expect(locationAt(testRegionCatalog,testLocationMap,[120,42])).toBeNull()
  const withHole=structuredClone(testLocationMap)
  ;(withHole.features[0]!.geometry.coordinates as [number,number][][]).push([[126.5,41.5],[127.5,41.5],[127.5,42.5],[126.5,42.5],[126.5,41.5]])
  expect(districtAt(withHole,[127,42])).toBeUndefined()
})
it('行政区相同才允许展示已有气象，区县不同不借用旧结果',()=>{
  expect(sameRegion(testRegion,{...testRegion})).toBe(true)
  expect(sameRegion(testRegion,{...testRegion,district_code:'220621'})).toBe(false)
  expect(sameRegion(testRegion,null)).toBe(false)
})
