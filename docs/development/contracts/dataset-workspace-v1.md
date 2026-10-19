# 数据集与默认工作区协议 v1

适用版本：Java 业务服务 0.2.0 起；阶段 2 的数据协议。0.3.0 的训练与模型扩展见 [训练和模型协议](training-models-v1.md)。现有前端继续使用原接口，不要求传工作区或数据集编号。

## 1. 所有权与身份

| 对象 | 写入方 | 约定 |
| --- | --- | --- |
| `dataset_record` | Java | UUID、原文件名、相对存储键、SHA-256、旧签名、文件大小、时间范围与行列数 |
| `workspace_context` | Java | `default` 当前数据集、选择修订号、更新时间 |
| `tfield_java_schema_history` | Flyway | Java 表的版本；与旧模型表分开管理 |
| `model` | Java（0.3.0 起） | 保留原 ID；阶段 2 曾由 Python 管理 |
| 数据文件 | Java 接收；Python只读校验与计算 | `<存储根>/<UUID>/source.xlsx`；首次接管时由 Python 复制旧文件 |

UUID 用于稳定定位，内容摘要用于校验；原 `signature` 继续用于已有模型与计算缓存的兼容判断。接管旧选择时保存原签名，新导入文件生成独立版本及签名。同名、同内容上传也各登记为新版本，不覆盖旧文件。

## 2. Java 外部接口

| 方法与地址 | 请求 | 响应 |
| --- | --- | --- |
| `POST /api/dataset/upload?name=原文件名.xlsx` | 原始 XLSX 字节，最多 32 MiB（可配置） | 原六字段：`signature`、`file`、`n_times`、`n_columns`、`time_start`、`time_end` |
| `GET /api/datasets?limit=100` | limit 范围 1–500 | `items`、`current_dataset_id`、`workspace_id` |
| `GET /api/workspaces/default` | 无 | `workspace_id`、`dataset_id`（可为 null）、`revision`、`updated_at` |
| `POST /api/workspaces/default/dataset` | JSON：`{"dataset_id":"UUID"}` | 更新后的工作区；重复选择同一版本不增加修订号 |

列表条目含上传六字段及 `dataset_id`、`sha256`、`size_bytes`、`created_at`、`status: "ready"`。ready 表示导入校验通过，读取或切换时仍检查实际文件。列表目前仅返回最新 limit 条，未提供分页游标。UTC 登记时间使用带 Z 的 ISO 格式；数据测量时间保持原格式。

上传响应增加 `X-TField-Dataset-Id` 头；依赖当前训练数据的兼容转发响应带该头及 `X-TField-Workspace: default`，空工作区使用编号 `none`。原 JSON 顶层结构不变。

上传流程：写独立临时文件 → 原子改名 → Python 校验 → 检查训练状态 → 同一 MySQL 事务登记并更新工作区。事务开始前失败可清理本次新文件；提交结果不确定时保留文件，返回错误并让调用方刷新工作区确认，避免删除可能已被引用的内容。未登记的残留目录需管理员核对后清理，目前没有自动清理服务。

## 3. Java 到 Python 的请求上下文

Java 从数据库读取本次请求的数据快照，附加以下内部头；不转发浏览器提供的同名头。

| 头 | 含义 |
| --- | --- |
| `X-TField-Internal-Key` | 共用内部凭据 |
| `X-TField-Dataset-Id` | UUID；`none` 明确表示工作区未选择数据 |
| `X-TField-Dataset-Signature` | 登记的 16 位旧签名 |
| `X-TField-Dataset-Hash` | 小写十六进制 SHA-256 |
| `X-TField-Dataset-Name` | 原文件名 UTF-8，URL-safe Base64，无尾部等号 |
| `X-Request-ID` | 调用链追踪编号 |

Python 校验凭据、文件位置和摘要，通过 `ContextVar` 绑定本次请求，并在结束时释放。异步训练提交时复制上下文到执行线程。隐式“当前数据集”加载使用该引用；显式读取实时 `train.xlsx` 等路径时保留原路径自己的签名。共享 Dataset 对象不会被修改。

适用兼容请求：`/api/dataset` 及其读取子路径、`/api/features`、除 arch 外的 `/api/field/*`、标定摘要与诊断、训练提交、模型列表与保存。实时接口的数据源独立，不套用训练工作区引用。

`none` 必须触发未导入空态，不能回退到 Python 全局选择。没有上下文头的 Python 独立入口保留原有会话语义；应只在本机或受控网络访问，内部凭据不构成完整的用户权限系统。

## 4. Python 内部接口

以下接口都需内部凭据，不出现在兼容 OpenAPI 中，也不由 Java 通用转发器公开。

| 方法与地址（前缀 `/internal/v1/datasets`） | 请求与用途 |
| --- | --- |
| `POST /validate` | `{dataset_id, filename}`；校验已落盘文件，返回登记凭证 |
| `POST /check` | `{dataset_id, sha256}`；确认版本文件存在且内容一致 |
| `GET /activity` | 返回 `training_running`，用于切换协调 |
| `POST /adopt-current` | `{dataset_id}`；复制旧选择并保留其签名，不修改旧选择 |

登记凭证字段：`dataset_id`、`file`、`storage_key`、`sha256`、`legacy_signature`、`size_bytes`、`n_times`、`n_columns`、`time_start`、`time_end`。路径使用相对存储键，不接受外部任意绝对文件路径。

## 5. 错误与恢复

| 状态 | 主要情形 |
| --- | --- |
| 400 / 415 / 422 | 文件内容无效、扩展名不支持、编号或参数无效 |
| 403 | 内部调用凭据无效 |
| 404 | 登记不存在，或对应文件缺失 |
| 409 | 空工作区、摘要不一致、训练中切换冲突（由 detail 区分） |
| 413 / 507 | 上传过大、存储写入失败 |
| 502 / 503 / 504 | 上游响应异常、依赖不可用、计算转发超时 |

错误正文保持 `detail`。选择失败保留旧工作区；文件缺失或变更时明确报错，不静默换成另一份数据。Java 重启从 MySQL 读取当前选择；Python 重启从请求重新加载文件。0.3.0 起训练记录和已完成结果支持持久化，运行中执行重启后明确中断；实时管线仍需重新准备。

当前协调锁覆盖单 Java 实例内的数据选择、训练提交和模型写操作，配合数据库运行槽与 Python 活动查询。0.3.0 默认 java 模式禁止 Python 直接写模型；计算请求同时绑定模型引用。多业务实例和多用户隔离仍未实现。

## 6. 备份与下一阶段

工作区恢复需要登记表和 UUID 文件目录同时存在。运行基线采集工具会保存新增表 SQL / JSON 和默认目录中的文件，内部凭据不入备份。外置数据卷需另行备份；恢复新库时先导入模型表与登记表 SQL，再启动 Java，保留存储键结构。

阶段 3 已使用本协议的数据集 UUID 作为训练绑定依据，阶段 4 已接入独立实时会话与恢复，阶段 5 已完成单机统一部署及核心业务联调。详见 [实时会话协议](live-sessions-v1.md) 与 [实际联调记录](../06-migration-acceptance-20261019.md)。更多故障窗口和运维范围按部署环境继续安排。
