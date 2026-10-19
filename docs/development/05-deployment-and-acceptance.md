# 统一部署与联调交接

更新：2026-10-19。业务服务 0.5.0。当前部署入口面向 Windows、单机、单工作区；Java 提供页面和 API，Python 承担计算，MySQL 单独运行。

## 1. 启动结构

```text
浏览器 http://127.0.0.1:8080
  └─ Java：前端静态资源、页面路由、业务 API
       ├─ MySQL：模型、数据集、工作区、训练和实时记录
       └─ Python http://127.0.0.1:8503：训练、诊断、温度场与实时管线
```

部署模式不需要 Vite。开发模式使用 5173，由 Vite 代理 Java。MySQL 不由脚本安装、启动或停止。接口、静态文件与页面路由分别处理；刷新 `/field`、`/live` 等页面正常，未知 `/api` 和缺失资源保持错误响应。

## 2. 首次准备

安装 Java 17、Python 3.10+、Node.js（版本见主 README）并准备 MySQL。Maven Wrapper 固定版本，首次构建需要下载。

在项目根目录运行：

```powershell
python -m pip install -r backend/requirements-api.txt
cd frontend
npm ci
cd ..
New-Item -ItemType Directory -Path .local -Force
Copy-Item scripts/system.example.json .local/system.local.json
```

编辑 `.local/system.local.json`，填写自己的数据库配置。`PythonExe`、`JavaExe`、`NpmExe`、`NodeExe` 可以是 PATH 中的命令，也可以是绝对路径；建议指定实际使用的 Python 环境和 Java 17。配置示例中的数据库用户名、密码需要替换。配置文件和运行状态均被 Git 忽略。

可选构建配置：`MavenExe`、`MavenSettings`、`MavenRepository`，分别覆盖 Maven、settings.xml 和依赖缓存的绝对路径。未指定时使用项目 Wrapper。

脚本不自动安装 Python / Node 依赖，也不升级数据库服务器。

## 3. 统一命令

```powershell
# 构建前端、Java，复制 Python 源码，生成发布包
.\scripts\system.ps1 Build

# 启动部署模式，访问 http://127.0.0.1:8080/live
.\scripts\system.ps1 Start
.\scripts\system.ps1 Status

# 暂停播放、核对业务后停止；保留数据库和业务文件
.\scripts\system.ps1 Stop

# 构建新版本后切换
.\scripts\system.ps1 Restart

# 开发模式：页面 5173，API 8080，使用当前源码
.\scripts\system.ps1 Start -Mode Dev
```

从其他目录调用时使用脚本完整路径；配置文件可通过 `-Config <路径>` 指定。脚本只管理其记录的进程，停止前核对进程启动时间和命令行标记；端口被其他程序占用时拒绝启动，不自动终止旧服务。重复 Start 不创建第二套进程，切换模式、配置或版本应使用 Stop / Restart。

如果电脑限制运行本地 PowerShell 脚本，可以仅为本次调用指定执行策略：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\system.ps1 Start`。不需要修改全局执行策略。

普通 Stop / Restart 会拒绝中断正在运行的训练或未确认准备。完成或取消训练后再操作；失联服务确需中断时可显式使用 `Stop -Force` 或 `Restart -Force`。Force 仍会核对进程身份，不能停止其他程序。未保存的已完成结果保留在暂存目录；运行线程不能跨重启续接。

## 4. 发布包和持久文件

Build 在 `.local/releases/<时间>/` 生成：

| 内容 | 说明 |
| --- | --- |
| `business.jar` | 固定构建的 Java 服务 |
| `frontend/` | 固定构建的 HTML、JS、CSS |
| `backend/api/`、`backend/src/` | 本次发布的 Python 源码 |
| Python requirements / pyproject | 依赖声明 |
| `python-environment.txt` | 构建时已安装依赖的版本清单，不包含凭据 |
| `manifest.json` | 文件摘要、业务版本、来源提交及工作区是否有未提交修改 |

Start 在启动前核对文件摘要；部署模式运行发布包内的 Python 代码与前端。数据库、源 XLSX、已保存模型、上传数据、实时会话和凭据不进入发布包。构建不会自动更改当前运行版本。

默认持久位置仍是项目 `backend/configs/` 下的 `datasets`、`training-jobs`、`live-sessions` 与 `live`，凭据位于 `.local/service-token`。这些绝对路径通过环境变量传给服务，避免每次发布产生一份新的业务数据。

| 环境变量（可放入配置文件 Environment） | 用途 |
| --- | --- |
| `TFIELD_JAVA_PORT` / `TFIELD_PYTHON_PORT` | 默认 8080 / 8503 |
| `TFIELD_DATASET_STORAGE_ROOT` | 数据版本目录，双方一致 |
| `TFIELD_TRAINING_ROOT` | Python 训练暂存目录 |
| `TFIELD_LIVE_SESSION_ROOT` | Python 实时源副本与回执目录 |
| `TFIELD_LIVE_SOURCE_ROOT` | 生成好的 `train.xlsx` 和 `live.xlsx` 所在目录 |
| `TFIELD_INTERNAL_TOKEN_FILE` | 共享内部凭据文件 |
| `TFIELD_FRONTEND_DIST` | 手动启动 Java 时指定已构建的前端；部署脚本自动配置 |

覆盖目录使用绝对路径。脚本执行结束会恢复调用终端的环境变量，避免不同配置之间串用数据库或文件目录。运行进程各自继承自己的配置。

`.local/current-release.json` 指向最近构建包，`.local/system-processes.json` 记录当前服务；日志在 `.local/runtime/<时间>-unified/`。使用 Status 查看真实地址、进程和日志位置。

## 5. 更新和回退

1. 结束或取消训练，暂停实时、上传和模型写入，等待操作确认；先备份。
2. 执行 Build，再 Restart；业务表按 Flyway 增量迁移，不能修改已执行迁移文件。
3. 核对 `/ops/health`，检查当前数据集、模型与实时会话。Python 重启后点击“恢复实时源”，恢复到确认帧且保持暂停。
4. 若需退回已保留的包：

```powershell
.\scripts\system.ps1 Restart -Release "C:\项目路径\.local\releases\上一发布目录"
```

回退前确认旧代码支持当前数据库结构和 Python 依赖。发布包保留源码及依赖清单，但不自带独立 Python 虚拟环境；依赖变化后的代码回退需同时恢复兼容环境。不能把任意旧版本都视为可直接回退。

本轮实际演练了两个 0.5.0 发布包间的回退和恢复，数据集、已保存模型及实时会话位置均保留。此记录不证明 0.3.0 等旧业务协议可以直接承接新状态。

## 6. 备份与恢复演练

```powershell
python backend/scripts/capture_migration_baseline.py --include-model-store
```

备份需要对应时点的 MySQL 表、登记文件、训练结果及会话副本。项目默认目录由工具收集，外置目录另行备份；内部凭据独立提供。

恢复到新空库：先 `model-store.sql`，再 `dataset-workspace-store.sql`；按原 UUID 恢复目录，配置共享凭据和新库后启动。不要把 SQL 导入正在使用的库。实时管线重新构建，运行中的训练不能续接。数据库客户端执行脚本时应使用真正的 SQL 文件导入功能，不应简单按分号切分包含注释的脚本。

本轮从升级前快照恢复到了独立新库，包含原 1 条模型、2 个数据版本、工作区与实时会话；已用恢复后的文件和模型走通计算与实时恢复。演练不会向用户原库写入联调记录。

## 7. 可重复联调

联调环境必须使用独立数据库、数据 / 训练 / 实时目录、凭据及端口。示例端口 18080 / 18503。Java 配置 `TFIELD_ACCEPTANCE_MODE=true` 和独有 `TFIELD_DEPLOYMENT_ID`；日常系统保持 false。测试脚本检查这两个值后才允许写入。

```powershell
# 在独立环境运行完整真实训练并保存；按实际目录修改参数
python backend/scripts/acceptance_flow.py --base-url http://127.0.0.1:18080 --deployment-id your-acceptance-id --report .local/acceptance/report.json --phase train
```

该脚本还提供 `model --job UUID`（接续已完成训练）、`data --source 文件.xlsx`、`web`、`live`、`cancel`、`interrupt-start`、`outage`、`interrupt-check`、`recover`、`auto-start`、`auto-check` 阶段。报告在多个阶段间共享上下文，按如下顺序安排：

1. 真实训练完成，重启计算服务后以 model 阶段保存，确认未保存结果可恢复。
2. data 检查上传、无效文件与数据版本切回；web 检查页面刷新和错误路径。
3. live 检查帧一致性、暂停与去重；cancel 检查互斥和协作取消。
4. interrupt-start 后仅中断独立计算进程；outage 确认失联状态，再启动服务，用 interrupt-check 和 recover 核对失败终态与原实时帧恢复。
5. auto-start 后实际等待至少 301 秒，再 auto-check；没有加速播放间隔。

脚本会创建联调模型和会话，保留供核对；同一报告不是任意顺序可重复运行的清理工具。再次从头联调建议新建独立环境与报告。

`compare_compute_paths.py` 使用独立环境的凭据文件比较 Java 与 Python 查询，覆盖数据、曲线、断面、三维和真实诊断，记录简单耗时样本。冷计算和热缓存调用分别记录，不能将先后两次调用解释为公平的冷启动性能比较。

可选安装 Playwright 后，`browser_acceptance.py --base-url 地址 --output 目录` 使用本机 Chrome 无头浏览器检查三维、坐标查询占位、布局、滑块及页面刷新，并输出截图。它不执行训练或保存模型。软件 WebGL 的结果不代表所有实体显卡和浏览器都已验证。

## 8. 本轮验收记录与边界

详见 [2026-10-19 联调记录](06-migration-acceptance-20261019.md)。本轮是单机功能联调和部署切换，未覆盖所有断电窗口、损坏产物、并发压力及硬件组合。多实例调度、用户权限、HTTPS、系统服务安装、自动重启和集中监控仍需按实际服务器环境安排。
