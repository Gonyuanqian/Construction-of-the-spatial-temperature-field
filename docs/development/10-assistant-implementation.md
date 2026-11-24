# 智能助手首期实现与运行说明

2026-10-31 最新进度：已实现服务端多轮会话、有限预算历史装配、纠错追问、坐标继承与重新绑定快照的边界，以及具体错误编号。已完成四阶段分析记录。以下首期单轮/仅浏览器历史等表述为历史阶段记录，以[多轮会话说明](14-agriseek-conversations.md)和[分析过程说明](13-agriseek-analysis-process.md)为准。

更新于 2026-10-30。分支 `codex/agri-temperature-assistant`。用户已批准 Harness 和提示词方案并授权开发。下述实现是第一阶段，尚未完成真实模型与农业领域验收。

本轮后续更新：本机已配置用户提供的 DeepSeek 凭据，官方认证接口返回 200，实际可用模型为 `deepseek-flash` 与 `deepseek-v4-pro`。无项目数据的真实 Harness 夹具完成一次工具调用/独立复核闭环，8 次模型调用、6 个执行循环、3 次候选评估；回答保留缺证据判断。首次测试曾发生输出截断，后续将单次输出预留由 2048 提升为 4096 并增加简洁要求。此记录不代表稳定性或领域质量达标。

首批 [农业温度文献资料包](../../knowledge/agri-temperature/README.md)含 6 个来源、12 个草稿单元；没有自动冒用专家审核或将其发布到生产向量库。Qdrant 与嵌入服务仍未部署/联调。

后续进度：Qdrant v1.20.0 与中文 CPU 嵌入服务已完成本机部署，13 项真实服务检查通过，包含重启持久化恢复；详见[服务部署与联调记录](11-assistant-knowledge-services.md)。前述“仍未部署”保留为历史状态，农业草稿尚未发布的边界保持不变。

最新知识进度：8 条定性文献知识经原文审校形成正式 v3 索引，本机默认选择已启用；原始草稿包不改写，4 条未通过本轮发布筛选。留出问题前三条命中 12/12，不可回答问题返回无证据 5/6，剩余失败案例与审核限制见[正式审核与评测记录](12-knowledge-review-and-retrieval.md)。此进度取代前述“尚未发布”的历史状态，不表示栽培阈值或最终模型回答已经验收。

最终复测记录：认证继续返回 200，但真实问答曾出现循环耗尽、列表序号误判及连接中断；已修正列表序号检查、直接注入固定事实减少无效往返、将检索状态登记为可引用事实，并为连接故障增加最多一次重试（失败响应按预留额度保守计入预算）。最后一次复测在两个连接尝试后仍失败，故**真实问答稳定性未通过**，不能把此前一次成功当作全面验收。当前新增后端测试 17 项通过，助手页面 3 项测试及前端构建通过；凭据不在任何 Git 非忽略文本文件中。

## 已实现

- `/assistant` 已注册并开放实时导航，沿用深蓝外壳，绕过训练数据集闸门；提供快照条、对话、作物/生育期输入、取消、进度和证据展开。
- Java 业务入口从实际实时会话绑定计算模型，在实时协调锁内调用 Python 捕获快照；没有调用准备、播放、暂停、步进接口。
- 快照在读取后立即物化并计算摘要。首期保存测点事实、源时刻、实际模型、会话清单和统计口径，后续循环不重新读取活动管线。
- 工具为 `read_snapshot` 与 `search_agri_knowledge`；`finish_answer` 是内部候选发布工具。首期明确只支持测点概览，尚未注册点位/体积/区域/历史查询工具。
- DeepSeek Function Calling、独立语义复核、引用/数字检查、最少两轮最多六轮、工具 12 次/模型 16 次/token 120000/90 秒预算及重复失败停止。思考模式目前明确关闭；保留协议消息字段，为后续启用预留。
- 运行异步执行，最多两个执行线程、四个在途任务；持久化去重，重复请求返回同一运行；取消结果不可被迟到响应覆盖；进程重启后未完成任务显示中断。
- 专用 Qdrant 适配与审核清单入库脚本。检索仅采用当前清单里的已发布、有效、作物与阶段匹配的原文；向量返回内容不直接当作知识。发布前再次检查知识清单摘要。

## 首期与完整方案的差距

- 暂使用 `.local/assistant/runs.sqlite3` 作为单机快照/任务日志，不增加 MySQL 表；未来完整会话/权限管理迁入 Java/MySQL。当前单默认工作区，未宣称多租户隔离。
- 使用普通查询轮询运行状态，尚未实现 SSE 或多轮对话记忆。每个问题独立运行，页面离开取消活动任务，历史显示仅限当前页面；已保存任务可通过 ID 查询。
- 向量检索当前为稠密召回并进行审核条件过滤，尚未完成稀疏融合、重排与农业检索基准。低召回不应解释为“农业没有此规律”。
- 当前未安装/启动 Qdrant、嵌入模型或配置收费模型密钥；没有虚构或自动批准农业阈值语料。未配置时页面如实显示。
- 当前仅验证软件边界与模拟供应商协议；并不代表领域答案准确率或真实 DeepSeek 延迟已通过验收。

## 服务配置

在启动 Python 的终端设置（密钥不能写入版本库）：

也可使用本机 `.local/assistant/credentials.json` 的 `deepseek_api_key` 字段。该目录已由 Git 忽略，环境变量优先；可通过 `TFIELD_ASSISTANT_CREDENTIALS_FILE` 指定绝对路径。本机统一启动配置已登记凭据路径，以便部署包也读取项目私有凭据；密钥本身不进入部署包或启动配置。修改后需重启已有服务才能加载新代码。

```powershell
$env:DEEPSEEK_API_KEY = '<实际密钥>'
$env:TFIELD_ASSISTANT_MODEL = 'deepseek-flash'
# 可选，默认 https://api.deepseek.com/chat/completions
$env:TFIELD_ASSISTANT_MODEL_URL = 'https://api.deepseek.com/chat/completions'
```

配置审核知识服务：

```powershell
$env:TFIELD_ASSISTANT_QDRANT_URL = 'http://127.0.0.1:6333'
$env:TFIELD_ASSISTANT_QDRANT_COLLECTION = 'agri_temperature'
$env:TFIELD_ASSISTANT_EMBEDDING_URL = 'http://127.0.0.1:8001/v1/embeddings'
$env:TFIELD_ASSISTANT_KNOWLEDGE_RELEASE = '<审核完成的清单绝对路径>'
# 有认证时另设 TFIELD_ASSISTANT_QDRANT_KEY / TFIELD_ASSISTANT_EMBEDDING_KEY
python backend/scripts/publish_assistant_knowledge.py --release '<审核完成的清单绝对路径>'
```

嵌入端点必须兼容 OpenAI 格式的 `/embeddings` 请求与返回，实际模型名由发布清单 `embedding_model` 指定。上线前固定模型修订，测量维数、召回和延迟；脚本不代替部署嵌入服务。

清单结构如下，其中没有提供未经核验的温度值，`chunks` 需由审核资料填入：

```json
{
  "release_id": "唯一且不可复用的发布版本",
  "embedding_model": "实际已部署的嵌入模型名",
  "chunks": [{
    "id": "稳定知识编号", "text": "已核对原文及完整条件", "title": "原始资料标题",
    "locator": "原文页码/章节/表格", "reviewer": "实际审核人", "reviewed_at": "2026-10-30",
    "crop": "作物名或通用机理用 *", "stage": "阶段名或通用机理用 *",
    "status": "published", "valid_from": "2026-10-30", "valid_to": "2027-10-30"
  }]
}
```

生产清单应放在受控目录；不能将普通用户可改写的文件当作审核权威。修改/撤回清单后检索立即重读；运行中清单变化会阻止旧知识候选发布。保留旧版本原文用于审计，不复用旧 `release_id` 写入新内容。

完成前后端构建并按项目现有方式启动后，访问 `/assistant`，先在实时监测准备源，再点击“绑定当前帧”。绑定结果的测点概览不依赖外部模型。发送自然语言问题需 DeepSeek 配置；农业阈值判断还需审核知识服务。

## 验证

本轮结果：新增后端 14 项测试通过，助手页面及导航 7 项测试通过，前端生产构建与 Java 编译通过。未运行全量前端测试，也没有执行真实模型调用或真实知识库联调。Java 在含中文目录的 Windows 环境编译时需使用 UTF-8（本次通过设置 `JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8` 完成）；默认 Maven Wrapper 在本机未正常启动，改用项目已缓存 Maven。

软件测试覆盖快照不可变、请求去重冲突、取消保护、重启中断、引用与数字检查、独立复核、轮数上限、上下文预算、未配置知识库和内部接口凭据。进一步需要真实 DeepSeek、Qdrant、已审核农业语料及领域人员进行端到端验收；150 条评测集与完整工具范围仍按 Harness 文档推进。

可用 `python backend/scripts/check_assistant_provider.py` 检查官方认证；附加 `--run-harness` 在临时夹具上进行真实模型测试（会消耗少量 API 用量）。只发送验证材料，不读取现场资料；运行报告写入 Git 忽略的 `.local/assistant/provider-smoke-result.json`，不含密钥。
