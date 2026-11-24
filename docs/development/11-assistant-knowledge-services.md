# Qdrant 与本地嵌入服务部署联调

日期：2026-10-30。结论：**本机真实服务联调 13 项检查通过，重启恢复通过**。测试只涉及工程夹具，不构成农业知识审核或检索质量验收。

## 实际部署

| 服务 | 固定版本与运行方式 | 本机地址 |
| --- | --- | --- |
| Qdrant | 官方 Windows x64 程序 v1.20.0，独立持久化存储 | `127.0.0.1:6333` HTTP；`127.0.0.1:6334` gRPC |
| 嵌入服务 | `BAAI/bge-small-zh-v1.5`，修订 `7999e1d3359715c523056ef9478215996d62a620`，CPU | `127.0.0.1:8001/v1/embeddings` |

Qdrant ZIP 从[官方 Release](https://github.com/qdrant/qdrant/releases/tag/v1.20.0)下载，并与该发布资产 SHA-256 校验一致：`6d13553584fd0411f00637519e293331ff0aa1fb79bd9e30db45839bb75de2be`。模型从[原始模型仓库](https://huggingface.co/BAAI/bge-small-zh-v1.5)按固定修订下载，各文件摘要记录于本机安装清单。

本机无 Docker，故采用原生程序；嵌入模型不执行远程代码，只加载本地 safetensors。输出为 512 维、经 L2 归一化的 CLS 向量，最大输入 512 tokens。超长文本返回 422，不能悄悄截掉作物条件。当前未添加 query 专用 instruction，索引与查询走同一编码方式；后续检索质量实验可比较指令策略并固定版本。

此模型用于轻量中文 CPU 工程联调，**不是 BGE-M3，也不代表已证明它最适合农业知识**。原资料草稿仍记录原候选模型；不能把其模型名直接用于本服务。正式发布时应选择模型、修订及切片策略并新建相应集合，禁止不同嵌入空间混用。

程序与权重存于 `.tools/assistant/`；配置、日志、安装摘要、数据库和测试报告存于 `.local/assistant/services/`，均由现有 Git 忽略规则排除。Qdrant telemetry 已禁用；两个服务仅监听回环地址。Windows 官方包没有附带 Dashboard 静态文件，本次验证的是实际数据库 HTTP/gRPC 服务，不声称管理网页已经安装。

## 测试结果

独立集合 `assistant_integration_c898540a78c7`，仅包含三条合成工程事实，不包含农业阈值或用户现场数据。调用了项目真实入库脚本、真实嵌入端点和生产检索适配器。

| 检查 | 结果 |
| --- | --- |
| 批量输出维数、有限值与归一化 | 通过 |
| 重复编码结果一致，容差内一致 | 通过 |
| 错误模型名拒绝 | 通过 |
| 空文本拒绝 | 通过 |
| 超长文本拒绝而不截断 | 通过 |
| 实际发布脚本写入 Qdrant | 通过 |
| 中文语义检索首位返回目标事实 | 通过 |
| 不匹配作物资料过滤 | 通过 |
| 索引保留旧点时，目录撤回/草稿仍被过滤 | 通过 |
| 真实文献资料包的草稿不被发布 | 通过 |
| 服务重启后原集合三条向量仍存在 | 通过 |
| 嵌入模型重启后重新就绪 | 通过 |
| 错误向量维数被 Qdrant 拒绝 | 通过 |

首轮批量编码两条短句耗时约 2.18 秒，包含冷请求影响；单一样本不作为平均延迟或容量指标。未测试大量数据、并发压力、服务崩溃一致性、多实例或设备外网访问。重启恢复验证不代表穷举断电窗口。

此外，本轮既有助手后端 17 项回归测试通过，新增服务与脚本完成语法检查；未再次运行与本改动无关的全量前端测试。

## 日常运行与复测

在项目根目录运行：

```powershell
# 已安装时无需重复下载；首次安装使用此脚本
python backend/scripts/setup_assistant_services.py

.\scripts\assistant-services.ps1 Start
.\scripts\assistant-services.ps1 Status

# 完整联调使用新建的独立测试集合，会保留集合用于重启检查
python backend/scripts/check_assistant_knowledge_services.py

# Stop 只停止该脚本登记且启动时刻匹配的服务；保留数据和模型
.\scripts\assistant-services.ps1 Stop
.\scripts\assistant-services.ps1 Start
python backend/scripts/check_assistant_knowledge_services.py --verify-restart
```

脚本后台启动进程，不弹出窗口；端口占用时退出，不自动终止其他应用。启动记录包含进程编号和启动时刻，避免复用 PID 时停止其他进程。`Status` 表示进程存在，实际就绪分别检查 Qdrant 根路径和嵌入 `/health`。嵌入模型冷启动需要时间，联调脚本最多等待 120 秒。

`Start` 优先使用 `.local/system.local.json` 的 `PythonExe`，否则使用当前 `python`；依赖见 `backend/requirements-embedding.txt`。本次复用了已安装的 Python/PyTorch/Transformers，没有修改全局 Python 依赖。需更换 Python 时建议单独环境。

安装清单：`.local/assistant/services/installation.json`；运行报告：`.local/assistant/services/integration-result.json`；日志：同目录 `qdrant.*.log`、`embedding.*.log`。模型/数据目录不要随意清理。

## 业务接入状态

本机统一启动配置已补充 Qdrant URL、嵌入 URL 和预留集合名称（仅在相应字段原先未配置时补充）。**没有选择正式发布清单、没有把测试集合接到业务问答，也没有改变 12 条文献草稿的状态。** 因此助手的“农业知识库尚未配置审核资料”仍可能是正确状态；不能把服务已启动等同于领域知识已上线。

下一步是审核可发布知识、建立与实际嵌入模型一致的发布版本并完成农业检索评测，再配置业务 `TFIELD_ASSISTANT_KNOWLEDGE_RELEASE`。DeepSeek 外部连接的稳定性问题独立存在，不由本次本地向量服务联调结果替代。
