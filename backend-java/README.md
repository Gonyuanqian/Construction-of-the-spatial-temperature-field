# Java 业务服务

当前迁移阶段：**统一部署与核心流程联调**，业务服务版本 0.5.0。Java 统一提供前端页面及业务接口，Python 执行训练与计算。已在独立库完成真实训练、保存、取消、实时恢复、自动播放、回退和浏览器联调；服务器运维及压力验收仍需结合环境安排。

推荐从仓库根目录使用 `scripts/system.ps1 Build / Start / Stop / Restart / Status`。部署模式访问 8080，开发模式使用 `Start -Mode Dev` 访问 5173。发布包、配置、日志与回退见 [统一部署交接](../docs/development/05-deployment-and-acceptance.md)，实际范围见 [联调记录](../docs/development/06-migration-acceptance-20261019.md)。下文保留手动开发方式。

## 环境

- Java 17 及以上。
- Spring Boot 3.5.16。
- Maven 3.9.16，通过项目 Maven Wrapper 使用，首次运行需联网下载。
- 原 Python 服务运行在 `http://127.0.0.1:8503`。
- MySQL 8，由 Java 连接；双方共用数据文件存储和内部凭据。

版本在 `pom.xml` 和 `.mvn/wrapper/maven-wrapper.properties` 固定。Java 侧使用 Spring MVC 和 `RestClient`；Python 算法继续复用 `backend/src/tfield/`。

## 构建和启动

在仓库根目录启动原 Python 服务：

```powershell
cd backend
python -m uvicorn api.main:app --host 127.0.0.1 --port 8503
```

另开终端，在仓库根目录构建并启动 Java：

```powershell
cd backend-java
.\mvnw.cmd '-Dmaven.test.skip=true' package
java -Dfile.encoding=UTF-8 -jar target/tfield-business-0.5.0.jar
```

前端在第三个终端运行：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

访问 [前端](http://127.0.0.1:5173/data)。Java 当前提供接口，前端静态页面仍由 Vite 开发服务或原有静态托管方式提供。

## 配置

| 环境变量 | 默认值 | 用途 |
| --- | --- | --- |
| `TFIELD_JAVA_HOST` | `127.0.0.1` | Java 监听地址 |
| `TFIELD_JAVA_PORT` | `8080` | Java 监听端口 |
| `TFIELD_PYTHON_URL` | `http://127.0.0.1:8503` | Python 服务根地址 |
| `TFIELD_PYTHON_CONNECT_TIMEOUT` | `3s` | 建立连接的超时 |
| `TFIELD_PYTHON_READ_TIMEOUT` | `120s` | 普通调用的超时 |
| `TFIELD_PYTHON_COMPUTE_TIMEOUT` | `600s` | 构场、诊断、准备管线等调用的超时 |
| `TFIELD_MAX_REQUEST_BYTES` | `33554432` | 请求体大小上限，默认 32 MiB |
| `TFIELD_API_TARGET` | `http://127.0.0.1:8080` | 前端开发代理目标，在前端终端或 `.env.local` 设置 |

Java 启动环境设置 `TFIELD_MYSQL_HOST`、`TFIELD_MYSQL_PORT`、`TFIELD_MYSQL_DB`、`TFIELD_MYSQL_USER`、`TFIELD_MYSQL_PASSWORD`。默认主机为 `127.0.0.1:3306`，数据库为 `tfield_models`；仓库保留原有本机演示连接默认值。Java 也支持通过 `TFIELD_JDBC_URL` 指定完整 JDBC URL。Python 默认经 Java 读取模型，不直接写数据库。

Flyway V1 创建数据集与工作区表；V2 创建训练任务表、扩展模型和结果引用；V3 明确幂等键区分大小写；V4 创建实时会话与操作表、工作区会话引用。模型 ID、JSON 与成品原样保留，缺少 artifact 列的老表会补列。`model` 与新增业务表现在仅由 Java 写入。

| 双方共用的配置 | 默认行为 |
| --- | --- |
| `TFIELD_DATASET_STORAGE_ROOT` | 项目内 `backend/configs/datasets`；覆盖时必须为绝对路径 |
| `TFIELD_INTERNAL_TOKEN` | 可设置相同的内部调用凭据；不要写入 Git |
| `TFIELD_INTERNAL_TOKEN_FILE` | 未设置凭据时读取该绝对路径；默认项目 `.local/service-token`，由 Java 首次启动随机生成 |

本机从仓库根目录或 `backend-java` 启动时可自动定位项目。脱离源码目录部署时明确设置存储根与凭据文件；分机部署需将同一数据卷映射到双方配置的根目录，凭据也需一致。Python 动态读取默认凭据文件，因此可以先启动 Python。

| Python 专用配置 | 默认值 |
| --- | --- |
| `TFIELD_BUSINESS_URL` | `http://127.0.0.1:8080`，用于读取模型记录与原始产物 |
| `TFIELD_MODEL_STORE_MODE` | `java`；旧模式回退才使用 `legacy` |
| `TFIELD_TRAINING_ROOT` | 项目 `backend/configs/training-jobs`；覆盖时使用绝对路径 |
| `TFIELD_LIVE_SESSION_ROOT` | 项目 `backend/configs/live-sessions`；覆盖时使用绝对路径 |

## 数据集与工作区

- `POST /api/dataset/upload?name=...` 保留原始文件体与旧响应字段。每次成功上传产生独立 UUID 版本，不覆盖同名旧文件；验证通过后在一个事务内登记并切换工作区。
- `GET /api/datasets?limit=100` 查询登记版本，`GET /api/workspaces/default` 查询当前选择。
- `POST /api/workspaces/default/dataset` 接受 `{"dataset_id":"UUID"}`，校验文件后切回已有版本。暂未增加前端版本选择界面。
- 首次启动且工作区为空时，尝试接管 Python 当前选择：复制文件，并保留原签名以兼容旧模型。如果 Python 没有当前选择或不可用，工作区保持空态，可从原上传页面导入。
- Python 计算请求绑定独立上下文；后台训练继承提交时的引用。训练进行中不允许经 Java 切换数据集，普通查询保留各自请求开始时的版本。
- Java 或 Python 重启后，工作区选择可恢复；训练任务与已完成结果、实时会话的恢复见后文。计算管线对象仍在内存中。
- 当前实现限一个 Java 实例、一个 Python 实例、一个默认工作区。数据和模型按请求绑定，多用户与多实例调度留待后续。

完整协议及错误含义见 [数据集与工作区协议](../docs/development/contracts/dataset-workspace-v1.md)。

## 训练任务与模型库

- 训练请求先登记 Java UUID 和参数快照，再让 Python 接收同编号执行；支持可选 `Idempotency-Key`。数据库限制一次一个运行任务。
- Java 按约 2 秒间隔核对进度。暂时断联会保留原任务，显示等待核对；取消意图会持久化，算法确认停止后才进入 cancelled。
- Java 重启后继续核对；Python 重启将未完成执行标为 failed，已完成标定包可从暂存目录重新加载。训练不会因重启自动重跑。
- 点击保存时，Python 导出标定包和模型原始字节，Java 验证摘要，并在同一事务中保存模型、关联任务、更新当前选择。同一任务最多保存一行模型。
- 计算请求携带模型与未保存结果引用。列表和详情的兼容性及展示结构继续由 Python 生成，所有数据库记录和产物均通过 Java 内部只读接口获取。
- 核心训练、保存、取消和计算重启路径已在独立库联调。实际范围与未覆盖项见 [联调记录](../docs/development/06-migration-acceptance-20261019.md)，协议见 [训练和模型协议](../docs/development/contracts/training-models-v1.md)。

## 实时会话

- 准备时固定当前模型和两份实时源的副本，保存摘要与算法版本；不会因切换模型或覆盖默认源而改变已有会话。
- Java 保存当前会话与确认游标，约每 5 秒核对一次；Python 保存原副本和操作回执，私有管线仍在内存中。
- Python 重启后显示恢复提示，用户点击“恢复实时源”使用原版本重建到确认帧，保持暂停。资料缺失或版本变化时明确报错。
- `POST /api/live/sessions` 创建新会话；先暂停并等源生成完成，再在前端“重新准备”。准备成功后才切换工作区，新准备失败保留原会话。
- 开始、暂停、步进携带请求键与操作 UUID；响应不确定时核对同编号回执，避免重复推进。帧查询通过会话编号拒绝旧页面的过期请求。
- 首帧场与升级前一致；非零帧恢复、计算失联、重复步进和真实 300 秒自动推进已在独立环境通过。详见 [实时会话协议](../docs/development/contracts/live-sessions-v1.md) 与联调记录。

## 接口与响应

- 现有 28 条方法与路径组合由 `src/main/resources/legacy-api-routes.json` 登记。
- 查询字符串和上传原始字节保留；普通计算响应按流转发。实时响应解析 JSON 并补充会话编号，不重新生成网格、不改变温度数值或 `null`。
- 上游业务错误的状态码与响应体保留。未知接口为 404，已知路径不支持的方法为 405。
- Java 自身的连接失败、调用超时和上游协议异常分别返回 503、504、502，错误正文使用 `detail`。
- 上传上限默认与 Python 一致。Java 会对超过上限的请求返回 413。
- 每条请求带 `X-Request-ID`，Java 与更新后的 Python 服务记录该编号及耗时；服务需重启后加载新的日志中间件。
- 计算查询不自动重试；训练提交使用相同任务编号核对，实时播放操作使用同一操作编号及持久回执核对，不因响应丢失重新分配编号。
- Python 对已注册路径的斜杠重定向保持为当前服务的相对地址。

## 运维检查

| 地址 | 含义 |
| --- | --- |
| `http://127.0.0.1:8080/api/health` | 兼容原前端健康接口，`version` 仍是算法版本 |
| `http://127.0.0.1:8080/ops/health` | MySQL、Python 与 Java 模型模式下的内部训练、实时协议，失败返回 503 |
| `http://127.0.0.1:8080/ops/info` | Java / Spring Boot 版本、迁移阶段和接口数量 |

运维健康检查确认数据库连通，但不代表某份数据文件、模型产物或实时管线可用，需通过对应业务接口确认。请求耗时在 Java 日志中分别记录整体与 Python 调用部分。

## 基线采集与本机备份

在仓库根目录、可访问 Python 与 MySQL 的环境中执行：

```powershell
python backend/scripts/capture_migration_baseline.py --include-model-store --export-contracts
```

- `.local/migration/<时间>/`：Python 状态及 Java 工作区快照；模型表 SQL / JSON；数据集、训练任务、实时会话、操作、工作区、Flyway 记录；原始数据、默认目录中的训练暂存结果与实时源副本、会话回执；文件摘要和 Python 依赖清单。
- `docs/development/contracts/legacy-openapi.json`：导出的接口基线，不含实际温度读数或模型产物。
- `legacy-api-routes.json`：由 OpenAPI 导出的兼容接口清单。Python 新增接口后需同步采集并审阅差异。

采集过程只读模型库，不上传数据、不提交训练、不改变所选模型、不推进实时帧。本机备份与构建缓存均被 Git 忽略。

备份时结束或取消训练，暂停实时播放、上传、切换和模型保存，等准备及操作确认完毕，保证文件与数据库快照对应。默认脚本备份项目内数据；外置数据存储、训练暂存与实时会话目录需另行备份。

恢复时先新建空数据库，导入 `model-store.sql`，再导入 `dataset-workspace-store.sql`，在 Java 启动前核对记录并恢复文件。管理目录中的 UUID 和相对结构必须一致；训练暂存及实时会话目录需与对应记录同时恢复。脚本保留原时间列，跳过数据库生成列。内部凭据另行提供，不纳入备份。恢复快照中的运行任务不能续接原线程，实时管线按确认帧恢复后保持暂停。

## 迁移期间切回 Python

在 `frontend/.env.local` 中设置：

```dotenv
TFIELD_API_TARGET=http://127.0.0.1:8503
```

写入权已切换，回退前需停止新任务、结束或取消正在运行的训练并备份。停用 Java 写入，在 Python 终端配置数据库与 `TFIELD_MODEL_STORE_MODE=legacy` 后启动，再切回前端代理，并重新导入当前数据。旧模式不会继承 Java 的任务记录和暂存结果，路径变化也影响旧签名；保留 Java 登记表、数据及训练结果目录。恢复 Java 时将 Python 改回 java 模式，避免两个写入方同时运行。

## 后续工作

已完成当前单机部署入口和核心流程交接；多实例、系统服务、压力与所有故障窗口仍需按部署需求补齐。详见 [部署交接](../docs/development/05-deployment-and-acceptance.md) 与 [完整迁移计划](../docs/development/04-spring-boot-python-migration.md)。
