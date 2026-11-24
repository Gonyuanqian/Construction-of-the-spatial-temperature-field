# 动态分析摘要与 DSH reasoning 通道的区分

更新：2026-10-31。

后续状态：原生通道已经在 [19-agriseek-native-thinking.md](19-agriseek-native-thinking.md) 接入；以下 disabled 描述记录本文件交付时的状态。当前主 Agent 默认启用原生 thinking，页面仍明确展示公开分析摘要。

## 核对的上游设计

固定参考 `deepseek-ai/deepseek-harness` 提交 `ce7073d51254c26cd63b22a60835b8f948deb447`：

- [内容块源码](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/packages/llm/llm/src/types.ts)定义独立的 TextBlock、ReasoningBlock 与 ToolCallBlock。
- [流式子系统文档](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/subsystems/llm-streaming.zh.md)定义 reasoning-delta、block-start/end、工具参数片段及组装规则。
- [Conversation 组装](https://github.com/deepseek-ai/deepseek-harness/blob/ce7073d51254c26cd63b22a60835b8f948deb447/docs/subsystems/conversation.zh.md)按稳定身份组织内容与执行事件，供不同视图消费。
- [DeepSeek thinking 接口](https://api-docs.deepseek.com/guides/thinking_mode/)通过 reasoning_content 区分原生推理与正文。

这些资料说明内容通道、数据结构、传输与组装；不能仅凭这些接口推断具体训练数据、Few-Shot CoT 策略或某种思考顺序是官方固定规范。`<think>` 等标签也不是业务工作流。

## AgriSeek 当前边界

现有模型请求仍是 `thinking=disabled`，页面不是供应商原生 reasoning_content 的回放。公开内容应称为“分析摘要”，如实说明任务目标、实际取数与候选检查。不得把后端四步执行表包装成模型自己产生的完整思维过程。

本次交付是动态公开摘要。没有开启或展示完整原生内部推理，也没有新增按固定顺序撰写内部推理的提示词。

## 动态节点

内部旧版四阶段状态继续用于运行器审计；新记录另提供 `analysis.public_nodes`，前端优先渲染这些节点：

- 任务目标节点：标题与要点来自本轮模型生成的 user_goal / answer_outline；摘要失败时保留原问题。
- 工具节点：实际调用才创建，按调用 ID 从 running 更新到完成或未完成；包含实际资料或事实引用，不展示原始工具参数。
- 候选检查节点：按实际检查次数创建；未通过时可展示审核器的简短问题说明与修订建议，通过时说明核验已完成。
- 结果节点：从实际终态生成，取消或故障会关闭未完成节点，不补造未发生的步骤。

没有工具调用就没有取数/检索节点；没有作物阈值证据就不显示“已比对阈值”；没有异常归因执行就不声称完成归因。内容、节点数量和顺序来自本轮任务与执行。标题不是固定的“需求解析→数据获取→对比分析→得出结论”。历史四阶段记录保持原样，前端兼容读取，不重写历史。

节点仍随既有事务性会话检查点和 SSE 传输，复用稳定会话/轮次 ID、顺序事件、断线续接与回放。`AssistantActivity` 保留为可选的技术执行明细；分析摘要不是完整内部推理或逐 token 思考直播。

## 自然语言约束

验证中发现旧关键词判断将“不必检索资料”也当成了要求检索。新增否定请求识别：明确不必/无需/不要搜索或检索的本轮请求，不强制联网，也不注册资料检索工具；现场数值工具仍按任务能力边界工作。这样摘要只出现实际选择与允许执行的动作。

## 验证

- 完整后端回归 127 项通过：动态节点身份更新、无工具时不虚构步骤、取消关闭、历史恢复与既有知识/数据核验。
- 前端回归 39 项通过：只显示本轮节点，空节点不渲染四阶段占位，新旧记录均可显示，文本仍按纯文本渲染。
- 否定检索约束及综合回答/分析的 40 项定向测试通过，覆盖额外三个否定用例。
- Vue 类型检查/生产构建、Java 打包通过。
- 真实模型独立线性场三轮验收 3/3：点位 15 °C → 修改坐标 17 °C → 关联历史的纠错澄清；报告 `.local/assistant/conversation-live.json`。不使用用户棚内观测数据。

页面实测“简要解释温度为什么会影响植物生长，不必检索资料”：59.277 秒完成，两次候选检查，联网搜索与原文读取均为零。公开节点只有模型任务目标、两次实际检查和最终发布结果，没有数据获取、阈值比对或归因等未执行步骤。报告 `.local/assistant/dynamic-summary-browser.json`。后续还修正了任务理解的技术调用标签，并让通过检查的节点也展示审核器返回的简短相关性与不确定性结论，相关 13 项定向测试通过。本文件不把模型调用成功等同于农艺专家认证。
