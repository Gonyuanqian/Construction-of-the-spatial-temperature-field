import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import LiveWeatherOverview from './LiveWeatherOverview.vue'
import {makeWeatherQuery} from '../test/weatherQueryFixture'

it('左侧省市与三项气象横排，使用实际外部输入且不提供配置源入口', () => {
  const w=mount(LiveWeatherOverview,{props:{observation:{bg_temp:23.4,bg_rh:65.2,bg_light:780},location:{province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市',district_code:'220621',district_name:'抚松县'}}})
  expect(w.findAll('.label').map(cell=>cell.text())).toEqual(['外部温度','相对湿度','光照强度'])
  expect(w.findAll('.value').map(cell=>cell.text())).toEqual(['23.4 °C','65.2 %','780'])
  expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
  expect(w.text()).not.toContain('抚松县')
  expect(w.text()).toContain('源数据单位')
  expect(w.text()).toContain('已保存气象数据')
  expect(w.text()).not.toContain('配置气象源')
  expect(w.text()).not.toContain('示例数据')
})

it('无数据保留四项占位，不预设地区或补成零', () => {
  const w=mount(LiveWeatherOverview)
  expect(w.findAll('.value').map(cell=>cell.text())).toEqual(['暂无','暂无','暂无'])
  expect(w.get('.region-selector').text()).toBe('选择省市地区')
  expect(w.text()).not.toContain('吉林省')
})

it('零值有效，缺少的外部湿度明确显示未提供', () => {
  const w=mount(LiveWeatherOverview,{props:{observation:{bg_temp:0,bg_rh:null,bg_light:0}}})
  expect(w.findAll('.value').map(cell=>cell.text())).toEqual(['0.0 °C','未提供','0'])
})

it('非有限气象值不当作有效读数', () => {
  const w=mount(LiveWeatherOverview,{props:{observation:{bg_temp:Number.NaN,bg_rh:Infinity,bg_light:-Infinity}}})
  expect(w.findAll('.value').map(cell=>cell.text())).toEqual(['暂无','暂无','暂无'])
})

it('地区沿用已有气象入口，刷新只发出状态读取事件', async () => {
  const w=mount(LiveWeatherOverview,{props:{observation:{bg_temp:25,bg_rh:60,bg_light:42800}}})
  expect(w.get('.weather-cell:last-of-type .value').text()).toBe('42,800')
  await w.get('.region-selector').trigger('click')
  expect(w.emitted('select-region')).toHaveLength(1)
  await w.get('button[aria-label="重新构场"]').trigger('click')
  expect(w.emitted('refresh')).toHaveLength(1)
  await w.setProps({refreshing:true})
  expect(w.get('button[aria-label="重新构场"]').attributes('disabled')).toBeDefined()
})
it('已查询气象保留来源名称和光照单位，收起技术明细及原始来源链接',()=>{
  const query=makeWeatherQuery();query.attributions=['https://developer.qweather.com/weather/attribution.html','数据来源声明']
  const w=mount(LiveWeatherOverview,{props:{query,observation:query.weather,location:query.location}})
  expect(w.text()).toContain('和风天气');expect(w.text()).toContain('单次构场');expect(w.text()).toContain('lux · 预报近似')
  expect(w.text()).not.toContain('本次构场信息')
  expect(w.text()).not.toContain('数据来源声明')
  expect(w.find('a[href="https://developer.qweather.com/weather/attribution.html"]').exists()).toBe(false)
  expect(w.find('a[href="https://www.qweather.com"]').exists()).toBe(true)
  expect(w.text()).not.toContain('实时实测')
})
it('查询中和错误状态不冒充已成功连接',async()=>{
  const w=mount(LiveWeatherOverview,{props:{querying:true}})
  expect(w.text()).toContain('正在查询气象')
  await w.setProps({querying:false,queryError:'服务不可用'});expect(w.text()).toContain('查询失败，请重新构场')
  expect(w.get('.api-state').attributes('title')).toContain('服务不可用')
})
it('缓存命中保持气象读数与单次构场操作提示',async()=>{
  const query={...makeWeatherQuery(),period_start:'2026-11-10T06:00:00Z',period_end:'2026-11-10T06:15:00Z',observed_at:'2026-11-10T06:10:00Z',light_time:'2026-11-10T06:15:00Z',fetched_at:'2026-11-10T06:14:00Z',expires_at:'2026-11-10T06:15:00Z',cached:false}
  const w=mount(LiveWeatherOverview,{props:{query,observation:query.weather,location:query.location}})
  const readings=w.findAll('.value').map(cell=>cell.text())
  expect(w.find('details').exists()).toBe(false)
  expect(w.get('.api-state').attributes('title')).toContain('本次结果保持不变')
  await w.setProps({query:{...query,cached:true}})
  expect(w.findAll('.value').map(cell=>cell.text())).toEqual(readings)
  expect(w.get('.api-state').attributes('title')).toContain('本次结果保持不变')
})
it('没有15分钟内光照时保留实况温湿度，不补零或沿用未来预报',()=>{
  const query={...makeWeatherQuery(),construction_ready:false,light_time:null,light_conversion:null,weather:{bg_temp:5.01,bg_rh:27,bg_light:null}}
  const w=mount(LiveWeatherOverview,{props:{query,observation:query.weather}})
  expect(w.findAll('.value').map(cell=>cell.text())).toEqual(['5.0 °C','27.0 %','暂无'])
  expect(w.text()).toContain('光照暂不可用')
  expect(w.find('.forecast-time').exists()).toBe(false)
  expect(w.get('.api-state').classes()).not.toContain('received')
})
