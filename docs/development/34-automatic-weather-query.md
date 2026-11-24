# 监测地点自动气象查询

更新：2026-11-09。

> 2026-11-10 已按“只做实时监测”调整：本文件保留第一版太阳预报查询实现说明，当前接口、时间窗口及缺失行为以 [近实时气象协议](36-near-realtime-weather.md) 为准，不再采用本文件原先允许未来两小时的规则。

## 当前行为

用户在地点弹窗中确认位置后，前端自动调用 `POST /api/live/weather/query`。已经保存监测地点的账号重新打开实时页面时也会查询。查询接口本身只读气象；前端随后通过独立接口自动构场，见 [自动构场](35-automatic-weather-field.md)。本文件记录查询和归一化协议。

页面可见且停留在实时监测页时，按返回的缓存到期时间自动更新。默认成功结果缓存 15 分钟；原有 5 秒状态轮询仍只读本地状态，不请求天气提供商。离页、标签页不可见和卸载时取消查询计时器；失败后等待用户刷新，不无限重试。

数据使用和风天气太阳辐射预报接口及 `extra=weather`，并非现场实测：

`GET /solarradiation/v1/forecast/{latitude}/{longitude}?hours=1&interval=15&extra=weather&localTime=true`

界面标注“和风天气 · 预报数据”，显示预报有效日期与时间。请求时间单独保存在 `fetched_at`，不冒充预报时刻。

## 请求与结果

```json
{
  "location":{"province_code":"220000","city_code":"220600","district_code":"220621"},
  "latitude":42.33,
  "longitude":127.28,
  "coordinate_system":"GCJ-02"
}
```

接口仅允许 USER/ADMIN 登录账号。行政区代码使用服务端 `RegionCatalog` 校验；当前只接受 GCJ-02，且使用吉林省周边外接矩形作坐标范围保护，不将此检查描述为精确的区县归属核验。浏览器地图依据实际行政区多边形进行点选。请求不接受模型 ID、凭据、服务地址、换算系数或用户自带气象数值。

结果包含：

- `provider=qweather`、`data_kind=forecast`；
- `location`、原选点 `requested_coordinates` 和实际查询的 `query_coordinates`；
- `forecast_time`、`fetched_at`、`expires_at`、`cached`；
- `query_id`：当前账号短期构场凭据；`source_fingerprint`：气象有效时刻、查询网格、输入值和换算方法的指纹；
- `weather`：`bg_temp` 为 ℃，`bg_rh` 为百分数，`bg_light` 为 lux；
- `weather_units`、`raw_weather`、`light_conversion`；
- 供应方追溯标记 `source_tag` 和 `attributions` 来源声明。

前端展示提供商署名及随数据返回的来源声明。声明按文字或 HTTP(S) 链接呈现，不执行供应方返回的 HTML。

## 归一化与时效

- 请求经纬度按接口约定四舍五入到两位小数，路径为纬度在前、经度在后。
- 选择距离获取时刻最近且位于“过去 15 分钟至未来 2 小时”范围内的预报；不依赖数组顺序。无合适时刻时返回明确错误。
- 温度必须提供 ℃ 单位；相对湿度严格按实际 v1 响应的 0～1 比例乘 100，超范围不猜测百分比口径。
- GHI 必须为 W/m²。通过共用 `WeatherLightNormalizer` 估算 lux，默认日光光效 110 lm/W，保留未实测标定的标记。
- 零值有效；缺少天气、未知单位、过时预报、非有限数值或转换溢出均返回错误，不用随机数、零值或别处的天气补齐。

`weather.bg_light` 已经是 lux，自动构场不能再按 W/m² 乘一次系数。构场沿用本次查询的地点坐标、有效时刻与来源信息。

大屏不会把新气象读数与旧温度场合称为同一结果。已保存场必须与当前选区、预报有效时刻、输入和来源指纹一致才能继续显示；否则保留正在构场或错误提示。

## 缓存和请求保护

成功结果默认按“保留两位小数的查询坐标”缓存 900 秒，不包含用户身份或地区标签。不同用户查询同一网格共用公开气象数据，但每次响应重新组装该请求的地区与原选点，避免缓存串用地点标签。

同网格并发请求合并为一次上游请求；缓存最多 256 个条目。错误默认缓存 60 秒，避免连续点击重复调用。每账号每分钟最多触发 6 次未命中请求，缓存命中不计入此限制。缓存为进程内状态，重启后清空，不宣称跨重启缓存。

请求有连接和读取超时，响应限制为 1 MB，支持 Gzip，不跟随重定向。不把密钥放入 URL，不向前端或错误详情返回密钥、原始上游异常或内部配置。

## 配置

凭据仅放在本机忽略目录中的 `.local/qweather.local.json`：

```json
{"api_host":"你的专属域名.qweatherapi.com","api_key":"你的 API KEY"}
```

统一启动脚本提供文件路径，配置变量包括：

| 变量 | 默认值 |
|---|---|
| `TFIELD_QWEATHER_CONFIG_FILE` | 项目 `.local/qweather.local.json` |
| `TFIELD_QWEATHER_CACHE_TTL_SECONDS` | 900 |
| `TFIELD_QWEATHER_FAILURE_TTL_SECONDS` | 60 |
| `TFIELD_QWEATHER_REQUESTS_PER_MINUTE` | 6 |
| `TFIELD_WEATHER_LIGHT_EFFICACY_LM_PER_W` | 110 |

仅接受专属 `*.qweatherapi.com` 域名，固定使用 HTTPS。没有配置时查询返回 503，核心系统仍可启动；已存在但格式无效的配置会阻止启动，避免静默使用错误凭据。修改凭据或配置后需重启业务服务。

## 验证记录

- 74 项后端测试通过；另有默认禁用的手动联网测试，需显式 `-Dtfield.qweather.live=true` 才运行，不在日常测试中消费请求。
- 手动联网测试在 2026-11-09 对抚松县做了一次真实请求，得到 22:00 预报：−8.12℃、62% 相对湿度、0 W/m² GHI；第二次相同查询使用同一进程缓存。
- 前端覆盖确认选点、旧回执防串、离页/不可见停止、缓存到期更新、失败等待重试、来源/预报/估算单位展示，以及旧场与新气象的时效匹配。
- 浏览器检查复用了上述真实响应，未产生额外收费请求，验证选点触发及 1440、1280、900 像素宽度展示。
- 记录位于本机 `.local/qweather-integration/`；测试不修改正式 MySQL，不新增数据库迁移，不读取或重置管理员密码。

## 接口依据

- https://dev.qweather.com/docs/api/solar-radiation/solar-radiation-forecast/
- https://dev.qweather.com/docs/resource/glossary/
- https://dev.qweather.com/docs/resource/metadata/
