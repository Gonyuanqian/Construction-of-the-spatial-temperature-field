import {it,expect,vi} from 'vitest'
import {designsApi,newDesign} from '../api/greenhouseDesigns'
import {requestedDesign} from './designSelection'
vi.mock('../api/greenhouseDesigns',async original=>({...await original<object>(),designsApi:{active:vi.fn()}}))
it('应用前核对服务器保存的方案版本，拒绝篡改引用',async()=>{vi.mocked(designsApi.active).mockResolvedValue({selection:{id:'real',revision:2,spec:newDesign()}});await expect(requestedDesign('forged','2')).rejects.toThrow('版本已改变')})
it('只将支持的小拱棚尺寸与有效地点传给监测',async()=>{const spec=newDesign();Object.assign(spec.location,{longitude:126.42,latitude:41.94,province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市'});vi.mocked(designsApi.active).mockResolvedValue({selection:{id:'real',revision:2,spec}});expect((await requestedDesign('real','2')).dimensions).toEqual({length_m:18,width_m:6,height_m:2.4});spec.structure.type='multi_span';await expect(requestedDesign('real','2')).rejects.toThrow('暂不能')})
