import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import LiveView from './LiveView.vue'
import { createAppRouter } from '../router'
import { loginAs } from '../test/authFixture'
import { clearSession } from '../api/session'
import { testArchive, testRegionCatalog } from '../test/archiveFixture'
import { makeLiveFramePayload, makeLiveStatus, makeVolumePayload } from '../test/fixtures'
import { makeWeatherQuery, testMonitoringLocation } from '../test/weatherQueryFixture'
import { newDesign, type DesignRecord } from '../api/greenhouseDesigns'
import LiveGreenhouseDialog from '../components/LiveGreenhouseDialog.vue'
import type { WarningSettings } from '../api/warnings'

vi.mock('../design/palette', () => ({ readPalette: () => ({
  paper: '#071D38', ink: '#FFFFFF', inkMuted: '#89A9C8', steel: '#223E5E',
  leaf: '#00CFFF', leafSoft: '#102E50', net: '#223E5E', layerTop: '#C44E52',
  layerMid: '#4C72B0', layerLow: '#55A868', bar: '#D98C2B', chartAxis: 12, chartTitle: 14,
}) }))
vi.mock('../charts/EChart.vue', () => ({ default: { template: '<div class="chart-stub" />' } }))
vi.mock('../scene/VolumeView.vue', () => ({ __esModule: true, default: { name: 'VolumeView', template: '<div class="volume-stub">有效温度场</div>' } }))

let currentStatus = makeLiveStatus({ state: 'idle', total: 0, cursor: 0 })
let houses = false
let catalogFails = false
let statusFails = false
let requests: string[] = []
let frameResponse: ReturnType<typeof makeLiveFramePayload> | null = null
let volumeResponse: ReturnType<typeof makeVolumePayload> | null = null
let queriedWeather = makeWeatherQuery()
let plans:DesignRecord[]=[]
let appliedPlan:DesignRecord|null=null
let activationFails=false
let warningSettings:WarningSettings
enableAutoUnmount(afterEach)
beforeEach(() => {
  loginAs('USER')
  localStorage.clear()
  houses = false; catalogFails = false; statusFails = false; requests = []
  currentStatus = makeLiveStatus({ state: 'idle', total: 0, cursor: 0 })
  frameResponse = null
  volumeResponse = null
  queriedWeather = makeWeatherQuery()
  plans=[];appliedPlan=null;activationFails=false
  warningSettings={saved:false,temperature:null}
  document.body.innerHTML = '<aside id="shell-side"></aside><div id="rail-extra"></div>'
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    requests.push(`${init?.method ?? 'GET'} ${url}`)
    if (url.startsWith('/api/user/alerts/settings')) {
      if (init?.method === 'PUT') warningSettings={saved:true,...JSON.parse(String(init.body))}
      return new Response(JSON.stringify(warningSettings))
    }
    const constructing=url==='/api/live/weather/construct'
    const activating=url.endsWith('/activate')&&url.startsWith('/api/user/greenhouse-designs/')
    if(activating&&!activationFails)appliedPlan=plans.find(plan=>url.endsWith(`/${plan.id}/activate`))??null
    if(constructing&&houses)currentStatus=makeLiveStatus({state:'ready',session_id:'automatic-field',prototype:true,dimensions:JSON.parse(String(init?.body)).dimensions,location:queriedWeather.location,time:queriedWeather.field_time,weather:queriedWeather.weather,weather_source:{provider:'qweather',source_fingerprint:queriedWeather.source_fingerprint}})
    const failed = activating?activationFails:constructing?!houses:url === '/api/user/greenhouses' ? catalogFails : statusFails && url.startsWith('/api/live/status')
    const body = failed ? { detail: activating?'方案版本已改变，请重新载入。':'服务暂时不可用' }
      : url === '/api/live/prototype' ? {ready:houses}
      : url === '/api/user/greenhouses' ? houses ? [testArchive] : []
      : constructing ? {id:'automatic-field',live:currentStatus}
      : url.startsWith('/api/live/status') ? currentStatus
      : url === '/api/live/weather/query' ? queriedWeather
      : url === '/api/user/greenhouse-designs?limit=100' ? {items:plans,total:plans.length}
      : url === '/api/user/greenhouse-designs/active' ? {selection:appliedPlan}
      : activating ? appliedPlan
      : url.includes('/api/live/frame/') ? frameResponse ?? makeLiveFramePayload({live:{...makeLiveFramePayload().live,session_id:currentStatus.session_id}})
      : url.includes('/api/live/volume/') ? volumeResponse ?? makeVolumePayload({
        live:{session_id:currentStatus.session_id ?? undefined},
        frame:{n:currentStatus.cursor,time:currentStatus.time ?? ''},
      }) : {}
    return new Response(JSON.stringify(body), { status: failed ? activating?409:503 : 200 })
  }))
})
afterEach(() => { document.body.innerHTML = ''; clearSession(); vi.useRealTimers(); vi.unstubAllGlobals() })

async function open(path='/live') {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const wrapper = mount(LiveView, { attachTo: document.body, global: { plugins: [router],stubs:{Teleport:true} } })
  await flushPromises()
  return wrapper
}
function expectPanels() {
  const text = document.body.textContent ?? ''
  for (const label of ['棚体三维温度场', '环境监测预警', '温度分布概览', '三维信息查询', 'AI 农事建议']) expect(text).toContain(label)
  expect(text).not.toContain('三维视图控制')
}

it('阈值可保存，按当前有效网格和棚外气象预警，跳过外推区与旧结果', async () => {
  currentStatus=makeLiveStatus({state:'ready',session_id:'current-grid'})
  const frame=makeLiveFramePayload()
  frameResponse=makeLiveFramePayload({live:{...frame.live,session_id:'current-grid',weather:{bg_temp:25,bg_rh:82,bg_light:700}}})
  const activeVolume=makeVolumePayload({
    live:{session_id:'current-grid'},frame:{n:0,time:frame.frame.time},mean:27.2,
    vmin:-20,vmax:90,stripes:[[3,0]],
    planes:[{y:0,measured:false,shed:null,values:[[19,31,null,90]],mean:27.2}],
  })
  volumeResponse=activeVolume
  const w=await open()
  const panel=()=>w.get('.env-card')
  const badges=()=>panel().findAll('.alert-badge').map(badge=>badge.text())
  expect(panel().text()).toContain('27.2 °C')
  expect(panel().text()).toContain('棚外相对湿度 82%')
  expect(badges()).toEqual(['未设阈值','未设阈值'])
  expect(panel().text()).not.toContain('拱跨宽')
  await panel().get('button').trigger('click')
  const form=()=>panel().get('form')
  const input=(index:number)=>form().findAll('input')[index]!
  await input(0).setValue('20');await input(1).setValue('18')
  await form().trigger('submit')
  expect(form().get('[role="alert"]').text()).toContain('下限须小于上限')
  await input(1).setValue('30');await input(2).setValue('40');await input(3).setValue('82')
  await form().trigger('submit')
  await flushPromises()
  expect(badges()).toEqual(['高温预警','低温预警','偏湿'])
  expect(JSON.parse(localStorage.getItem('tfield.environment-alerts.v1.test-user')!)).toEqual({
    humidity:{low:40,high:82},
  })
  expect(warningSettings).toEqual({saved:true,temperature:{low:20,high:30}})

  volumeResponse={...activeVolume,planes:[{...activeVolume.planes[0]!,values:[[null,25,26,90]]}]}
  frameResponse={...frameResponse,live:{...frameResponse.live,weather:{bg_temp:25,bg_rh:39,bg_light:700}}}
  await w.get('[aria-label="重新构场"]').trigger('click');await flushPromises()
  expect(badges()).toEqual(['正常','偏干'])

  currentStatus=makeLiveStatus({state:'ready',session_id:'different-grid'})
  await w.get('[aria-label="重新构场"]').trigger('click');await flushPromises()
  expect(badges()).toEqual(['暂无数据','暂无数据'])
})

it('地区右侧开启定时后立即查询并构场，按所选间隔更新，暂停保留手动重新构场', async () => {
  vi.useFakeTimers(); houses=true
  localStorage.setItem('tfield.monitoring-location.v1.test-user',JSON.stringify(testMonitoringLocation))
  const w=await open()
  await w.get('[aria-label="定时监测"]').trigger('click')
  await w.get('.timed-panel select').setValue('5')
  await w.get('.timed-action').trigger('click');await flushPromises()
  expect(requests.filter(p=>p==='POST /api/live/weather/query')).toHaveLength(1)
  expect(requests.filter(p=>p==='POST /api/live/weather/construct')).toHaveLength(1)
  expect(w.get('.api-state').text()).toContain('每 5 分钟')
  queriedWeather={...makeWeatherQuery(),query_id:'next-ticket',source_fingerprint:'next-weather',weather:{bg_temp:10.1,bg_rh:62,bg_light:35000}}
  await vi.advanceTimersByTimeAsync(300_000);await flushPromises()
  expect(requests.filter(p=>p==='POST /api/live/weather/query')).toHaveLength(2)
  expect(requests.filter(p=>p==='POST /api/live/weather/construct')).toHaveLength(2)
  expect(w.findAll('.weather-cell .value').map(n=>n.text())).toEqual(['10.1 °C','62.0 %','35,000'])
  await w.get('.timed-action').trigger('click');await vi.advanceTimersByTimeAsync(300_000)
  expect(requests.filter(p=>p==='POST /api/live/weather/query')).toHaveLength(2)
  await w.get('[aria-label="重新构场"]').trigger('click');await flushPromises()
  expect(requests.filter(p=>p==='POST /api/live/weather/query')).toHaveLength(3)
  expect(requests.filter(p=>p==='POST /api/live/weather/construct')).toHaveLength(3)
})

it('没有档案时保留完整大屏和禁用查询，不发构场请求或编造温度', async () => {
  const w = await open()
  expectPanels()
  expect(w.text()).toContain('尚未配置可用的棚体结构与气象模型')
  expect(w.get('.strip .cell .value').text()).toBe('暂无')
  expect(w.find('.volume-stub').exists()).toBe(false)
  expect(w.find('.chart-stub').exists()).toBe(false)
  expect([...document.querySelectorAll<HTMLInputElement>('#shell-side input')].every(input => input.disabled)).toBe(true)
  expect(requests.filter(request=>!request.includes('/api/user/alerts/settings'))).toEqual(['GET /api/user/greenhouses','GET /api/live/prototype','GET /api/live/status'])
  expect(w.find('button[data-act="prepare"]').exists()).toBe(false)
})
it('温室棚体位于定时下方，选中保存的方案后以其地点与尺寸构场',async()=>{
 vi.useFakeTimers();houses=true
 const point={...testMonitoringLocation,city_code:'220100',city_name:'长春市',latitude:43.82,longitude:125.32}
 const plan:DesignRecord={id:'my-greenhouse',revision:4,spec:newDesign()}
 Object.assign(plan.spec.location,point)
 Object.assign(plan.spec.structure,{length_m:8,width_m:3,arch_height_m:1.8})
 plan.spec.name='长春试验棚'
 plans=[plan]
 queriedWeather=makeWeatherQuery(point)
 const w=await open()
 const actions=w.get('.monitor-actions')
 expect(actions.findAll('button').map(n=>n.attributes('aria-label'))).toEqual(['定时监测','温室棚体'])
 await w.get('[aria-label="温室棚体"]').trigger('click');await flushPromises()
 const picker=w.getComponent(LiveGreenhouseDialog)
 await picker.get('select').setValue(plan.id)
 expect(picker.text()).toContain('长春试验棚 · v4')
 expect(picker.text()).toContain('吉林省 · 长春市')
 expect(picker.text()).toContain('8 × 3 × 1.8 m')
 await picker.get('form').trigger('submit');await flushPromises()
 expect(w.findComponent(LiveGreenhouseDialog).exists()).toBe(false)
 expect(w.get('.region-selector').text()).toBe('吉林省 · 长春市')
 const bodies=(path:string)=>vi.mocked(fetch).mock.calls.filter(([url])=>url===path).map(([,init])=>JSON.parse(String(init?.body)))
 expect(bodies('/api/user/greenhouse-designs/my-greenhouse/activate')).toEqual([{revision:4}])
 expect(bodies('/api/live/weather/query')).toEqual([{location:{province_code:'220000',city_code:'220100'},latitude:43.82,longitude:125.32,coordinate_system:'GCJ-02'}])
 const dims={length_m:8,width_m:3,height_m:1.8}
 const constructed=()=>bodies('/api/live/weather/construct')
 expect(constructed()).toEqual([{query_id:queriedWeather.query_id,dimensions:dims}])
 expect(w.find('.volume-stub').exists()).toBe(true)
 expect(JSON.parse(localStorage.getItem('tfield.house-dimensions.v1.test-user')!)).toEqual(dims)
 await w.get('[aria-label="重新构场"]').trigger('click');await flushPromises()
 await w.get('[aria-label="定时监测"]').trigger('click')
 await w.get('.timed-action').trigger('click');await flushPromises()
 expect(constructed()).toHaveLength(3)
 expect(constructed().every(b=>JSON.stringify(b.dimensions)===JSON.stringify(dims))).toBe(true)
 await w.get('[aria-label="温室棚体"]').trigger('click');await flushPromises()
 expect(w.getComponent(LiveGreenhouseDialog).text()).toContain('当前方案 长春试验棚 · v4')
})
it('重新打开保存的原型结果时恢复其尺寸，不重新查询或构场',async()=>{
 const dims={length_m:12,width_m:3,height_m:2},query=makeWeatherQuery()
 currentStatus=makeLiveStatus({state:'ready',session_id:'saved-sized',prototype:true,dimensions:dims,location:query.location,time:query.field_time,weather:query.weather,
  weather_source:{provider:'qweather',monitoring_mode:'single_shot',data_kind:'current',source_fingerprint:query.source_fingerprint,field_time:query.field_time,observed_at:query.observed_at,
   light_time:query.light_time!,fetched_at:query.fetched_at,requested_coordinates:query.requested_coordinates,query_coordinates:query.query_coordinates}})
 const w=await open();await vi.waitFor(()=>expect(w.find('.volume-stub').exists()).toBe(true))
 expect(JSON.parse(localStorage.getItem('tfield.house-dimensions.v1.test-user')!)).toEqual(dims)
 expect(requests.some(p=>p.startsWith('POST'))).toBe(false)
})

it('空方案有设计入口，缺地点的方案无法应用，服务器冲突保留原监测地点',async()=>{
 localStorage.setItem('tfield.monitoring-location.v1.test-user',JSON.stringify(testMonitoringLocation))
 const w=await open()
 const trigger=w.get('[aria-label="温室棚体"]')
 await trigger.trigger('click');await flushPromises()
 expect(w.getComponent(LiveGreenhouseDialog).get('a[href="/greenhouse-design"]').text()).toBe('前往温室设计')
 await w.getComponent(LiveGreenhouseDialog).get('button:not([type=submit])').trigger('click')
 const unlocated={id:'draft',revision:1,spec:newDesign()}
 const valid={id:'valid',revision:2,spec:newDesign()}
 Object.assign(valid.spec.location,testMonitoringLocation,{city_code:'220100',city_name:'长春市'})
 plans=[unlocated,valid];activationFails=true
 await trigger.trigger('click');await flushPromises()
 const picker=w.getComponent(LiveGreenhouseDialog)
 await picker.get('select').setValue('draft')
 expect(picker.text()).toContain('补全监测地点和经纬度')
 expect(picker.get('button[type=submit]').attributes('disabled')).toBeDefined()
 await picker.get('select').setValue('valid')
 await picker.get('form').trigger('submit');await flushPromises()
 expect(picker.get('[role="alert"]').text()).toContain('方案版本已改变')
 expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
 expect(requests).not.toContain('POST /api/live/weather/query')
})

it('设计页已应用的版本经同一配置路径构场',async()=>{
 houses=true
 const plan={id:'from-design',revision:2,spec:newDesign()}
 Object.assign(plan.spec.location,testMonitoringLocation)
 appliedPlan=plan
 const w=await open('/live?applyDesign=from-design&designRevision=2')
 expect(requests).toContain('GET /api/user/greenhouse-designs/active')
 expect(requests.filter(p=>p==='POST /api/live/weather/query')).toHaveLength(1)
 expect(requests.filter(p=>p==='POST /api/live/weather/construct')).toHaveLength(1)
 expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
})

it('已有可用档案但没有个人气象结果时保留模块并提示提交气象', async () => {
  houses = true
  const w = await open()
  expectPanels()
  expect(w.find('h2').exists()).toBe(false)
  expect(w.find('.empty-status').exists()).toBe(false)
  expect(w.findAll('[data-view]')).toHaveLength(0)
  expect(w.get('button[aria-label="选择监测地点"]').text()).toBe('选择省市地区')
  expect(w.find('a[href="/replay"]').exists()).toBe(false)
  expect(requests.some(url => /\/live\/(volume|frame)\//.test(url))).toBe(false)
})

it('地区选择按钮打开地点弹窗，不新增配置源模块', async () => {
  const w=await open()
  const prior=globalThis.fetch
  vi.stubGlobal('fetch',vi.fn(async (input:RequestInfo|URL,init?:RequestInit)=>String(input)==='/api/user/regions'
    ? new Response(JSON.stringify(testRegionCatalog)) : prior(input,init)))
  await w.get('.region-selector').trigger('click');await flushPromises()
  expect(w.getComponent({name:'MonitoringLocationDialog'}).props('open')).toBe(true)
  expect(document.querySelector('dialog[aria-label="选择监测地点"]')).not.toBeNull()
  expect(w.get('.weather-overview').text()).not.toContain('配置气象源')
})

it('确认地点自动查询并构场；模型未配置的错误可在配置后刷新恢复', async () => {
  const w=await open()
  const location={province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市',longitude:127,latitude:42,coordinate_system:'GCJ-02'}
  w.getComponent({name:'MonitoringLocationDialog'}).vm.$emit('confirm',location)
  await flushPromises()
  expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
  expect(w.find('.volume-stub').exists()).toBe(false)
  expect(requests.filter(path=>path==='POST /api/live/weather/query')).toHaveLength(1)
  expect(requests.filter(path=>path==='POST /api/live/weather/construct')).toHaveLength(1)
  expect(w.text()).toContain('自动构场失败')
  expect(requests.some(path=>path==='POST /api/live/weather')).toBe(false)
  houses=true
  await w.get('button[aria-label="重新构场"]').trigger('click')
  await flushPromises()
  await vi.waitFor(()=>expect(w.find('.volume-stub').exists()).toBe(true))
  expect(requests.some(path=>path.includes('/api/live/frame/0'))).toBe(true)
  expect(w.find('button[data-act="start"]').exists()).toBe(false)
  expect(w.find('a[href="/replay"]').exists()).toBe(false)
})

it('切换到其他地区后不把旧地点的温度和温度场冒充新地点',async()=>{
  currentStatus=makeLiveStatus({state:'ready',session_id:'old-region',location:{province_code:'220000',province_name:'吉林省',city_code:'220200',city_name:'吉林市'}})
  const w=await open();await vi.waitFor(()=>expect(w.find('.volume-stub').exists()).toBe(true))
  w.getComponent({name:'MonitoringLocationDialog'}).vm.$emit('confirm',{province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市',longitude:127,latitude:42,coordinate_system:'GCJ-02'})
  await flushPromises()
  expect(w.find('.volume-stub').exists()).toBe(false)
  expect(w.find('.chart-stub').exists()).toBe(false)
  expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
  expect(w.findAll('.weather-cell .value').map(n=>n.text())).toEqual(['9.6 °C','61.0 %','33,000'])
  expect(w.text()).toContain('自动构场失败')
  expect(requests.some(path=>path==='POST /api/live/weather/query')).toBe(true)
  expect(requests.some(path=>path==='POST /api/live/weather')).toBe(false)
})

it('状态读取失败时保留布局并显示连接错误，不声称档案未配置', async () => {
  statusFails = true
  const w = await open()
  expectPanels()
  expect(w.get('[role="alert"]').text()).toContain('服务暂时不可用')
  expect(w.text()).toContain('暂时无法读取构场状态')
  expect(w.text()).not.toContain('尚未配置可用')
})

it('档案读取失败也不阻止展示已保存的个人结果', async () => {
  catalogFails = true
  currentStatus = makeLiveStatus({ state: 'ready', session_id: 'saved-result' })
  const w = await open()
  await vi.waitFor(() => expect(w.find('.volume-stub').exists()).toBe(true))
  expect(w.find('[aria-label="棚体三维温度场占位"]').exists()).toBe(false)
  expect(w.text()).toContain('26.5 °C')
})

it('手动刷新后空态切换到真实场，结果消失时清除旧读数', async () => {
  const w = await open()
  houses = true
  currentStatus = makeLiveStatus({ state: 'ready', running: true, session_id: 'new-weather' })
  await w.get('button[aria-label="重新构场"]').trigger('click'); await flushPromises()
  await vi.waitFor(() => expect(w.find('.volume-stub').exists()).toBe(true))
  expect(w.find('[aria-label="棚体三维温度场占位"]').exists()).toBe(false)
  // 轮询发现结果不再可用时，不能继续显示上一份温度。
  currentStatus = makeLiveStatus({ state: 'idle', total: 0, cursor: 0 })
  await w.get('button[aria-label="重新构场"]').trigger('click'); await flushPromises()
  expectPanels()
  expect(w.get('.strip .cell .value').text()).toBe('暂无')
  expect(w.find('.chart-stub').exists()).toBe(false)
})

it('初始无档案时仍轮询状态，后台配置完成的新结果可以自动出现', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const w = await open()
  currentStatus = makeLiveStatus({ state: 'ready', session_id: 'published-later' })
  await vi.advanceTimersByTimeAsync(5000); await flushPromises()
  expect(w.find('.volume-stub').exists()).toBe(true)
  expect(requests.filter(url => url === 'GET /api/live/status')).toHaveLength(2)
})

it('气象条使用当前帧外部输入，未提供的湿度不以模型估计值代替', async () => {
  currentStatus = makeLiveStatus({state:'ready',session_id:'weather-current'})
  const base=makeLiveFramePayload()
  frameResponse=makeLiveFramePayload({frame:{...base.frame,bg_rh:92},live:{...base.live,session_id:'weather-current',weather:{bg_temp:22.5,bg_rh:null,bg_light:800},location:{province_code:'220000',province_name:'吉林省',city_code:'220600',city_name:'白山市',district_name:'抚松县'}}})
  const w=await open()
  expect(w.findAll('.weather-overview .value').map(cell=>cell.text())).toEqual(['22.5 °C','未提供','800'])
  expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
  expect(w.get('.weather-overview').text()).not.toContain('92')
  expect(w.get('.weather-overview').text()).not.toContain('棚内平均温度')
})

it('与当前会话不一致的旧帧不能填入气象条', async () => {
  currentStatus = makeLiveStatus({state:'ready',session_id:'new-weather'})
  frameResponse=makeLiveFramePayload({live:{...makeLiveFramePayload().live,session_id:'old-weather',weather:{bg_temp:35,bg_rh:90,bg_light:1200}}})
  const w=await open()
  expect(w.findAll('.weather-overview .value').map(cell=>cell.text())).toEqual(['暂无','暂无','暂无'])
})
it('重新打开页面恢复已保存单次结果，不自动重新查询或构场',async()=>{
 const query=makeWeatherQuery(),point={...query.location,...query.requested_coordinates}
 currentStatus=makeLiveStatus({state:'ready',session_id:'saved-single',location:query.location,time:query.field_time,weather:query.weather,
  weather_source:{provider:'qweather',data_kind:'current',monitoring_mode:'single_shot',source_fingerprint:query.source_fingerprint,
   field_time:query.field_time,observed_at:query.observed_at,light_time:query.light_time!,fetched_at:query.fetched_at,
   requested_coordinates:query.requested_coordinates,query_coordinates:query.query_coordinates}})
 const w=await open();await vi.waitFor(()=>expect(w.find('.volume-stub').exists()).toBe(true))
 expect(w.get('.region-selector').text()).toBe('吉林省 · 白山市')
 expect(w.findAll('.weather-cell .value').map(n=>n.text())).toEqual(['9.6 °C','61.0 %','33,000'])
 expect(requests.some(p=>p.startsWith('POST'))).toBe(false)
 expect(localStorage.getItem('tfield.monitoring-location.v1.test-user')).toContain(String(point.longitude))
})
