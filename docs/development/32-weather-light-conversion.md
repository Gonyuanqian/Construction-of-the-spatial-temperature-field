# 气象接入层光照换算

更新：2026-11-08。原采集单位由用户确认为照度 lux / lx。原工作簿中保留“原始设备单位”的说明，本次不改写源数据或重新训练模型。

## 统一入口

`POST /api/live/weather`、`POST /api/user/weather` 和携带气象请求体的 `/api/live/prepare`、`/api/live/sessions` 都经过 Java `WeatherService.submit`。

`WeatherLightNormalizer` 在此处将当前输入统一为训练所用的 lux。G 的当前/历史特征和 F 构场使用同一尺度；Python 不再重复换算。历史数据库中的 `bg_light` 已经是 lux，只读入历史链，不重新经过换算器。

```text
外部光照值 + 明确的单位
        ↓ Java 接入层
        lux + 原始值/单位/换算方法/系数
        ↓
        G 预测虚拟测点 → F 构场 → 保存结果
```

本次实现统一输入换算，不包含自动请求和风天气、定时任务或前端页面改动。单次接口验证文件仍在本机 `.local/qweather-probe/`，认证信息不进入前端或版本库。

## 输入协议

原请求继续有效：省略 `bg_light_unit` 时，`bg_light` 按 lux 处理，保持原数值。手动输入和演示 CSV 使用此约定。也可以显式传 `lux` 或 `lx`。

太阳总水平面辐照度输入必须显式传 `W/m²` 或 `W/m2`，例如：

```json
{
  "greenhouse_id":"已启用棚体配置的 UUID",
  "location":{"province_code":"220000","city_code":"220600"},
  "timestamp":"2026-11-08T12:00:00+08:00",
  "bg_temp":25.0,
  "bg_rh":60.0,
  "bg_light":500.0,
  "bg_light_unit":"W/m²"
}
```

单位名称忽略首尾空格及大小写。明确传 null、未知单位、负值、非有限值及乘法溢出均返回 422，不根据数值大小猜测单位，也不接受请求方提供换算系数或伪造的 `light_conversion`。

单位为 `W/m²` 的值在此协议中表示估算室外水平日光照度的 GHI；不能把 DNI、DHI、倾斜面辐照度或电功率冒充 GHI 输入。后续天气提供商适配器应从和风天气 `ghi.value` / `ghi.unit` 取值，先校验单位再调用此入口。

原湿度协议仍为 0～100%。提供商适配器应将和风天气实际返回的 0～1 湿度转为百分数，不能直接把 `0.59` 作为 `0.59%` 提交。

## 系数与适用范围

当前方法 `daylight_constant_v1`：

`照度 lux = GHI W/m² × 日光光效 lm/W`

服务端配置：`TFIELD_WEATHER_LIGHT_EFFICACY_LM_PER_W=110`，对应 Spring 配置 `tfield.weather.light-efficacy-lm-per-w`。默认 110，仅为日光演示基线，要求系数是大于 0 的有限数值。无效配置阻止服务启动，不静默回退。

这不是通用固定单位换算。光谱、云况、太阳高度、受光面和遮挡都会影响关系。110 的参考来自日光实测比较研究，尚未通过本项目采集环境校准。若原照度传感器位于棚膜或遮阳网下，还需处理透射与遮挡。正式使用应比较成对数据上的标定方法与 Perez 等日光光效模型，独立验证转换及后续温度场误差。

- CIE 光谱加权定义：https://cie.co.at/eilvterm/17-21-060
- 日光光效比较研究：https://doi.org/10.1016/S0960-1481(99)00115-9

## 保存与读取

`weather_frame.bg_light` 保存归一后的 lux。换算记录保存在现有 `summary_json.light_conversion` 中，不增加数据库列或执行结构迁移。气象帧返回 `bg_light_unit: "lux"`，以及顶层 `light_conversion`，例如：

```json
{
  "source_value":500.0,
  "source_unit":"W/m²",
  "target_value":55000.0,
  "target_unit":"lux",
  "method":"daylight_constant_v1",
  "factor":110.0,
  "estimated":true,
  "efficacy_lm_per_w":110.0,
  "assumption":"outdoor_horizontal_daylight",
  "calibrated":false
}
```

直接输入 lux 的方法为 `identity`、系数为 1、`estimated=false`。旧结果缺少换算记录时返回 null，不补造历史系数。实时状态、网格附带的 `live` 视图提供同一份换算记录及 `weather_units`，原有 `weather` 三项数值结构保留。

重试与历史规则：

- 原 lux 请求保留原有摘要算法，省略单位与显式 lux/lx 可以重试同一结果。
- 辐照请求按原始值及规范单位识别，`W/m²` 与 `W/m2` 等价。服务器系数变化后，重试旧输入仍返回原记录与原系数，新时刻采用新系数。
- 同时刻将辐照请求改成 lux，即使转换结果数值相同，也返回 409，避免静默替换原始来源。
- 读取状态、历史或网格不会执行新的换算、气象请求或模型推断。

## 验证

Java 全部 63 项测试通过。新增覆盖 500 W/m² → 55000 lux、零值、lux 原值、非法单位/数值及溢出、可配置系数、推断入参、连续帧不重复换算、记录持久化、旧 lux 重试、系数调整后的旧结果恢复及实时视图一致性。持久化测试使用隔离 H2，不修改本机正式 MySQL。
