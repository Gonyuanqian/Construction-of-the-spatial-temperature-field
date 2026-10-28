# 棚式空间温度场重建系统

基于 **Vue 3 + Spring Boot + Python / FastAPI + Three.js** 的棚内温度场重建与可视化系统。结合棚内温湿度测点和棚外气象数据，完成数据检查、模型训练、空间构场和实时演示。

**项目状态：单机核心迁移已完成，训练与实时工作台持续完善中。本文更新于 2026-10-28。Java 业务服务版本：0.5.0。**

当前版本已完成从 Python 单后端到 **Spring Boot 业务后端 + Python 训练与计算服务** 的单机迁移。Spring Boot 在 **8080** 同时提供前端页面与 API，Python 在 **8503** 执行训练和温度场计算。数据集、模型、训练记录和实时会话均有明确的持久化与恢复方式。真实训练、保存、取消、非零帧恢复和自动播放已在独立环境联调。服务器运维与压力验收仍需按部署环境安排。详见 [部署交接](docs/development/05-deployment-and-acceptance.md)、[联调记录](docs/development/06-migration-acceptance-20261019.md) 和 [迁移计划](docs/development/04-spring-boot-python-migration.md)。

日常访问：[实时监测](http://127.0.0.1:8080/live) · [数据导入](http://127.0.0.1:8080/data) · [温度场构建](http://127.0.0.1:8080/field)。这些地址在完成本机配置并启动系统后可用。

新成员建议依次阅读：[当前进度](#1-当前进度) → [页面流程与数据边界](#2-两种模式与数据边界) → [快速启动](#3-快速启动) → [团队开发入口](#6-团队继续开发) → [最新验证结果](#7-构建与验证)。首次克隆后还需配置本机 MySQL、提供 XLSX 数据并建立模型；Git 中的标定 JSON 和界面参考图不能代替这些运行资料。

## 1. 当前进度

系统已形成“数据导入 → 模型训练 → 模型保存与选择 → 温度场查看”的主要流程，并提供独立数据源驱动的实时监测演示。

| 模块 | 当前状态 | 入口与说明 |
| --- | --- | --- |
| 数据导入与检查 | 已实现 | `/data`：文件导入、质量统计、拱形测点分布和每页 10 行的数据预览 |
| 模型训练 | 已实现 | `/train`：特征说明、分组参数面板、参数优选与取消、空间验证、训练诊断和模型保存；同一应用内支持跨页保持状态 |
| 空间温度场的构建 | 已实现 | `/field`：先选择模型并点击“开始构场”，再查看断面 / 三维、切换时刻；三维提供点位查询和剖切控制 |
| 模型库 | 已实现 | `/models`、`/models/:id`：列表与详情同屏，查看来源、验证与参数，显式选用工作区模型；入口位于训练模式左侧导航栏 |
| 实时监测 | 已实现演示流程 | `/live`：独立文件回放、断面 / 三维视图、三维立体态 / 切面态、环境参数、沿棚均温与视图控制 |
| 温度场智能助手 | 已预留导航，待开发 | 预留 `/assistant`；尚无问答页面、模型接入和问答接口 |
| 历史数据 | 已预留导航，待开发 | 预留 `/history`；尚无专用查询页面、历史归档和回放服务 |
| 系统设置 / 影响分析 | 尚未开放 | 导航占位，功能范围和接口有待后续确定 |

未开放的导航项处于禁用状态，预留地址尚未注册为页面。根路径 `/` 默认进入 `/data`。

### 本次迁移成果

- **业务后端**：Spring Boot 统一管理数据集、工作区、训练任务、模型库及实时会话；Python 保留模型训练、诊断与空间温度场计算。
- **任务与模型恢复**：训练请求和模型保存支持去重；完成结果可跨计算服务重启保存，运行中被中断的任务明确失败。
- **实时会话恢复**：固定源数据副本和模型，保存确认位置；恢复后暂停，重新准备成功后才切换到新会话。
- **统一部署**：提供 Windows 构建、启动、停止、状态查看和发布包回退入口；部署模式使用 8080，开发模式使用 5173。
- **联调交接**：补充真实训练、数值对照、浏览器检查、备份恢复及已知边界的记录，见 [联调结果](docs/development/06-migration-acceptance-20261019.md)。

### 最近完成的调整（截至 2026-10-28）

- **训练模式外壳**：使用冷浅灰背景、白色卡片和绿色强调色；模式切换并入标题栏，左侧导航加入图标、选中标记和模型库入口，减少正文顶部留白。
- **数据导入与检查**：重排文件导入区、四项质量统计、测点分布与数据预览；两张主卡片调整宽高比例并保持等高。预览按每页 10 行翻页；若接口只返回部分数据，明确显示预览行数与全量行数。
- **模型训练**：顶部展示特征，下方左右排列参数配置和验证结果，底部保留训练与保存入口。区分待优选、优选中、已完成、未保存和模型库历史记录；其他数据集的优选成绩不作为当前成绩展示。以桌面核心模块同屏为目标，较长结果在模块内滚动，窄屏改为纵向排列。
- **训练状态保持**：参数、任务进度、诊断结果和保存状态由应用工作区持有，同一应用内切页后继续保留；重新导入数据会清除旧上下文。
- **构场流程**：进入 `/field` 只读取模型列表，等待用户选择并点击“开始构场”；重新进入页面或更换选择后需要再次确认，避免自动使用旧模型构场。
- **模型库**：列表与详情同屏，补充来源、成品状态、空间验证和参数信息。查看详情与选用模型分开；“用于构场”会选用模型并进入构场页，仍需在构场页确认。
- **实时工作台**：完善标题、状态栏、查询标题、发光框线、透视网格、坐标指示轴和均温曲线的渐变填充；调整三栏间距与底部卡片高度。断面视图右侧按查询、环境参数、温度概览排列；隐藏滚动条外观，仍保留滚动能力。
- **实时三维展示**：默认立体态，右上角可切换为切面态；原有“展开调节”、剖切刀、棚体示意长度和视图控制保留。立体态连接有效网格单元的外表面，沿用同一份温度数据，不跨越未定义区域或无测量带补色。

以上代码已随提交 `5185514` 推送至 `main`。当前构建通过，但全量前端测试尚未全部通过，详见第 7 节；界面参考图不能视为当前版本的浏览器验收结果。

## 2. 两种模式与数据边界

### 训练模式

通过页面上传符合项目数据契约的 XLSX，完成训练与诊断，在模型支持的空间范围内重建温度场。训练结果可以命名并保存至 MySQL 模型库，再选择用于构场。

页面操作按以下顺序进行：

1. **导入与检查**：在 `/data` 选择文件并点击“导入数据”，核对时间范围、质量统计、测点位置和预览内容，再进入模型训练。
2. **参数优选**：在 `/train` 查看特征与参数配置，点击“参数优选”提交搜索任务。当前数据集没有匹配记录时，右侧显示等待提示；任务完成后显示空间验证成绩。页面会标明成绩来自未保存结果还是模型库记录。
3. **训练诊断**：点击“开始训练”运行当前参数的诊断，查看模型与基线对比、预测分布和残差图。它与参数搜索是两个操作；手动修改参数不会更新原优选成绩，需重新运行训练诊断查看效果。
4. **保存与选用**：给未保存结果命名并保存，在 `/models` 查看详情或显式选用。查看详情不会切换模型；仅保存参数的旧记录与已保存模型成品有不同提示。
5. **确认构场**：在 `/field` 下拉框选择可用模型，再点击“开始构场”。有了场以后才能切换断面 / 三维和时刻；更换模型会清除旧场，等待重新确认。不同数据来源的可用模型会显示“借来的”说明，应核对来源与适用范围。

训练页中的“空间选参组 / 空间留出组”属于测点空间验证划分，与后文 A／B／C 时间数据集划分不同。优选成绩、当前参数诊断和跨时段评估也不是同一类结果；模型库的跨时段评估入口目前尚未开放。

- 经过 Java 入口时，当前训练数据集选择保存在 MySQL 默认工作区中；Java 或 Python 重启后可按登记引用重新加载。文件保存在 `backend/configs/datasets/<dataset_id>/source.xlsx`，原文件名和旧签名单独登记。
- 直接访问 Python 8503 的旧入口仍使用内存选择，重启后需要重新导入；它与 Java 工作区相互独立。
- 单纯把数据集放入 `backend/`，不会自动成为页面的当前数据集。
- 训练与验证使用时间留出和既定的验证划分。当前时间切点为 `2026-07-27 12:00:00`，训练段位于切点之前。
- 训练任务与取消意图存入 MySQL；Java 重启后继续核对状态。已完成但未保存的结果暂存在磁盘，Python 重启后可重新读取；运行中的训练因 Python 重启中断时会明确失败，不自动重跑。
- 同一应用内切换路由会保留参数、优选任务与诊断；刷新或关闭浏览器后，诊断结果和未提交的手调状态不保证保留。已登记的优选任务按后端摘要恢复，页面不会因返回训练页而自动再次提交任务。
- 模型优先从保存的产物恢复；缺少可用产物或产物不兼容时，相关管线可能重新拟合。不能将“切换模型”理解为所有情况下都不发生计算。

### 实时模式

当前是**基于独立 XLSX 文件的留出数据回放演示**，尚未接入真实传感器或物联网数据流，也不提供未来温度预测。

| 文件 | 用途 |
| --- | --- |
| `backend/configs/live/train.xlsx` | 实时管线使用的训练段 |
| `backend/configs/live/live.xlsx` | 实时演示逐帧接入的数据段 |

交付样例包含 1,308 个时刻，按当前切点分成 1,164 个训练时刻和 144 个实时帧。帧数取决于源数据，不能套用于所有数据集。

自动播放每 **300 秒**推进一帧，并支持暂停和手动步进。前端每 5 秒检查状态，暂停时也检查服务是否重启；同一会话同一帧不重复取温度场。这不代表每 5 秒有新的测量数据。实时源由脚本手动生成，上传训练数据不会自动替换它。

经 Java 准备时，会复制两份源文件到 `backend/configs/live-sessions/<session_id>/`，记录数据摘要、模型和计算版本；后续更换源文件或模型库当前项不影响已有会话。Java 保存确认游标，Python 保存源副本与操作回执，管线对象仍在内存中。

Python 重启后点击“恢复实时源”，会使用原副本和模型重建到最近确认帧，完成后保持暂停。需要使用新数据或新模型时先暂停，再点“重新准备”；新会话成功后才替换当前会话。开始、暂停和下一帧携带操作编号，网络重试复用编号。这里保存的是会话及恢复资料，尚无历史数据页面、归档检索或真实设备接入。详见 [实时会话协议](docs/development/contracts/live-sessions-v1.md)。

| 操作 | 使用的数据和模型 | 完成后的进度 |
| --- | --- | --- |
| 恢复实时源 | 原会话保存的数据副本与绑定模型，用于计算服务重启后的恢复 | 回到最近确认帧，保持暂停 |
| 重新准备 | 当前配置的实时源文件与模型库当前选用的模型，创建新会话；需先暂停 | 从第 0 帧开始，保持暂停，再点击“开始”播放 |

实时页的“断面 / 三维”切换查看方式；三维画布右上角的“立体态 / 切面态”切换呈现方式。它们不重新选择模型或创建实时会话。“展开调节”中的剖切与示意长度仍独立生效。

### 温度场读数口径

- 可视化中的网格点与连续色面包含模型重建结果，不能全部解释为真实传感器实测值。
- 三维坐标查询吸附到最近网格点，应以返回坐标和出处说明为准。
- 拱外或场未定义的位置不返回有效温度；当前几何配置的最高测点为 1.10 m，其上的无测量带需按接口定义展示，不能补成真实温度。
- “拱外，无定义”指返回的网格点位于棚体拱形轮廓之外。棚体截面不是矩形，靠近两侧时可用高度更低；即使 x、z 分别落在坐标轴范围内，该组合也可能在拱线以上。它与拱内的“无测量带，不报数”需要区分。
- 棚体示意长度用于几何展示，不改变底层温度场；色标上下限也不等同于带位置的业务极值结论。
- 验证指标属于对应数据和验证划分，不能直接当作实时帧的现场误差。

## 3. 快速启动

### 环境与依赖

| 依赖 | 要求 / 用途 |
| --- | --- |
| Python | 3.10 及以上；运行 FastAPI 与核心计算库 |
| Java | 17 及以上；运行新增 Spring Boot 兼容接口服务 |
| Maven | 项目 Wrapper 固定 3.9.16，首次使用自动下载 |
| Node.js | `^20.19.0` 或 `>=22.12.0`，与当前 Vite 版本要求一致 |
| MySQL | 模型库持久化；默认连接本机 3306 端口 |
| XLSX 数据集 | 由使用者提供，仓库不包含原始数据和实时数据文件 |

以下命令以 PowerShell 为例；Python 依赖建议安装在项目虚拟环境中。

```powershell
git clone https://github.com/Gonyuanqian/Construction-of-the-spatial-temperature-field.git
cd Construction-of-the-spatial-temperature-field
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-api.txt
cd frontend
npm ci
cd ..
```

### 配置模型库

确保 MySQL 已启动，在 **Java 启动终端**设置连接信息。默认 Java 模式下 Python 通过内部接口读取模型；只有旧独立模式才由 Python 直接连接 MySQL。例如：

```powershell
$env:TFIELD_MYSQL_HOST = "127.0.0.1"
$env:TFIELD_MYSQL_PORT = "3306"
$env:TFIELD_MYSQL_USER = "your_user"
$env:TFIELD_MYSQL_PASSWORD = "your_password"
$env:TFIELD_MYSQL_DB = "tfield_models"
```

Java 使用 Flyway 管理模型、数据集、工作区、训练任务、实时会话、操作和迁移历史表，已有模型的 ID、标定包与成品保留。账号需具备相应权限。代码保留本机演示连接默认值，团队成员应通过环境变量配置自己的数据库。数据库记录、数据文件和模型产物不会随 Git 克隆自动迁移。

### 统一启动（Windows）

配置好数据库和运行环境后，在项目根目录执行：

```powershell
New-Item -ItemType Directory -Path .local -Force
if (-not (Test-Path .local/system.local.json)) {
    Copy-Item scripts/system.example.json .local/system.local.json
}
# 编辑本机配置，填写数据库、Java 等信息
# PythonExe 填写本项目 .venv\Scripts\python.exe 的绝对路径
.\scripts\system.ps1 Build
.\scripts\system.ps1 Start
.\scripts\system.ps1 Status
```

访问 [实时页面](http://127.0.0.1:8080/live) 或 [数据页面](http://127.0.0.1:8080/data)。部署模式运行发布包内的前端、Java 和 Python，不依赖前端开发服务；MySQL 需预先启动。停止使用 `Stop`，更新后使用 `Restart`，开发模式使用 `Start -Mode Dev`。重复启动、端口冲突、日志及回退方法见 [部署交接](docs/development/05-deployment-and-acceptance.md)。

### 手动开发：启动 Python

手动开发需要 **MySQL + Python + Java + 前端** 同时可用，其中后端包含 Python 计算服务和 Java 业务服务。先启动 MySQL，再打开下面三个终端；每个终端均从仓库根目录开始，保持进程运行。

第一个终端启动 Python。以下命令使用前面安装依赖的项目虚拟环境；Python 默认使用 Java 模型库，Java 地址可通过 `TFIELD_BUSINESS_URL` 修改：

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend --host 127.0.0.1 --port 8503
```

### 手动开发：启动 Java

在仓库根目录打开第二个终端，按“配置模型库”一节设置该终端的数据库环境变量，Python 服务启动后执行：

```powershell
cd backend-java
.\mvnw.cmd '-Dmaven.test.skip=true' package
java -Dfile.encoding=UTF-8 -jar target/tfield-business-0.5.0.jar
```

Java 在 8080 提供业务接口与模型读写，Python 在 8503 执行训练、模型加载和计算。双方访问同一数据目录、使用相同内部凭据；本机从项目目录启动时由 Java 自动创建凭据。默认 Python 模式不直接写数据库，独立部署的配置见 Java 服务说明。

已有对应版本的 JAR 时可省略 Maven 打包；更新 Java 代码后需重新打包。Maven 命令跳过了测试，仅用于生成开发启动文件。

### 手动开发：启动前端

在仓库根目录打开第三个终端：

```powershell
cd frontend
npm run dev -- --host 127.0.0.1
```

手动开发时打开 [数据导入](http://127.0.0.1:5173/data)、[模型训练](http://127.0.0.1:5173/train) 或 [实时监测](http://127.0.0.1:5173/live)。修改前端通常由 Vite 自动更新；8080 上的部署页面需要重新 Build 并 Restart 才会使用新界面。

手动启动的三个进程分别在各自终端按 `Ctrl+C` 停止，再执行同一启动命令即可重启。由 `system.ps1` 管理的服务使用该脚本的 `Stop` / `Restart`；不要同时再启动一套相同端口的进程。

| 地址 | 用途 |
| --- | --- |
| [统一部署入口](http://127.0.0.1:8080/live) | Java 同源提供页面和 API，日常推荐入口 |
| [数据导入页](http://127.0.0.1:8080/data) | 部署模式：首次进入与训练数据导入 |
| [温度场构建页](http://127.0.0.1:8080/field) | 部署模式：断面和三维查看 |
| [实时监测页](http://127.0.0.1:8080/live) | 部署模式：实时演示工作台 |
| [开发模式入口](http://127.0.0.1:5173/data) | 使用 `Start -Mode Dev` 或手动启动 Vite 后访问 |
| [Python API 文档](http://127.0.0.1:8503/docs) | 计算接口参数与响应结构；Java 新增业务接口见版本协议文档 |
| [健康检查](http://127.0.0.1:8503/api/health) | 确认 API 进程可访问 |
| [业务服务状态](http://127.0.0.1:8080/ops/health) | 确认 Java 可以连接 MySQL 与 Python |

开发模式前端固定使用 5173 端口，并将 `/api` 默认代理至 Java 8080；部署模式直接使用 8080。`TFIELD_API_TARGET` 可覆盖开发代理。模型写入权已切换到 Java，回退旧 Python 模式需要暂停业务、备份并设为 `TFIELD_MODEL_STORE_MODE=legacy`，不能只改代理地址。`/api/health` 只表示 Python 存活；`/ops/health` 同时检查数据库、Python 与训练、实时内部协议。

### 首次使用流程

1. 进入 `/data`，上传符合项目结构的 `.xlsx`，检查数据和测点信息。
2. 进入 `/train`，查看特征构造、执行参数优选并等待完成，再按需要点击“开始训练”查看诊断。
3. 保存一份具名模型到模型库，查看来源、成品状态与兼容性，按需要选用。
4. 进入 `/field`，先选择模型并点击“开始构场”，再查看断面与三维；三维视图支持选点、坐标查询和剖切。
5. 如需查看实时监测，按下一节准备独立数据源，再进入 `/live`。

## 4. 数据准备

### 训练数据导入

页面接受项目约定的 XLSX 工作簿，当前上传上限为 **32 MiB**。任意列名的 Excel 文件不能直接使用。

工作簿约定包括“建模对齐数据”“插值标记”“测点字典”等工作表，时间字段为 `timestamp`，并包含匹配配置的棚内温湿度测点与背景气象字段。“处理说明”“字段说明”用于描述数据来源与含义。

具体结构以 [字段与几何配置](backend/src/tfield/config.py) 和 [数据加载实现](backend/src/tfield/data/loader.py) 为准。Java 入口的上传版本保存在 `backend/configs/datasets/<UUID>/source.xlsx`；旧 Python 入口仍使用 `backend/configs/uploads/`，这些文件不进入 Git。

### 泛化实验数据划分

已制定 A／B／C 时间划分：**A 训练集 576 个时刻、B 跨时段验证集 288 个时刻、C 最终测试集 444 个时刻**。本机导出目录为 `outputs/generalization-20261021/`，包含三个 XLSX、文件摘要和数据核对记录；数据文件不进入 Git。划分规则见 [generalization-split-v1.json](backend/configs/generalization-split-v1.json)，使用方法与数据限制见 [泛化实验数据说明](docs/development/07-generalization-datasets.md)。

本阶段完成数据划分与用途标记，冻结模型评估入口尚未实现。B／C 的温度值均为源文件已经线性对齐的值；上传接口目前不强制实验角色，勿将 B／C 上传后重新训练并作为独立测试结果。

### 生成实时演示数据

在仓库根目录执行；`--src` 指向手头的完整数据集：

```powershell
.\.venv\Scripts\python.exe backend/scripts/make_live_source.py --src "D:\data\完整数据集.xlsx"
```

不传 `--src` 时，脚本默认读取：

```text
backend/人参棚_多棚温湿度_气象时间对齐数据集.xlsx
```

脚本会修复时间轴，再按当前切点生成 `backend/configs/live/train.xlsx` 与 `live.xlsx`；切点两侧均需有数据。更换源数据后需手动重新生成，生成会更新这两份文件。等待生成完成，再在实时页暂停并点击“重新准备”建立新会话；源生成与新会话准备应串行进行。已有会话继续使用原副本，恢复原会话不会自动改用新文件。

进入实时页前，还需在模型库中准备并选择可用的兼容模型。仅有两份实时文件不等于已有可用模型；仅有 `configs/bundle_*.json` 也不等于已写入 MySQL 模型库。

## 5. 技术结构

```text
.
├── backend-java/            # Spring Boot 业务管理、兼容接口与前端静态托管
├── backend/
│   ├── api/                 # FastAPI 路由、数据缓存、模型库与实时管线
│   ├── src/tfield/          # 数据处理、特征、训练、验证、温度场重建
│   ├── scripts/             # 标定、实时源生成及维护工具
│   ├── configs/             # 标定包、上传文件与本机实时数据
│   ├── tests/               # 后端测试
│   └── requirements-api.txt # Web 服务及核心计算依赖
├── frontend/
│   ├── src/views/           # 数据、训练、构场、模型库、实时页面
│   ├── src/components/      # 通用组件
│   ├── src/composables/     # 数据集上下文、跨页训练工作区、异步请求与任务轮询
│   ├── src/scene/           # Three.js 场景与三维交互
│   ├── src/design/          # 设计令牌、文案、图标与规范守卫
│   └── src/router/          # 当前开放页面的路由
├── scripts/                # 统一部署入口及本机配置样例
└── docs/development/        # 团队开发、迁移、部署与联调交接文档
```

- **前端**：Vue 3、TypeScript、Vue Router、Vite；ECharts 展示曲线与诊断，Three.js 展示三维温度场。
- **Java 业务服务**：Spring Boot 3.5.16、JDBC、Flyway；托管前端，管理数据集、工作区、训练记录、模型保存事务、实时会话与当前选择，兼容转发计算接口。
- **Python 后端**：FastAPI 接收明确任务与模型引用；`tfield` 承担数据处理、训练和温度场计算，使用 NumPy、pandas、scikit-learn、XGBoost 等。
- **持久化**：MySQL 保存模型库、数据集、工作区、训练任务、实时会话与操作记录。未保存训练结果位于 Python 的 `configs/training-jobs/`；实时源副本与回执位于 `configs/live-sessions/`。管线缓存和执行线程仍在内存中；实时重启恢复以 Java 最近确认游标为准。

### 主要接口

以下路径均带 `/api` 前缀，详细参数以运行中的 `/docs` 为准。

| 类别 | 主要接口 |
| --- | --- |
| 数据 | `GET /dataset`、`POST /dataset/upload`、`GET /dataset/timeseries`、`GET /dataset/layer-timeheight`、`GET /dataset/preview` |
| 特征与标定 | `GET /features`、`GET /calibration`、`POST /calibration/diagnostics` |
| 训练任务 | `POST /calibration/jobs`、`GET /calibration/jobs/{job_id}`、`DELETE /calibration/jobs/{job_id}` |
| 温度场 | `GET /field/arch`、`GET /field/sections`、`GET /field/curve`、`GET /field/compare`、`GET /field/volume` |
| 模型库 | `GET /models`、`GET /models/{model_id}`、`POST /models`、`POST /models/{model_id}/current` |
| 实时演示 | `GET /live/status`、`POST /live/prepare`、`POST /live/start`、`POST /live/pause`、`POST /live/next`、`GET /live/frame/{n}`、`GET /live/volume/{n}` |
| 新建实时会话 | `POST /live/sessions`：使用当前源文件与所选模型重新准备；已有会话需先暂停 |

`DELETE` 训练任务接口用于请求取消任务。实时帧查询受当前播放进度约束，不能代替任意历史时间查询接口。

## 6. 团队继续开发

请先阅读共同约定，再进入对应页面文档。功能清单和接口草案用于讨论，可以结合实际需求调整；颜色、字体、外壳、图标、组件和数据口径应统一维护。

| 文档 | 关注内容 |
| --- | --- |
| [共同设计与开发约定](docs/development/00-shared-ui-guidelines.md) | 共享主题、布局外壳、组件复用、路由和跨页上下文 |
| [实时监测开发文档](docs/development/01-live-monitoring.md) | 已实现能力、布局方向、后续优化与接入事项 |
| [温度场智能助手开发文档](docs/development/02-temperature-field-assistant.md) | 问答范围、数据依据、交互组织和温度场联动建议 |
| [历史数据开发文档](docs/development/03-history-data.md) | 查询、归档、回放、对比和来源追溯建议 |
| [Spring Boot 与 Python 迁移计划](docs/development/04-spring-boot-python-migration.md) | 分工、阶段记录、兼容与回退；单机核心迁移与联调已完成 |
| [统一部署与联调交接](docs/development/05-deployment-and-acceptance.md) | 单机启动、版本包、日志、配置与回退 |
| [迁移联调记录](docs/development/06-migration-acceptance-20261019.md) | 真实训练、模型、实时恢复、浏览器与回归结果及边界 |
| [泛化实验数据说明](docs/development/07-generalization-datasets.md) | A／B／C 时间划分、数据质量、实验角色与评估限制 |
| [训练与模型协议](docs/development/contracts/training-models-v1.md) | 优选任务、幂等提交、模型保存和前端跨页状态 |
| [实时会话协议](docs/development/contracts/live-sessions-v1.md) | 会话副本、确认游标、恢复、新建和操作去重 |

### 当前代码入口

| 修改范围 | 优先查看 |
| --- | --- |
| 应用外壳、标题和导航 | `frontend/src/App.vue`、`components/TitleBar.vue`、`components/NavRail.vue` |
| 数据导入、测点图与预览 | `frontend/src/views/DataView.vue`、`charts/options/sensorLayout.ts` |
| 训练布局、参数与跨页状态 | `frontend/src/views/TrainView.vue`、`components/ParamPanel.vue`、`composables/useTrainingWorkspace.ts`、`composables/useJob.ts` |
| 模型库查看和选用 | `frontend/src/views/ModelsView.vue`、`api/models.ts` |
| 选模型后构场 | `frontend/src/views/FieldView.vue` |
| 实时布局、状态条和均温概览 | `frontend/src/views/LiveView.vue`、`components/OverviewStrip.vue`、`charts/options/liveMeanCurve.ts` |
| 三维查询、调节与呈现 | `frontend/src/scene/VolumeView.vue`、`scene/VolumeScene.vue`、`scene/solidSurface.ts` |
| 主题与共用文案 | `frontend/src/design/tokens.css`、`design/base.css`、`design/icons.ts`、`design/copy.ts` |

表中省略前缀的前端路径均相对于 `frontend/src/`。跨页训练状态应继续由工作区管理，避免页面重新挂载时重复提交任务；展示层不要自行重算温度、均温、验证指标或改变 `null` 的含义。

### 风格与实现约定

- 实时工作台沿用**深蓝背景、青色强调、亮蓝交互**；训练模式使用**冷浅灰背景、白色卡片、深蓝文字与绿色强调**。助手和历史页接入时复用实时工作台外壳。
- 颜色、字体、间距与圆角引用 `frontend/src/design/tokens.css`；图标与文案沿用 `design/icons.ts`、`design/copy.ts`。
- 卡片、图表和三维能力优先复用现有组件，避免页面各自建立一套视觉规则。
- 新增页面需同步处理路由和工作台主题：当前外壳用 `/live` 路径判断实时模式，仅添加助手或历史路由还不足以复用外壳。
- 显示真实空态、错误和数据出处；不要用演示值填充缺失结果，也不要把未实现的能力写成已经上线。

后续可优先讨论：真实实时源接入、历史状态持久化、基于系统数据的只读问答及证据展示。这些方向尚未全部实现，也未固定开发排期。

## 7. 构建与验证

### 最新检查（2026-10-28，代码基线 `5185514`）

| 检查 | 结果 |
| --- | --- |
| `npm run build` | 通过，包含 TypeScript 检查和 Vite 打包；有大体积产物提示 |
| `npm test -- --pool=threads --maxWorkers=2` | **545 项通过、56 项失败，共 601 项**；49 个测试文件通过、10 个失败，另有 101 条未处理运行错误 |
| `git diff --check` | 推送前通过 |
| 本轮 Java / Python 回归及浏览器验收 | 未重新执行，不能沿用历史结果视为本轮通过 |

当前测试存在实时页独立挂载缺少 `#rail-extra` 目标、设计守卫仍使用旧标题 / 导航 / 阴影约束等问题；部分输出还包含 Vue 更新异常。上述是已观察到的失败线索，尚未完成逐项归因，不能将全部失败直接归为过期测试。后续应核对新交互与测试约束，保留数值、任务恢复和选点语义检查，再补充浏览器中的布局、WebGL 拾取及模式切换验收。

### 历史验收（2026-10-19）

迁移至 0.5.0 时，曾在独立数据库和文件目录完成真实 40 次参数搜索、结果跨重启保存、重复保存去重、模型切换、上传与拒绝、取消、计算失联和重启失败、实时非零帧恢复、步进去重、真实 300 秒自动推进和版本包回退。该次 45 项 HTTP 检查、9 项浏览器检查及 10 组 Java / Python 载荷对照通过；前端 583 项测试通过，后端非 slow 回归覆盖 507 项，其中一次数据库连接超时用例单独重跑通过，104 项 slow 测试未运行。详见 [历史联调记录](docs/development/06-migration-acceptance-20261019.md)。这些结果属于当时版本，不代表当前版本的全量验收。

### 前端

```powershell
cd frontend
npm run build
npm test -- --pool=threads --maxWorkers=2
```

全量前端测试中有构建产物相关检查，建议先完成构建，构建和测试串行执行。上面的线程池命令是在本机实际使用的方式，`npm test` 仍是默认入口。数值与组件测试之外，涉及实际 WebGL 渲染、拾取和布局的改动还应使用浏览器检查。

### 后端

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q -m "not slow"
```

原 Python 测试套件针对旧接口与 SQL 存储。运行前设置 `TFIELD_MODEL_STORE_MODE=legacy` 并使用独立测试数据库；`python -m pytest -q` 包含耗时较长的计算用例。数据库测试默认使用 `tfield_models_test`，会清理测试表，不要连接正在使用的业务库。这些用例不代替新 Java 任务与模型链路的联调验收。

### 原 Python 服务运行构建产物

使用旧模式前需按前文完成备份与模式配置。在仓库根目录构建前端，再启动后端：

```powershell
cd frontend
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn api.main:app --app-dir backend --host 127.0.0.1 --port 8503
```

后端可托管 `frontend/dist/` 并处理前端路由回退，浏览器访问 [构建后的系统](http://127.0.0.1:8503/data)。静态目录在后端启动时挂载；首次构建前已经运行的后端需重启。

这是原有的 Python 合并托管方式。当前默认通过统一部署入口由 Java 托管前端并管理业务，推荐使用前文 `scripts/system.ps1`；旧方式不会继承 Java 的业务状态管理。

## 8. 常见情况

| 现象 | 处理方式 |
| --- | --- |
| 重启后提示未导入数据 | Java 入口检查工作区、MySQL 与文件存储配置；直连 Python 旧入口需重新上传 |
| 模型列表失败或保存失败 | 检查 MySQL 服务、连接环境变量和建库建表权限 |
| 前端无法连接后端 | 检查 Java 8080、Python 8503 是否均已启动，或检查前端代理目标 |
| 实时模式提示缺少源文件 | 手动运行实时源生成脚本，检查两份 XLSX 和兼容模型 |
| 导入新训练数据后实时页没变化 | 两种模式的数据源独立；按需重新生成实时文件，生成完毕后暂停并“重新准备” |
| 实时页提示恢复 | 点击“恢复实时源”，按原副本和模型重建到确认帧；副本缺失或版本改变时需修复存储或重新准备新会话 |
| 进入构场页没有立即显示温度场 | 当前需先选择模型并点击“开始构场”；仅查看模型库详情不会自动构场 |
| 训练页显示等待参数优选完成 | 当前数据集没有匹配的优选记录；运行“参数优选”并等待完成，不能用其他数据集成绩代替 |
| 手调参数后优选成绩没有改变 | 右侧保留原优选记录；点击“开始训练”查看当前参数诊断，原表不会随滑块实时重算 |
| 选点提示“拱外，无定义” | 查询返回点在拱形截面外，通常位于两侧拱线以上；调整到棚体轮廓内，并核对吸附后的坐标 |
| 源码已更新，但 8080 页面仍是旧样式 | 8080 使用构建产物；统一入口重新 Build / Restart，开发调试改用 5173 |
| 助手 / 历史 / 设置入口不能点击 | 当前为规划占位，尚未开放页面 |
| 8080 能打开接口但打不开界面 | 用统一入口 Build 后 Start / Restart；手动托管时检查 `TFIELD_FRONTEND_DIST` 是否指向有效构建目录 |
| 8503 能打开接口但打不开界面 | 日常使用 8080；原 Python 托管方式需生成 `frontend/dist/` 后重启 |
| 5173 端口已被占用 | 检查已有前端进程；当前开发配置不会自动换到其他端口 |

## 9. 仓库维护

数据集、上传文件、实时 XLSX、构建产物、依赖目录及本机凭据不应提交。提交前确认代码、测试、README 和开发文档的状态说明一致；对外共享模型库需另行安排数据库与产物迁移。

`outputs/` 中已提交的 PNG 是界面参考资料；`outputs/generalization-*/` 与 `outputs/model-evaluation-*/` 中的数据子集、实验结果和评估归档按 `.gitignore` 留在本机。新成员克隆后不会获得这些归档、MySQL 内容、上传文件或运行会话，需另行交接。`backend/configs/bundle_*.json` 按现有约定提交，但不等于完整模型库备份或已保存的模型成品。

问题与建议可提交至 [GitHub Issues](https://github.com/Gonyuanqian/Construction-of-the-spatial-temperature-field/issues)。仓库目前未包含 `LICENSE` 文件。
