# 农业知识审核、正式索引与检索评测

日期：2026-10-30。当前正式版本：`agri-temperature-qualitative-20261030-v3`。**8 个知识单元、4 个来源已入正式索引并选为本机默认版本；范围仅限定性解释与研究边界。**

## 审核依据与逐条结论

用户已明确授权继续审核、建立正式索引并评测。本轮是 Codex 依据原文进行的内容审校，不冒用农业专家身份，也不代表专家会签。没有发布作物温度阈值、设备处方或现场误差。

原始 [12 条草稿](../../knowledge/agri-temperature/literature-seed-v1.json)保持不变。[审核记录](../../knowledge/agri-temperature/review-v1.json)对每条登记依据、结论和限制；[最终修订](../../knowledge/agri-temperature/review-amendment-v3.json)将案例中的“观察到”收紧为“模拟结果显示”，避免把 CFD 结果当作现场实测。来源与本系统的使用限制分字段保存。

| 原始知识编号 | 决定 | 原文定位/保留原因 |
| --- | --- | --- |
| FAO217-temperature-target | 发布 | FAO Chapter 2，印刷 p.31 / PDF p.47 |
| FAO217-natural-ventilation | 发布 | FAO Chapter 3，印刷 p.50 / PDF p.66 |
| FAO217-evaporative-cooling | 发布 | FAO Chapter 4，印刷 pp.70–71 / PDF pp.86–87 |
| FAO217-germination-medium | 发布，限定萌发期 | FAO Chapter 13，印刷 p.358 / PDF p.374 |
| CHOAB2019-design | 发布，限定摘要可核验范围 | 出版社摘要与 DOI 题录 |
| CHOAB2019-energy-balance | 保留草稿 | 与已有条目重叠，模型参数解释待结合完整章节细分 |
| GUZMAN2019-virtual-sensing | 发布 | 出版社 PDF pp.2–3，Sections 1–2 |
| GUZMAN2019-transfer-limit | 发布 | 出版社 PDF p.3，引言末段的研究限制 |
| CHEN2025-coupled-control | 保留草稿 | 摘要核对完成，控制算法细节待全文拆分，避免重复知识 |
| OGUNDELE2026-heterogeneity | 发布，限定模拟案例 | 期刊摘要空间分布段，不移用案例数值 |
| JIAO2020-canopy | 保留草稿 | 双膜日光温室/芹菜场景专属性强，待独立复核与场景适配 |
| JIAO2020-validation | 保留草稿 | 验证结论需结合完整试验边界与测点条件核对 |

FAO 内容逐段与[机构原文](https://www.fao.org/4/i3284e/i3284e.pdf)核对。虚拟传感器条目核对[出版社 PDF](https://mdpi-res.com/d_attachment/sensors/sensors-19-00060/article_deploy/sensors-19-00060.pdf)，案例核对[期刊原页](https://www.agroengineering.org/jae/article/view/1971)。Solar Energy 条目只引用[出版摘要可核验范围](https://www.sciencedirect.com/science/article/pii/S0038092X19308205)，不宣称已取得全部付费全文。

五篇 DOI 经 Crossref 官方元数据核对，返回 200，题名一致，所返回记录没有 `update-to` 或关系字段中的更新信号。本次检查**不能证明不存在任何撤稿/勘误**；没有以此为全部质量保证。保留草稿的论文也不因此被断言有误。官方核对摘要存于资料目录 `source-checks-v1.json`，完整本机记录在 `.local/assistant/knowledge-review/source-integrity.json`。

## 发布与版本追溯

正式文件：[v3 发布清单](../../knowledge/agri-temperature/releases/agri-temperature-qualitative-20261030-v3.json)。Qdrant 集合：`agri_temperature_qualitative_20261030_v3`，实有 8 点；早期 v1/v2 集合和清单保留以便对照，不覆盖已发布内容。

嵌入模型仍为 `BAAI/bge-small-zh-v1.5`，修订固定为 `7999e1d3359715c523056ef9478215996d62a620`。编码内容包含标题、正文及适用边界，策略为 `title_body_limits-v1`。发布和查询都核验服务返回的模型修订，防止同维数但不同向量空间混用。

v1 是无相似度门槛的基线；v2 用开发集校准查询门槛并把上下文限制为最多 3 条；v3 进一步收紧一条模拟案例的措辞。检索先检查发布状态、有效期和作物/阶段条件，再用**合格证据中的最高分**决定整条查询是否返回资料，防止已撤回或不适用的高分命中绕过门槛。

v3 发布内容摘要：`7e265d1b9a43340f074c3960bfb0b3b5747636ae04a51cbfcc3cd4c14443db96`。清单还保留原始草稿、审核记录、修订记录和父版本摘要。

## 评测设计与结果

[固定题集](../../knowledge/agri-temperature/benchmark-v1.json)共 28 问：开发集 8 个可回答、2 个不可回答；留出集 12 个可回答、6 个不可回答。题集和知识内容由同一助手设计/审校，尚未取得独立农业专家标注；留出问法仍与同一批知识主题相关，因此只是初步同语料评测。

题集在首次索引查询前固定。首次评测后发现低相关问题也会返回最近文本；阈值只从开发结果选择，没有按留出标签改动问题、答案或阈值。但留出结果已被查看，所以后续属于**同一留出集的对比复测，不是新盲测**。

查询门槛为开发集最高负例分数加微小余量：`0.58577787`。这只是本模型、本语料的初始门槛，不是置信度、普适事实门槛或针对其他嵌入模型的默认值。开发负例只有两个，须用更多独立问题检验泛化。

| 留出集指标 | 无门槛 v1 | 正式 v3 |
| --- | ---: | ---: |
| 可回答问题首位命中 | 10/12，83.3% | 10/12，83.3% |
| 可回答问题前三条命中 | 12/12，100% | 12/12，100% |
| 平均倒数排名 MRR | 0.9167 | 0.9167 |
| 不可回答查询返回无证据 | 0/6 | 5/6，83.3% |
| 返回引用的出处/版本元信息可定位 | 全部通过 | 全部通过 |

注意：前三条命中表示标注依据在结果中，不表示三条都相关，更不表示最终回答正确率 100%。引用元信息校验也不等同于模型已正确使用每条引用。

详细逐题结果与分数：[v1 基线](../../knowledge/agri-temperature/evaluations/retrieval-v1.json)、[v2 对照](../../knowledge/agri-temperature/evaluations/retrieval-v2.json)、[v3 正式结果](../../knowledge/agri-temperature/evaluations/retrieval-v3.json)。v3 此轮检索中位耗时约 0.46 秒；本机小样本顺序请求，不能当作并发容量或线上延迟承诺。

### 必须保留的失败案例

H15“现在棚内最热位置的准确坐标和温度是什么？”仍召回空间温差相关文献。文献**没有**这个棚的现场坐标与温度，因而该查询仍属于不可回答。已如实计为未正确拒绝的负例，没有删除或改成正例。

业务回答必须使用现场工具提供这类事实；工具缺失时说明不支持，不能拿相关文献代替。每条发布知识都带 `evidence_kind=qualitative`、使用限制和“不支持数值阈值”的标记；硬检查会拦截只凭定性文献生成带数值的温度主张。相似度与这些约束仍不能替代完整的语义复核。

本轮未调用 DeepSeek 评估最终生成答案，也没有证明模型拒答率、幻觉率或领域建议准确率。外部模型连接稳定性问题依然独立存在。

## 本机启用与复测

默认知识选择已切到 v3，私有配置位于 `.local/assistant/knowledge-active.json`；统一启动配置同步登记了正式清单与集合。环境变量优先于默认文件；部署包通过 `TFIELD_ASSISTANT_ACTIVE_KNOWLEDGE_FILE` 的绝对路径读取项目私有选择。已有旧进程需要重新加载新代码，本轮没有停止或重启已有训练/业务进程。

激活脚本校验评测通过标记、发布清单摘要、审核与修订摘要，并保留上一次私有选择。原始 12 条草稿状态不变，只有审核后生成的新版本中 8 条标为发布。

```powershell
# 重测当前正式索引；不需要重新写入
python backend/scripts/evaluate_agri_retrieval.py --version v3

# 明确需要重建当前同版索引时，按同 ID 幂等写入
python backend/scripts/evaluate_agri_retrieval.py --version v3 --index

# 评测结果与内容摘要通过后选择该版本
python backend/scripts/activate_assistant_knowledge.py --version v3
```

重新审核或改变内容时应创建新版本；不要覆盖 v1/v2/v3。重新生成基线报告会改变其摘要，不能用新报告去悄悄重造同名的既有 v2。当前后端回归测试 21 项通过，覆盖默认选择、环境优先级、模型修订不匹配、低相关过滤及定性文献不得转成数值处方等边界。

后续重点是扩大农业语料与独立评测问题、加强现场问题与知识问题的路由，并完成真实模型端到端引用与拒答验收。
