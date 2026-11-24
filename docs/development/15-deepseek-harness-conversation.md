# AgriSeek 对话交互系统：deepseek-harness 设计应用

更新：2026-10-31。

## 参考来源与范围

参考 DeepSeek 官方仓库 `deepseek-ai/deepseek-harness`，固定提交
`ce7073d51254c26cd63b22a60835b8f948deb447`。本次阅读设计文档并自行实现适配，不安装或执行上游代码，不引入 Cordis 或替换 Vue / Java / Python 技术栈。

- [Conversation 组装专项设计](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/subsystems/conversation.zh.md)
- [Conversation Node 组装决策](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/.agents/notes/implemented/architecture/2026-08-09-client-conversation-node-assembly.zh.md)
- [LLM Streaming 接口与组装](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/subsystems/llm-streaming.zh.md)
- [Web Client 所有权与分层](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/subsystems/web-client.zh.md)
- [DeepSeek Chat Completions 协议](https://api-docs.deepseek.com/api/create-chat-completion/)

参考文档副本及 SHA256 清单位于忽略目录 `.local/references/deepseek-harness/`。实现以当前 subsystem 文档为准；早期节点决策笔记用于理解设计动机。

## 设计映射

| 上游设计 | AgriSeek 实现 | 解决的问题 |
| --- | --- | --- |
| Host 持有权威状态和持久事件顺序 | Python SQLite `runs` + `assistant_events`，同事务更新 | 页面不编造历史和执行结果 |
| 连续 SessionEvent window | 每会话递增 `seq`，原子快照 + cursor，SSE 续接 | 读取历史与接收实时更新之间不丢事件 |
| `(kind,id)` 关联 Context | 独立 TS `ConversationAssembler`、Definition 注册表 | 更新按显式 ID 归属，不猜“最近一个未完成工具” |
| Turn/Step Location | `turn_id=run.id`、`step_id=run.id:step:cycle` | 多轮和同轮多次工具执行有明确坐标 |
| checkpoint 独立恢复节点 | `turn/checkpoint` / `turn/end` 携带完整公开 run；活动更新携带完整身份与状态 | 加载窗口缺少 start 时仍能恢复 |
| Client model 与 transport / UI 分离 | `ConversationSession` 管连接代次/游标/重试；Assembler 管节点；Vue 接收快照 | 流协议和重连逻辑不再散落在页面组件 |
| 稳定节点与统一折叠 | `replace`、`append`、`prepend` 共用 Definition；未变化节点复用对象 | 回放和实时结果一致，重复事件不重复渲染 |
| 流式 block / tool 组装后执行 | `model_stream.collect` 按 tool index 组装碎片，终止标志和工具身份校验 | 半段 JSON、截断输出和歧义工具不能进入执行器 |

本次将模型内容和工具参数视为内部生成块；公开业务流仅发布实际执行摘要、状态和审核后的答案。没有把供应商内部推理字段直接变成 UI 的“思考过程”。四阶段分析仍是按真实执行整理的公开记录。

## 数据流

```mermaid
flowchart LR
  D[DeepSeek SSE] --> B[有界内容与工具块组装]
  B --> R[工具执行及独立证据复核]
  R --> S[SQLite 任务状态与事件日志]
  S --> P[Python SSE 事件接口]
  P --> J[Java 增量转发]
  J --> C[Session Controller]
  C --> A[Conversation Assembler]
  A --> V[Vue 分析记录与执行节点]
```

原有受控 ReAct 循环、至少两轮复核、最多六轮、模型/工具预算、固定快照、当前轮证据要求、多轮历史裁剪继续生效。此次没有改变知识结论的发布规则。

## 事件和接口契约

公开事件：

```json
{"seq":12,"type":"activity/update","time":1793440000.0,"turn_id":"run-uuid","step_id":"run-uuid:step:1","data":{"id":"run-uuid:model:1","kind":"model","status":"running","label":"生成候选与工具请求","received_chars":128,"tool_count":1}}
```

- `turn/start`：提交成功后与 run 同事务写入，幂等重试不产生第二条 start。
- `turn/checkpoint`：公开任务状态变化；纯内部审核原文变化不写公开事件。
- `turn/end`：终态状态、已审核结果和分析摘要原子写入。取消后不接受迟到模型或活动更新。
- `activity/update`：显式关联模型请求或工具调用，公开字段白名单；同 ID 从 running 进入 completed / failed。工具完成只表示调用返回，候选通过与否由四阶段分析及最终状态说明。
- 重启恢复将遗留活动任务持久化为 interrupted 并写一条 end；重复读取不重复写入。

Java 业务入口：

| 接口 | 行为 |
| --- | --- |
| `GET /api/assistant/conversations/{id}` | 同一事务读取最近 100 轮、最近 128 条公开事件、cursor 和 `protocol_version=1` |
| `GET /api/assistant/conversations/{id}/events?after=12&limit=100` | 升序返回游标之后的事件；limit 1–200；未来或负游标拒绝 |
| `GET /api/assistant/conversations/{id}/stream?after=12` | 从 13 开始续接，`event:session`、`id:13`、JSON data；ready 声明协议版本 |

SSE 每 5 秒心跳，单连接最多 25 秒，客户端自动续接。Java 使用 `StreamingResponseBody` 读取后立即 flush，不走 JSON 缓冲；异步线程池核心 2、最大 8、队列 16，MVC 超时 35 秒。内部服务凭据只由 Java 添加。无效会话或游标在提交 HTTP 200 前验证。

客户端先装载服务端快照，再从该快照 cursor 接收增量。重复 seq 忽略，发现缺口则重新读取原子快照；连续流失败时临时同步任务状态，随后重试流。连接代次阻止旧连接在切换会话后写入新会话。POST 返回的旧 queued 状态不能覆盖更高 event_seq 的结果。

离开或刷新页面只断开观察连接，后台任务继续；明确点击“取消分析”才取消任务并关闭正在读取的供应商响应。原有会话父链、并发 head 校验和新对话隔离仍由后端负责。

## 内容发布与资源边界

模型调用真实启用 `stream:true`，按 UTF-8 SSE 帧读取，累积 content 和按 index 交错到达的 tool 参数；`reasoning_content` 不累积、不落盘、不传前端。最大响应 512 KiB，最多 4 个工具，每个参数最多 16384 字符。工具 ID 改变、重复 ID、缺少 finish / DONE、无效 JSON 都失败退出。`length` 等非正常结束丢弃工具请求，现有运行器拒绝发布。中途取消或预算耗尽同样不执行未结算块。

当前农业领域采用“生成内部候选 → 引用/数值检查 → 独立复核 → 发布终态结果”。因此浏览器实时看到模型与工具状态、四阶段分析；最终正文在审核通过后发布，不伪装成已经通过审核的逐 token 文本。失败时仍可显示程序工具独立确认的现场事实，并标明 partial。

历史显示窗口和送入模型的上下文预算不同：UI 快照最多 100 轮，初始执行轨迹最多 128 事件；全量事件仍在 SQLite，可通过 events 分批读取。组装层支持 prepend，但本次未新增更早历史翻页按钮。模型历史仍最多 4 轮 / 6000 UTF-8 字节。

当前事件日志不自动清理；这是单工作区应用，尚不构成面向多租户的权限模型。现有实时监测外框、顶部标题和左右导航布局保留。

## 验证记录

### 工具协议纠错补丁（2026-10-31）

后续原生通道改造见 [19-agriseek-native-thinking.md](19-agriseek-native-thinking.md)。以下 required/disabled 方案保留为非 thinking 回退路径；当前原生主循环使用 auto，并允许正文转候选后进入同一审核流程。

一次“温度与植被生长的关系”问答已读取固定上下文并检索到三条本地资料，但第二次模型输出正文、没有 tool_calls。事件记录中最后一次正文进度为 57 字符，工具数为 0。运行器随后触发 `model_tool_protocol`，尚未进入候选复核。该次没有执行联网工具，不能据此判断联网故障或没有知识资料。

根因是请求/运行器契约不一致：请求带 tools 却没有设置 tool_choice，供应商默认 auto 允许普通消息，而运行器要求通过工具提交每一步，包括 finish_answer。[官方参数说明](https://api-docs.deepseek.com/api/create-chat-completion/)明确 required 在关闭 thinking 时要求工具调用。

修复：主循环显式 `thinking=disabled` + `tool_choice=required`；审核器继续使用无工具的 JSON 输出。收到完整但无工具的响应时，每个 run 至多纠正一次格式，保留已完成工具结果、不重跑任务；追加纠正请求后仍无调用则受限失败。不会从普通文本或 JSON 猜测工具名、补造调用，也不会直接发布草稿。原有两轮审核、工具/模型计数、时间和上下文预算、取消保护继续生效，流截断和不完整工具块仍拒绝执行。

新增 `protocol_repairs`；内部记录仅包含 finish_reason、工具数量、正文类型/长度及模型调用编号。持续失败时公开同类脱敏诊断，不保存或回传供应商草稿及内部推理。新增回归覆盖文本/空内容/普通 JSON 的纠正、已执行工具结果保留、每轮任务一次上限、连续不合规停止、取消和异常工具数量；后端累计 121 项通过。

真实 DeepSeek 独立会话复测“温度与植被生长的关系”：64.28 秒回答成功，8 次模型调用、3 次候选检查、1 次联网搜索和1份联网原文；本次 `protocol_repairs=0`，显式 required 已使模型按工具协议返回。引用包含本地 FAO 资料和中国气象局来源。报告 `.local/assistant/protocol-live.json`。完整 Vue 类型检查/生产构建及 Java 打包通过。

- 后端 89 项通过：新增测试覆盖并发事件序号、取消与迟到结果、重启事件、鉴权与游标、交错工具碎片、截断/缺帧/重复 ID 拒绝、真实 HTTP 流式调用路径、仅终态发布答案。
- 前端 35 项通过：回放与实时一致、节点身份复用、补历史、缺口/重复、旧响应不回退、新旧连接隔离、失败降级、跨 UTF-8 字节和多行 SSE；包括已有助手页面与 App 回归。
- Vue 类型检查及生产构建、Java Maven 打包通过。Java 构建脚本跳过单元测试；业务流代理另做 HTTP 联调。
- 真实 DeepSeek 独立线性场验收 3/3：15 °C → 换坐标 17 °C → 关联上一轮的纠错澄清；报告 `.local/assistant/conversation-live.json`。该结果验证交互链路，不代表农艺专家验收。
- Java8080 → Python8503 断线续接联调：先收到 seq 1/2/3，重连从 4/5 继续；报告 `.local/assistant/stream-gateway.json`。
- 浏览器：运行中刷新后恢复任务，保留最终来源引用及模型/工具执行节点；随后纠错追问继续关联同一会话。

复现命令：

```powershell
# backend 目录
python -m pytest tests/test_assistant_stream.py tests/test_assistant_conversation.py tests/test_assistant.py tests/test_assistant_analysis.py tests/test_assistant_field_tools.py tests/test_volume_sample.py -q
# frontend 目录
npm test -- src/assistant/conversation.test.ts src/views/AssistantView.test.ts src/components/AssistantAnalysis.test.ts src/App.test.ts
# 项目根目录；使用真实模型
python -X utf8 backend/scripts/evaluate_assistant_conversations.py --live
```
