# AgriSeek 原生 thinking 通道

更新：2026-10-31。提示词版本：`agri-temperature-v0.7-native-thinking`。

后续意图校正、连续审核止损、保守恢复及 UI 精简见 [20-agriseek-intent-and-recovery.md](20-agriseek-intent-and-recovery.md)。当前公开界面已移除单独的通道工程状态行，原生推理续接仍启用。

## 实现范围

主回答 Agent 已实际开启 DeepSeek 原生 thinking，接收流式 `reasoning_content`，在同一次 Agent 执行的后续工具轮次完整回传。这里不是提示模型写出一个 `<think>` 文本块，也不是把公开四步摘要改名为原生推理。

原生推理只存在运行器内存和发往 DeepSeek 的当前执行上下文中；不写 SQLite、会话事件、前端缓存、诊断或日志。页面独立显示原生通道状态，继续展示动态公开分析摘要、真实工具执行记录及审核通过的回答。摘要不是内部推理原文的逐字回放。

## 协议依据与请求方式

依据 [DeepSeek thinking 文档](https://api-docs.deepseek.com/guides/thinking_mode/)、[工具调用文档](https://api-docs.deepseek.com/guides/tool_calls/)和 [Chat Completions 接口](https://api-docs.deepseek.com/api/create-chat-completion/)。

- 默认模型沿用现有 `deepseek-flash` 配置；主回答请求使用 `thinking.type=enabled`、`reasoning_effort=low`、`stream=true`。
- thinking 模式不支持 `tool_choice=required` 或指定某个工具，改用 `auto`。实际工具仍从本轮路由允许的注册列表中选择和校验。
- 流中分别组装 `reasoning_content`、`content` 与 `tool_calls`。工具参数完整、结束原因正确、收到 `[DONE]` 之后才允许分发。
- 主 Agent 每条 assistant 消息保留完整原生推理；同一执行中的后续请求原样回传，包括合法的无工具正文消息。不得裁切当前执行的推理来节省上下文。
- 跨用户轮次沿用已有服务端公开历史摘要，不持久化原始推理。传输时为这些合成的历史 assistant 消息补空 `reasoning_content`；真实模型多轮已验证可接受。
- 任务理解、正文格式整理、独立审核继续使用非 thinking JSON 请求，以约束辅助调用成本，不把它们标成原生推理生成。

## 原生正文与审核

`tool_choice=auto` 下，模型可以返回 `finish_reason=stop` 和正文而没有工具调用。这是合法终态，不能再直接报 `model_tool_protocol`。

运行器先尝试将该正文读为 Candidate JSON；若是自然语言，用一次独立非 thinking 请求将**公开正文草稿**整理为候选，不向整理器提供原生推理。该候选和 `finish_answer` 提交的候选使用同一套规则及独立审核。格式不合法、核验失败或输出截断时不发布草稿；不会从正文猜测工具名称或伪造 tool result。

两种提交路径都把简短失败检查和修订建议反馈给主 Agent。最低两个 Agent 循环、至少两次候选检查，最多六个循环；重复失败无进展时提前停止。现场数字继续要求本轮固定快照事实，外部资料仍作为辅助证据。原生 thinking 不绕过这些规则。

## 公开元数据与生命周期

Run 的 `thinking` 仅含 `enabled`、`effort`、`calls`、`reasoning_chars`、`status`。字符数是本轮已接收推理字符数（含可能中断的接收尝试），不是 token 数或质量评分。接收状态最多约每半秒随现有事务性检查点/SSE 更新，不增加原文事件类型。

页面有实际原生调用后才显示通道状态；无模型调用的澄清不伪称已推理。完成、取消、失败和服务重启都会关闭状态。取消后既不能分发迟到工具，也不能覆盖已取消任务的结果。重启只回放公开状态与摘要，正在运行的原生推理不会恢复。

## 预算和回退

- 原生主调用单次输出上限 8192 token，共享推理与正文；保守输入预算按 UTF-8 字节和输出预留合计不超过 64000 计，包含完整原生回传。
- 非 thinking 辅助调用继续按 32000 的保守上下文预算执行。公开历史最多四轮、6000 字节，先于本轮执行消息裁剪。
- 原生模式单轮任务墙钟预算 180 秒，单次 HTTP 超时最多 45 秒；非原生回退仍为 90 秒/25 秒。运行器在流片段间检查总预算和取消。
- 现有最多 16 次模型调用、12 次工具调用、120000 token 总预算和有限重试继续生效。流大小上限 512 KiB，不截断工具参数后执行。
- 环境变量 `TFIELD_ASSISTANT_THINKING_ENABLED=false` 可整体回退；API `thinking_enabled=false` 可对单次任务回退。非 thinking 模式保留 `tool_choice=required` 和最多一次协议纠正。旧会话不重写。

## 验证记录

- 后端相关回归 **139 项通过**，其中新增原生通道专项 **9 项**：分片通道隔离、工具轮次完整回传、纯正文转候选、无效正文拒绝、空正文重试保留原生推理、取消、预算、全局回退、真实 HTTP 流路径与跨轮历史隔离。测试直接检查运行记录、SQLite 事件和公开会话中没有原生推理测试标记。
- 助手及相关前端 **53 项通过**（页面、摘要、会话组装、API、导航、App 外框），包含原生状态与审核后正文分开展示。
- Vue 类型检查、生产构建和 Java 打包通过。当前本地运行包 `.local/releases/20261031-221947-254`。
- 真实 DeepSeek 独立线性温度场 **3/3**：首问 15°C、继承位置上下文的追问 17°C、笼统纠错请求澄清；前两轮实际收到原生推理并完成工具续接。新会话保持隔离。报告 `.local/assistant/conversation-live.json`。
- 真实农业通识“不必检索”用例 21.48 秒完成，两次原生调用、两次候选检查，搜索和原文读取均为零。报告 `.local/assistant/protocol-live.json`。
- 浏览器同类用例 22.995 秒完成，实际接收 619 个原生推理字符，页面显示原生状态与动态公开摘要，公开会话/事件无 `reasoning_content` 字段。报告 `.local/assistant/native-thinking-browser.json`；截图 `outputs/agriseek-native-thinking.jpg`。
- 重启后恢复原实时会话 `35ef4fb1-9487-4077-aa6c-2db3208df2a5`、模型 B、游标 0，未推进回放。

全站前端运行结果为 575 项通过、60 项失败（12 个文件），另有实时监测组件挂载的未处理错误。失败涉及旧版导航数量、设计令牌、标题外观、实时布局、三维与实时页测试等，完整输出 `.local/assistant/native-frontend-tests.txt`；这些未计为本次通过项，也未在本次原生通道任务中扩展修改。通过当前验收不等同于农艺内容专家认证或模型可靠性保证。
