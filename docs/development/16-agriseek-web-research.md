# AgriSeek 联网检索与原文证据

更新：2026-10-31。提示词版本：`agri-temperature-v0.5-web-research`。

## 问题与行为

此前运行器只注册本地 `search_agri_knowledge`，系统提示词也限定了证据来源。本地发布清单没有相关条目时，助手既没有外部搜索工具，也不能自行补造知识。

现在采用“本地资料 + 本轮联网证据”：

1. 默认开启联网，本地查询无命中、未配置或暂不可用时，自动搜索外部来源并尝试读取前两个来源的原文。
2. 本地已有条目但不足以回答时，模型可调用联网工具补充；“联网、搜索、检索、最新、近期”等明确要求会在首次模型生成前进行联网准备。
3. 现场读数、极值和区域统计仍来自固定快照；纯现场数值查询不注册联网工具。论文问答不会仅因包含“现在/当前”就要求绑定快照。
4. 输入框增加“联网搜索”开关，关闭后本轮不注册、调用外部工具，设置随请求和会话记录保存。新对话默认开启。
5. 最终引用单独显示“联网原文”、来源网址、读取日期与未入库标记；执行记录显示实际搜索、读取及复核过程。

## 服务与工具

通过 [DeepSeek 官方 Search / Fetch API](https://api-docs.deepseek.com/guides/search/) 使用现有服务端凭据，无新增供应商密钥。请求只访问固定官方 API 域名；前端不持有密钥。

| 工具 | 输入 | 返回与约束 |
| --- | --- | --- |
| `search_web` | 最多 128 字的公开农业 query | 筛选后的 `S:` 来源线索；不直接生成可引用证据 |
| `read_web_source` | 本轮搜索返回的 source_id | 有界原文选段及 `W:` 证据、网址、读取日期、内容哈希 |
| `search_agri_knowledge` | 本地 query、既有作物/阶段条件 | 保留已审校 K: 查询；无有效条目时尝试前述联网链路 |

Search 请求启用 `need_content=true`。原始 `content` 暂存在当前运行器内，读取工具优先从该原文选段；缺失时调用 Fetch。`snippet` / `summary` 不进入事实证据。此次真实联调中部分 Fetch 请求返回 404，Search 的原文字段可用，因此不强制依赖一次独立 Fetch 成功。

原文可能只来自可访问的摘要页面，不表示已读论文全文。`original_verified` 仅表示本轮确实取得了原始内容字段，不是对来源结论的专家认证。最终引用还需要候选引用和适用条件复核。

每轮最多 2 次不同搜索、3 次不同原文读取；重复查询或读取复用本轮缓存。每次外部请求至多 8 秒、响应上限 2 MB；单份选段约 2200 UTF-8 字节，最多选 3 个原文段落。既有 90 秒总预算、12 次工具、16 次模型、6 轮上限与至少两次候选检查继续生效。Search 返回原文时无需额外 Fetch 请求；实际服务计费以官方说明为准。

## 来源及发布规则

- 只采用 HTTPS、公开机构、大学/政府及已登记出版方域名；实现清单在 `web_research.py`。搜索排名、authority 或域名本身都不作为事实正确的证明。
- 不能读取任意用户网址、私有 IP、带账号密码的 URL、非标准端口，或其他运行器的来源编号。读取目标必须来自本轮已筛选搜索结果。
- 搜索仅发送公开农学关键词；常见凭据、邮箱、会话编号、链接被拒绝，显式坐标和带温度单位的现场数值会从查询中去除。不把完整快照、聊天记录或本棚读数作为搜索上下文发送。
- 原文和工具返回中的命令不具有权限；生成器和复核器提示词均要求把它们视为待核验资料。
- `K:` 继续使用本地发布清单及既有严格引用规则；`W:` 是本轮外部证据，不能自称已入库或经农业专家审定。
- 每条 W: 主张单独引用一份成功读取的原文，允许忠实中文概述；数字必须出现在实际原文选段中，不能从 URL 或读取日期凑数字。还须检查温度对象、作物、品种、设施和实验条件。
- 两次复核通过后，最终引用标记 `review_status=claim_review_passed`；论文实验温度不自动变成本棚设定值，外部文章不能补充现场实测值。
- 不自动写入 Qdrant。正式知识入库仍走独立整理和审核流程。SQLite 只随问答保存最终引用片段及执行记录，不保存完整外部页面。
- 当外部渠道暂不可用或没有可核验原文时，保留清楚的状态说明。原文预算耗尽且没有有效知识时提前停止，避免重复复核空答案；现场事实若已取得仍按既有 partial 规则保留。

## 配置与兼容

- `DEEPSEEK_API_KEY` 或现有忽略目录凭据文件继续生效，不新增浏览器凭据。
- `TFIELD_ASSISTANT_WEB_SEARCH=false` 可全局关闭外部工具；默认启用。
- POST `/api/assistant/runs` 新增可选 `web_search_enabled`，默认 true；纳入幂等请求指纹。
- capabilities 新增 `web_search_configured`；运行记录增加 `web_search_calls` / `web_read_calls`。
- 使用既有 Java JSON 代理、SSE 事件、会话节点组装和多轮父链，未新增浏览器直连第三方服务。

## 验证

后端 113 项通过，新增 24 项涵盖原文/摘要分离、Search 原文兼容、来源和查询约束、同轮缓存/预算、跨运行器隔离、失败脱敏、外部数值来源、自动补充、关闭联网与路由。前端 37 项通过，包含开关请求、新对话默认值、外部引用日期与链接展示，及既有会话/事件流回归。Vue 类型检查与构建、Java 打包通过。

真实模型与公开来源验收：

- 本地无命中模拟：DIF 与株高机理问题，自动搜索 1 次、读取 2 次、复核 2 次，23.55 秒，回答包含 W: 引用。
- 明确联网请求：同一主题，搜索 2 次、读取 2 次、复核 2 次，18.26 秒，回答包含 W: 引用。
- 两项使用独立临时会话数据库；第一项模拟本地无命中，不修改正式 Qdrant。正式本地库只读检查也显示 DIF/株高主题无命中。
- 浏览器正式链路：同一 DIF 问题 27 秒完成；事件日志确认“本地资料不足”后自动执行搜索、读取两份原文，最终 W: 引用来自出版方和 Wageningen University 机构来源。来源链接、读取日期、联网开关均已检查，报告 `.local/assistant/web-browser.json`，截图 `outputs/agriseek-web-research.jpg`。
- 首次联调因原文通道失败未通过，旧报告保留在忽略目录；采用 Search 原文字段后重新通过，未放宽证据检查规则。

报告：`.local/assistant/web-live-auto.json`、`web-live-explicit.json`。这些结果验证工具交互和引用发布流程，不代表农艺专家认证或未来每个网页均可读取。

```powershell
# backend 目录
python -m pytest tests/test_assistant_web.py tests/test_assistant_stream.py tests/test_assistant_conversation.py tests/test_assistant.py tests/test_assistant_analysis.py tests/test_assistant_field_tools.py tests/test_volume_sample.py -q
# frontend 目录
npm test -- src/assistant/conversation.test.ts src/views/AssistantView.test.ts src/components/AssistantAnalysis.test.ts src/App.test.ts
# 根目录：真实模型、公开来源；不修改正式知识索引
python -X utf8 backend/scripts/evaluate_assistant_web.py --empty-local
python -X utf8 backend/scripts/evaluate_assistant_web.py --question '请联网检索温室 DIF 昼夜温差与株高的研究，并给出出处，不给本棚设备设定值。'
```
