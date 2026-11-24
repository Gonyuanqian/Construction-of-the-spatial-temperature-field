# AgriSeek 四阶段分析过程

更新：2026-10-31。界面在最终回答上方提供可折叠的「分析过程」，四个阶段为需求解析、数据获取、对比分析、得出结论。

## 输出与职责

Harness 根据实际路由、工具返回和候选检查写入公开执行摘要。模型仍通过 `finish_answer` 提交带证据的候选；原有数值检查、至少两轮候选检查、最多六轮循环与取消保护继续生效。新增记录不占模型上下文，不增加模型调用次数。

DeepSeek 的思考模式与工具调用是独立的协议能力，参见[官方说明](https://api-docs.deepseek.com/guides/thinking_mode/)。本次保留现有模型模式，公开记录使用工具结果及检查状态，不向前端透传或持久化模型的 `reasoning_content`，也不把原始提示词、供应商错误内容写进过程面板。

## 后端结构

`POST /api/assistant/runs` 建立任务时就返回 `analysis`。Java 原有代理透传 JSON，无需新增接口或数据库表。Python 将记录保存在既有任务 JSON 中，`GET /api/assistant/runs/{id}` 返回最新阶段；前端沿用一秒轮询，运行中自动展开，结束后可再次展开查看。历史任务没有该字段时保持原显示，不补造记录。

以下仅为结构示例，温度数值来自独立测试夹具：

```json
{
  "status": "running",
  "analysis": {
    "version": 1,
    "kind": "execution_summary",
    "started_at": 100,
    "finished_at": null,
    "elapsed_ms": 2300,
    "steps": [
      {"id":"intent","title":"需求解析","status":"completed","summary":"查询固定快照中的现场温度事实。","items":[]},
      {"id":"data","title":"数据获取","status":"completed","summary":"已从固定快照取得重建网格结果。","items":[{"text":"有效网格最高温：28.00 °C。","tool":"find_temperature_extrema","evidence_ids":["F:maximum:fixture"]}]},
      {"id":"comparison","title":"对比分析","status":"running","summary":"正在核验数值、引用与统计口径；本题无需农业标准对比。","items":[]},
      {"id":"conclusion","title":"得出结论","status":"pending","summary":"等待执行。","items":[]}
    ]
  }
}
```

状态包括 `pending/running/completed/blocked/skipped/failed/cancelled/interrupted`。阶段可以因补证而重新进入运行中，以反映实际工具循环；不会人为延时播放动画。每阶段最多保留八条去重后的简明记录。`started_at/finished_at` 为 Unix 秒，`elapsed_ms` 为实际记录时长；重启中断停留在最后可确认的记录时间。

## 内容边界

- 需求解析：显示问题类型、所需工具；缺坐标、缺区域或不支持的能力如实说明。
- 数据获取：显示固定回放的时刻、帧、实际模型、工具名称、返回温度与位置；重建网格、回放测点分别标注。通用知识问答不声称查询了现场传感器。
- 对比分析：显示实际检索到的条目、出处、引用编号和候选检查进度。目前已发布资料以定性机理为主，明确说明没有执行作物数值阈值或「专家标准模型」对比。没有知识依据时不给出虚构阈值。
- 得出结论：只有最终候选通过检查才标记完成。部分结果标记未完成，并保留工具确认的事实；取消、服务重启、超时与执行失败均关闭进行中阶段，迟到结果不能覆盖取消。

## 验证入口

后端：`python -m pytest tests/test_assistant_analysis.py tests/test_assistant.py tests/test_assistant_field_tools.py tests/test_volume_sample.py -q`（在 backend 目录）。

前端：`npm test -- src/components/AssistantAnalysis.test.ts src/views/AssistantView.test.ts src/App.test.ts`（在 frontend 目录）。

测试覆盖首次模型请求前就可读的过程记录、真实工具数值、定性资料来源、无数据早退、模型连接失败、取消冻结、重启中断，以及前端折叠/耗时和文本安全渲染。供应商可用性与农艺答案质量需要另行评测，过程面板不会将失败任务显示为成功。

本轮上述后端测试 66 项、前端相关测试 27 项通过，前端和 Java 打包通过。实际页面以「空气温度能代表叶片温度吗？」完成一次真实模型问答，约 16 秒、两次候选检查，四个阶段均完成，回答使用 FAO 定性条目。另有 CLI 真实测试出现连接中断或候选执行失败，现场题保留已确认数值并标记部分完成，知识题不发布答案；不能据页面单次成功宣称模型稳定性或领域准确率已验收。本机验收摘要保存在忽略目录 `.local/assistant/analysis-acceptance-20261031.json`。
