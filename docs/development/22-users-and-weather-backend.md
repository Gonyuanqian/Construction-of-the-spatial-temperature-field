# 账号、棚体档案与外部气象构场后端

更新：2026-11-04；Java 业务版本 0.6.0，现已采用 V6 共享地区档案。当前匹配接口和兼容规则以 [地区档案契约](24-greenhouse-archive-matching.md) 为准。

## 交付范围与使用边界

这次完成后端业务：账号登录、管理员/用户权限、账号管理、地区棚体档案、气象模型发布与绑定、外部气象构场和结果持久化。前端登录、用户管理、角色导航和用户工作台现已接入，见 [前端交接](23-login-role-navigation-and-users.md)。经用户授权，本机已完成备份、V5、首次管理员初始化和正式切换，见 [切换记录](../reports/auth-rollout-20261104.md)；本轮尚未提交 GitHub。

系统仍是 B/S：浏览器访问 Java，Java 管业务和权限，Python 管模型计算。训练是管理员使用的业务功能，并不等同于另一种 C/S 架构。旧训练、模型库和文件回放工作区继续供管理员使用，仍只有一个 `default` 工作区。普通用户使用新棚体接口，不读写这个全局实时会话。多个管理员的独立训练空间、分布式任务队列不在本次范围内。

## 权限与账号

| 身份 | 允许的业务 |
| --- | --- |
| 未登录 | 登录、基础健康检查；不能读写业务数据 |
| USER | 自己的账号和密码、共享地区档案、本账号的气象与构场历史 |
| ADMIN | 用户管理、棚体档案、气象模型发布绑定、原训练和模型库、运维信息 |

权限由 Spring Security 在后端检查。普通用户即使直接请求旧训练、模型库或管理接口，也会收到 403。共享档案无需逐个用户授权；其他账号的构场结果统一返回 404。管理员可以管理全部棚体档案。

账号由管理员创建，不开放公共注册。账号名称为 3–64 位英文字母、数字、`_.-`，统一转为小写；角色为 `ADMIN` 或 `USER`。密码至少 8 个字符，UTF-8 不超过 72 字节，使用 BCrypt（cost=12）保存。不能禁用或降级最后一个启用的管理员。停用账号保留历史关联，不提供物理删除。

登录返回随机 256 bit 的 Bearer 会话令牌，数据库只保存 SHA-256 摘要。令牌默认有效 12 小时，可以通过 Spring 属性 `tfield.security.token-seconds` 配置为 60–604800 秒。退出、改密、管理员重置密码、角色或启用状态调整都会撤销相应会话；服务重启不会丢失尚未过期的会话。不使用 Cookie 身份认证。

首次启动空账号库，必须给 Java 配置 `TFIELD_BOOTSTRAP_ADMIN_USERNAME`、`TFIELD_BOOTSTRAP_ADMIN_PASSWORD`；没有预置账号或默认管理员密码。只在账号表为空时创建初始管理员，之后这两个变量不会覆盖已有账号。可通过未跟踪的 `.local/system.local.json` 的 `Environment` 配置。部署使用 HTTPS，并在入口代理配置登录限速；本次没有实现短信、找回密码、登录验证码或多因素认证。

2026-11-05：实时监测 `/api/live/**` 已统一复用本气象构场服务；原文件回放移至管理员 `/api/replay/**`。前端本轮未改，详见 [实时气象后端](25-live-weather-backend.md)。

## 接口约定

以下路径由 Java 提供。除登录、健康检查外，请求携带 `Authorization: Bearer <access_token>`。`Content-Type: application/json`，错误结构为 `{"detail":"原因"}`。常见状态：401 未登录/令牌失效，403 身份不允许，404 资源不存在或无权访问，409 状态冲突，422 参数无效。

### 登录与账号管理

| 方法、路径 | 请求/返回 |
| --- | --- |
| `POST /api/auth/login` | `{username,password}` → `{access_token,token_type,expires_at,user}` |
| `GET /api/auth/me` | 当前账号，不返回密码或摘要 |
| `POST /api/auth/logout` | 撤销当前会话 |
| `POST /api/auth/password` | `{current_password,new_password}`；成功后重新登录 |
| `GET /api/admin/users?limit=20&offset=0` | `{items,total}`；limit 1–100 |
| `POST /api/admin/users` | `{username,display_name,password,role}` |
| `GET /api/admin/users/{id}` | 账号详情 |
| `PATCH /api/admin/users/{id}` | 完整提交 `{display_name,role,enabled}`；撤销该账号已有会话 |
| `POST /api/admin/users/{id}/password` | `{password}`；重置密码并撤销会话 |

前端建议集中处理 Authorization 和 401，重新登录后再发起新请求；不要将会话令牌放在 URL、日志、Git 或共享文件中。前端令牌存储与账号切换清理已实现，见前端交接。

### 管理员：模型与棚体档案

| 方法、路径 | 说明 |
| --- | --- |
| `GET/POST /api/admin/weather-models` | 列表 / 登记 `{name,package_id}`，初始为 DRAFT |
| `GET /api/admin/weather-models/{id}` | 登记详情和不可变包元数据 |
| `PATCH /api/admin/weather-models/{id}` | `{status:"PUBLISHED"}` 发布，或 `DISABLED` 停用 |
| `GET/POST /api/admin/greenhouses` | 列表 / 创建地区、尺寸等字段，见 [档案契约](24-greenhouse-archive-matching.md) |
| `GET/PATCH /api/admin/greenhouses/{id}` | 详情 / 完整修改地区、尺寸、启用状态等字段 |
| `PUT /api/admin/greenhouses/{id}/weather-model` | `{weather_model_id}`，只能绑定已发布版本 |

`weather_model_id` 是气象部署记录 UUID，`package_id` 是服务器本地包 UUID，`model_id` 是原模型库的第二阶段模型数字 ID，三者用途不同。发布时校验包所有文件摘要，并校验包内第二阶段成品与模型库 artifact 的 SHA-256 一致。包不能通过 HTTP 上传，也不能由普通用户指定文件路径、模型编号或工作区上下文。

当前仅支持 `ginseng_arch_v1` 固定几何和原 24 点布局，默认拱跨宽 2.1 m、拱顶高 1.3017 m，源平面 y=3/9/15 m；显示范围 y=0–18 m。更换传感器布局、棚型或形体缩放需要另行验证并定义新模板，接口暂不提供缩放参数。

### 用户：气象与温度场

| 方法、路径 | 说明 |
| --- | --- |
| `GET /api/user/greenhouses` | 返回共享且启用、有地区信息的档案 |
| `GET /api/user/greenhouses/{id}` | 棚体、绑定模型状态及输入方案 |
| `POST /api/user/weather` | 提交外部气象，完成构场并保存结果摘要 |
| `GET /api/user/greenhouses/{id}/frames?limit=20&offset=0` | 按时间倒序的历史；limit 1–200 |
| `GET /api/user/greenhouses/{id}/frames/{frameId}/field` | 获取原先保存的 `{summary,field}`，不重新构场 |

输入示例：

```json
{
  "location": {"province_code":"220000","city_code":"220600"},
  "timestamp": "2026-11-04T12:00:00+08:00",
  "bg_temp": 25.0,
  "bg_light": 1000.0
}
```

`timestamp` 必须带时区；Java 转 UTC 保存，Python 转 Asia/Shanghai 构造训练时使用的时间特征。背景温度单位为 ℃，湿度为 0–100%。`bg_light` 必须与训练数据使用相同物理量、单位和尺度，不能把天气服务的太阳辐射值直接当成训练光照值。本次没有接入天气预报服务或实施单位换算。

两输入方案 `two` 不需要 `bg_rh`，模型额外预测第二阶段所需的背景湿度；`full` 方案必须提供 `bg_rh`。只接受地区、时间与外部气象，提交棚内 24 点或模型 ID 等额外字段会被拒绝。光照必须非负，所有数值必须有限。同一账号、棚体、气象地区、时刻和输入返回原结果；该时刻不同输入返回 409；新帧必须晚于最后一帧。不可回填旧帧，避免默默改变历史预测。

返回记录包含 `id`、`greenhouse_id`、`weather_model_id`、`observed_at`、气象输入、位置、档案配置快照和 `summary`。摘要包含 `mean/vmin/vmax`、24 个 `node_temperatures`、模型版本摘要、`stage1_mode`、`humidity_source`、训练范围提示等。完整 `field` 复用既有体积渲染字段，默认 37 个 y 平面、standard 网格、启用原有物理约束。所有平面的 `measured` 均为 false；原源平面单独标 `virtual_source`。界面必须持续显示这是气象推算，而非现场实测。

## 计算流程和模型包

1. 用户提交地区代码，Java 先匹配区县档案，再按明确规则回退到全市默认档案，读取绑定的已发布模型。
2. 只取本账号、该棚体、该气象地区、该模型及同一配置快照最近 12 条已保存的外部气象，加上本帧。13 帧连续且间隔均为 5 分钟时使用历史 G；首次、断档或换模型后历史不足，使用单时刻 G。
3. G 输出 24 个虚拟温度；两输入方案同时估计背景湿度。当前实现使用先前实验经 B 时段选定的 G，模型类别不限定为 XGBoost。
4. 将本帧预测值装成独立内存 Dataset，恢复包内已训练的 F，重新计算虚拟测点残差，再执行 IDW、断面混合及原物理约束。绝不重新拟合 F，也不读取真实棚内温度作为在线输入。
5. Python 保存结果文件，Java 校验棚体 revision 和模型状态后在事务内登记本帧。计算期间地区匹配、档案配置或本流数据变化会拒绝写入，用户可重试。各账号与地区不共享输入历史。

模型包由可信管理员在服务器本地生成：

```powershell
# 在 backend 目录；路径使用本机实际位置。
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python scripts/package_weather_model.py `
  --current <已训练的单时刻G.pkl> `
  --history <已训练的一小时G.pkl> `
  --artifact <原模型库F的成品.bin> `
  --model-id 3 --schema two
```

也可加 `--bounds <bounds.json>`，例如 `{"bg_temp":[训练最小值,训练最大值],"bg_light":[训练最小值,训练最大值]}`；范围必须来自训练数据。超范围会在结果标注，范围提示不能替代泛化验证。生成新的 UUID 目录和 manifest，包含两个 G、一个冻结 F、SHA-256、固定几何、输入方案和时区。不同输入方案分开打包。可信本地 pickle 与服务运行环境版本应一同保存，不能加载来历不明的 pickle。

本机可用的实验成品位于 `outputs/model-evaluation-weather-chain-20261104/models`：`two_current_00.pkl` / `two_history_00.pkl` 与 `full_current_00.pkl` / `full_history_00.pkl`；冻结 F 位于该归档 `inputs/saved.artifact.bin`，对应模型库 ID 3。部署到其他数据库时，应先确认其 ID 和原始成品一致，不要仅按名称猜测。

## 存储、部署与恢复

Flyway V6 将棚体改为共享地区档案，按账号和地区隔离帧，新增位置与配置快照；旧成员表仅保留数据。具体匹配规则和迁移见 [地区档案契约](24-greenhouse-archive-matching.md)。V5 原先新增 `app_user`、`auth_session`、`user_admin_lock`、`weather_model`、`greenhouse`、`greenhouse_member`、`weather_frame`，保留已有数据集、训练任务和模型数据。

| 配置 | 用途 |
| --- | --- |
| `TFIELD_BOOTSTRAP_ADMIN_USERNAME/PASSWORD` | 首次建立管理员，只交给 Java |
| `TFIELD_WEATHER_MODEL_ROOT` | Python 本地只读发布包目录，默认 `backend/configs/weather-models` |
| `TFIELD_WEATHER_RESULT_ROOT` | Python 结果文件目录，默认 `backend/configs/weather-results` |
| `TFIELD_INTERNAL_TOKEN` 或 `TFIELD_INTERNAL_TOKEN_FILE` | Java/Python 之间共用的内部凭据 |
| `TFIELD_MODEL_STORE_MODE=java` | 默认业务形态；Python 旧 `/api/**` 也要求内部凭据，健康接口除外 |

`scripts/system.ps1` 将气象模型和结果根目录固定在项目数据区，避免随 release 切换而丢失。手动或异机部署务必设置绝对路径。MySQL 与两个数据目录均须持久化和备份。数据库有记录但结果文件缺失时明确报 404，不重新计算成另一个版本。

只对外发布 Java 和静态前端。Python 及 MySQL 保持内网可达，Java/Python 的内部凭据不得下发浏览器。`legacy` 模式仅用于原单后端开发与历史测试，没有新账号隔离，不用于用户部署。

本机正式演示已切换 0.6.0。其他环境升级时仍需统一发布前后端，旧无登录前端不能直接使用受保护业务；先备份数据库并配置初始管理员，已有账号时无需再提供初始化凭据。V5 不支持通过直接删除新表来回退用户业务。

## 验证与后续交接

本轮 V6 棚体档案改造通过 Java 17 项、前端相关 26 项和隔离全链路 103 项检查，见 [本轮验收](../reports/greenhouse-archives-20261104.md)。以下为 V5 历史验收：已执行 Java 账号/权限测试 11 项、Python 新链路和相关回归 37 项，并使用独立 MySQL 库、独立端口及真实 G/F 成品完成 69 项 HTTP 联调：用户隔离、管理员旧几何和模型接口兼容、模型草稿/发布/禁用、授权撤销、两种输入构场、冷启动和历史切换、保存读取、幂等、密码重置和会话失效等。记录见 [后端验收记录](../reports/backend-users-weather-20261104.md)。这些检查证明业务链路与权限行为，不是新增泛化精度结论。

可复现联调入口 `backend/scripts/verify_users_weather.py --evaluation-root <归档目录> --java <java.exe> --jar <0.6.0.jar>`，从仓库根运行且设置 `PYTHONPATH=backend/src`。脚本总是新建 `tfield_users_test_<随机值>` 数据库、选择临时端口，使用随机测试账号密码，退出时仅停止自己创建的子进程；报告和模型保留在 `.local/backend-users-test-*`，测试库也保留供检查。脚本不读取或修改生产模型库。

前端统一登录、401 处理、用户/棚体档案和用户气象工作台已经接入；模型包登记发布仍由服务端管理。后续可根据用户反馈补模型发布界面、气象批量导入、天气接口适配、结果保留策略、运维审计与登录防护增强；这些扩展不改变“Java 授权、Python 计算、用户结果按账号、棚体和气象地区隔离”的边界。
