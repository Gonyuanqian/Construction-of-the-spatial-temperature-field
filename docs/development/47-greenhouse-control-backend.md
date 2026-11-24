# 温室控制与 AgriSeek 控制计划后端

2026-11-22。按确认的参考图实现后端，前端页面保持原状。功能绑定**本账号的个人温室设计**，不混用管理员棚体模板库。所有设备均为模拟设备，返回 `mode=simulation`、`connection_status=simulated`；未接入真实阀门、风机或补光灯。

## 业务链路

1. 从既有个人温室列表选择已保存方案，使用指定修订号初始化控制配置。保存独立的设计快照；草稿修改不会悄悄改变设备布局。
2. 根据设计中的滴灌、喷灌开关建立对应控制单元，并创建通风、补光模拟单元。一个单元代表阀门/设备控制组，**不是每个喷头一个控制器**。允许手动新增控制单元、命名、分组、停用。全棚、A、B 目前只是虚拟分组，没有推导实际阀门布线或分区传感器。
3. 用户可手动启动/停止，或创建单次、每天执行的任务。所有启动必须有运行时长，服务端到时自动停止。补光可设亮度，风机可设低/中/高档。
4. AgriSeek 读取固定快照，生成分析概述、动作、依据与待核查条件。用户查看、修改、勾选后确认，才创建标注 `source=agriseek` 的单次任务。生成本身不操作设备，也不创建聊天记录。
5. 后台调度执行任务，将模拟状态变化及操作事件一起提交。操作记录可按软件异常筛选，支持任务过期、设备忙碌/停用导致跳过等情况；不是现场硬件告警。

设备返回 `running_seconds`、`total_runtime_seconds`、`today_runtime_seconds`。按 Asia/Shanghai 划分当天，跨日运行分段计时，延迟处理到时停止不会把超时等待算作模拟运行；没有伪造流量、电量或实测温度变化。

## 接口

统一前缀 `P=/api/user/greenhouse-designs/{designId}/control`。现有 Bearer 登录；USER 和 ADMIN 都只能读写本账号方案，跨账号返回 404。路径编号为 UUID。只接受文档字段，不能通过请求填写 owner、执行模式、任务来源或模型上下文。

| 方法 / 路径 | 行为 |
| --- | --- |
| POST `P/setup` | `{revision}`；初始化模拟控制，重复初始化同版本保留原设备 ID |
| GET `P` | 配置、绑定设计快照、几何布局、分组、设备状态/能力与 `design_stale` |
| POST `P/devices` | `{request_key,kind,name,zone_key}`；新增控制单元，最多 32 个 |
| PUT `P/devices/{id}` | `{request_key,revision,name,zone_key,enabled}`；更新设备；停止本单元并暂停旧任务 |
| POST `P/devices/{id}/commands` | `{request_key,revision,action,parameters}`；start/stop；启动核对设备版本 |
| POST `P/stop-all` | `{request_key}`；停止全部并暂停全部任务、暂停控制 |
| POST `P/resume` | `{request_key}`；恢复控制，**不会重新启用旧任务** |
| POST `P/rebind` | `{request_key,revision}`；显式绑定新设计版本，设备保留，控制和旧任务暂停 |
| GET / POST `P/tasks` | 列表 / 新建任务，最多 200 条未删除任务 |
| PUT `P/tasks/{id}` | `{request_key,revision,name,enabled,spec}`；编辑或启停任务 |
| POST `P/tasks/{id}/delete` | `{request_key,revision}`；软删除，保留事件 |
| GET `P/events?limit=30&offset=0&alarms=false` | 操作事件；alarms=true 只显示 expired/skipped/failed |
| GET `P/capabilities` | 检查计算端 `control_plan_version=1` 并返回 AgriSeek 能力 |
| POST `P/plans` | `{request_key,stage,horizon_minutes,prototype_frame_id?}`；排队生成 |
| GET `P/plans` / `P/plans/{id}` | 最近 30 份 / 具体计划、冻结快照、结果、状态 |
| PUT `P/plans/{id}` | `{revision,result}`；保存编辑后的草案，可删除动作、调整参数，不添加未知动作编号 |
| POST `P/plans/{id}/confirm` | `{revision,action_ids:[UUID...]}`；原子创建所选任务，同选择重复确认不重复创建 |
| POST `P/plans/{id}/cancel` | 取消待生成/草案；生成中的迟到结果丢弃；已确认计划在任务中停用 |

`request_key` 必须为 UUID。设备操作与任务变更在同棚操作事件中去重，同编号异内容/不同目标返回 409；计划生成在同棚计划表独立去重。版本冲突为 409，非法输入为 422。读取接口不会偷偷提交生成或设备动作。

### 启动与定时任务请求示例

以下数值仅演示接口，不是人参设备处方。`kind` 为 `drip/sprinkler/ventilation/lighting`，`zone_key` 为 `all/a/b`。

```json
{
  "request_key": "00000000-0000-4000-8000-000000000001",
  "revision": 1,
  "action": "start",
  "parameters": {"duration_seconds": 600, "brightness_percent": 40}
}
```

滴灌/喷灌允许 1–1800 秒；通风/补光允许 1–21600 秒。这些是原型请求上限，不代表适宜运行时长。补光必须有 1–100 的 `brightness_percent`；风机必须有 `speed=low/medium/high`。其他设备不能填这两类字段。

```json
{
  "request_key": "00000000-0000-4000-8000-000000000002",
  "name": "早间滴灌",
  "device_id": "00000000-0000-4000-8000-000000000003",
  "spec": {
    "parameters": {"duration_seconds": 600},
    "schedule": {"kind": "daily", "time": "07:00", "timezone": "Asia/Shanghai"}
  }
}
```

单次使用 `schedule={"kind":"once","at":"2026-11-23T07:00:00+08:00"}`。必须包含时区且在未来 31 天内。任务列表支持 ready/running/completed/paused/stopped/expired/skipped；每天任务执行后重新进入 ready，实际运行状态由对应设备及事件显示。停用/删除正在运行的任务会停止由**该任务**启动的设备，不停止之后被人工另行启动的运行。

## AgriSeek 输入、结果及状态

`stage` 为至多 80 字的用户阶段说明；`horizon_minutes` 为 15–1440。生成无需气象数据也可给条件性分析，不能编造已观察到的温差或缺光。有监测数据时，前端显式传入已有 `prototype_frame_id`，服务端核对拥有者、保存时间（不超过一小时）、小拱棚尺寸及请求地点坐标。**不自动取账号最近一次可能属于另一地点的监测结果**。

快照包含保存结构/种植参数、设备能力与状态、数据来源和原始时间、棚内估温的 mean/vmin/vmax。只传白名单气象元信息与温度摘要；不把个人方案名称、地理坐标或完整天气来源对象发送模型。当前没有土壤水分、冠层实测光照和设备响应模型，不能推断某个虚拟分区已过热，也不能承诺降温量或节水率。暂不由 AI 安排滴灌/喷灌，人工设备控制和既有灌溉任务保留。

独立的内部接口 `POST /internal/v1/assistant/control-plans` 要求内部凭据和用户上下文。复用已有 AgriSeek 模型配置，最多两次有界模型请求：结构化生成 → 独立复核。没有工具循环、联网搜索或普通聊天记录。Python 验证设备 ID、启用/运行状态、动作参数、时间范围；Java 再次验证并分配动作 ID。没有用静态模板冒充生成成功。模型未配置、连接失败、格式非法或复核不通过，会保留真实失败状态，不创建任务。

计划生命周期：`queued → generating → draft → confirmed`，另有 `failed/cancelled`。POST 立即返回 queued，前端轮询 GET；离页或刷新后从数据库恢复，不重新提交。生成任务有 180 秒租约，服务中断后过期任务记为 failed，**不自动重试收费请求**；用户可以用新请求编号重试。取消生成时不强行中断已发出的 HTTP，但不会采纳其迟到返回。

结果为 `{summary,actions,notes}`，每项动作包含 `{id,device_id,parameters,start_after_minutes,reason}`。`start_after_minutes` 从用户确认时间计算。计划两小时后不能确认；设备、任务或控制配置变化、设计修订号变化、停止全部后均使旧快照失效，需重新生成。确认时再次检查设备，原子创建所选任务，并保存确认选择及任务 ID；重复同选择可取回结果，改变选择返回 409。

## 持久化与运行

Flyway V11 增加五张业务表：`greenhouse_control`、`greenhouse_control_device`、`greenhouse_control_task`、`greenhouse_control_event`、`greenhouse_control_plan`。不更改旧账号、模型、设计及气象记录。后端初次改造时仅验证代码与隔离数据库；后续前端接入已同步切换本机前后端并完成 V11 迁移，详见 [前端部署记录](48-greenhouse-control-frontend.md)。

Spring 调度默认每秒检查设备/任务，每三秒处理一份 AI 请求。沿用现有至少两线程的调度池，避免模型请求占住到时停止任务。网络推理期间不持有数据库事务。控制变更及调度按棚行锁串行化；多个实例不能同时派发同一任务。任务开始、设备模拟状态、下次时间与审计记录同事务提交。

关闭网页不影响任务；服务本身关闭时不能执行。重启后处理已到期停止，错过超过 120 秒的启动不补执行；每天任务跳到下一天，防止积压灌溉集中执行。设备忙碌或停用则跳过并记录。账号停用、设计版本变更时自动停止并暂停本棚任务。

前端下一步可直接按参考图对接：顶部选本人方案和初始化；左右设备布局/控制卡；AgriSeek 面板读取可用数据、草案与确认；底部任务及事件标签。不要把模拟成功显示为真实设备回执，不要在现有温度场中伪造开风机后的降温。真实设备接入后仍需独立网关、回执、离线状态、幂等命令和现场失联停机策略。

## 验证

Java 使用实际 V9/V8/V11 SQL 创建隔离 H2 数据库，覆盖账号隔离、状态与任务持久化、请求幂等、并发创建/调度、自动停止、跨日累计时长、停止全部、版本绑定、时区、错过时间窗口、AI 草案/编辑/确认/取消/失败/中断恢复、监测地点/尺寸/拥有者核对。HTTP 权限测试覆盖普通用户入口及匿名拒绝。

Python 使用模拟模型响应验证结构化动作、独立复核、边界、不合适动作拒绝、空草案、内部凭据/拥有者、无配置与失败不泄漏、无聊天记录。测试不调用真实天气/模型，不操作正式数据库或硬件。功能测试通过不代表真实农事参数或设备效果已验证。

本轮验证通过：41 项 Java 回归（其中新增控制相关 25 项）、47 项 Python 回归；Java 编译通过，Python 语法检查通过。SQL 在上述隔离 H2 测试中实际执行，没有在正式 MySQL 上试运行。前端未改动，不将设计效果图作为浏览器验收结果。
