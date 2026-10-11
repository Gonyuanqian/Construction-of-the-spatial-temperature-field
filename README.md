# 棚式空间温度场重建系统

FastAPI 后端 + Vue 3 前端。这个项目做的是**棚式空间温度场的构建** —— 棚里只有
几个测点，要把整个棚（每一层、每一个位置）的温度都算出来、并且看得见。

为此做了两条路：

- **训练模式** —— 拿一份以往的温湿度与气象数据集训练出模型，**在这份数据集上**
  把整个棚的空间温度场构建出来，并逐折检验它准不准。建模、看效果、调参数都在这里。
- **实时模式** —— 调用训练好的模型，从**没见过的**数据里构建温度场：新数据一到就
  算出棚里各处的温度，**不再重新训练**。

模型标定一次就存进模型库，两种模式共用同一份 —— 换模型不用重训，页面上直接切。

## 功能特性

| 能力 | 说明 |
|---|---|
| 数据导入与检查 | 读一份 xlsx（棚内温湿度 + 棚外气象），报数据集身份、三项检查、测点空间分布、昼夜与残差 |
| 模型训练 | 特征构造表、最优参数、逐折与逐点误差。标定一次几十秒，成品可存进模型库 |
| 空间温度场构建 | 断面与三维棚体两种看法；三维**懒加载**，切过去才下载 Three |
| 模型库 | 存的是训练好的**成品**：库里选哪一份就用哪一份，切模型不重训、不重算 |
| 实时模式 | 在模型**没见过**的留出段上逐帧构场：144 帧，一帧一帧演，可暂停与步进 |
| 上传别的数据集 | 页① 可以传另一份 xlsx 进去看（落在 `backend/configs/uploads/`） |

一处口径提前说清：**页② 的每个数原样来自标定包** —— 重算一遍会得到略微不同的数，
于是页面上的数与 `configs/` 里那个包对不上。这是有意的：要的就是「这个包给出什么」。

## 界面预览

仓库里暂时没有截图（这一节待补）。五屏分别是：

| 屏 | 地址 | 长什么样 |
|---|---|---|
| ① 数据导入与检查 | `/data` | 数据集身份、三项检查、测点空间分布、昼夜与残差 |
| ② 模型训练 | `/train` | 特征构造表、最优参数、逐折与逐点误差 |
| ③ 空间温度场的构建 | `/field` | 断面与三维棚体两种看法（三维懒加载） |
| 模型库 | `/models` | 库里那几份成品；选一份就切过去 |
| 实时模式 | `/live` | 一屏一帧，**收起导航**；144 帧留出段逐帧演 |

顶部标题条常驻（标题 + 后端状态 + 模型库入口），左侧四项导航，另加顶部的模式开关
（训练 / 实时）。导航第四项「影响分析」**留位并写明理由**，不是空页 —— 后端还没有
逐点误差与按时段的接口，内容也还没定下来。

## 环境要求

| 需要 | 版本 | 说明 |
|---|---|---|
| Python | 3.10 起（开发与测试在 3.11 上） | 后端与核心库 `tfield` |
| Node.js | `^20.19.0 \|\| >=22.12.0` | Vite 8 的要求，写在这里免得白撞一次 |
| MySQL | 8 | 存「这一次用哪一份模型」。库与表**第一次连接时自建**，不用手工建库 |
| 数据集 | 一份 xlsx | **不进仓库**，见「安装步骤」第二步 |

## 安装步骤

```bash
git clone https://github.com/Gonyuanqian/Construction-of-the-spatial-temperature-field
cd Construction-of-the-spatial-temperature-field

# 后端依赖（含 FastAPI / uvicorn / pymysql）
cd backend && python -m pip install -r requirements-api.txt && cd ..

# 前端依赖
cd frontend && npm install && cd ..
```

### 第二步：把数据集放进去

**本仓库不带数据集。** 克隆下来第一件事是把你手上那份 xlsx 放进 `backend/`：

```
backend/人参棚_多棚温湿度_气象时间对齐数据集.xlsx
```

- **位置**：`backend/` 下，与 `api/`、`src/`、`configs/` 同级。
- **文件名必须逐字是这样**：名字由 `backend/src/tfield/config.py` 的 `DATA_FILENAME`
  写死，改一个字后端就找不到它。
- 它已在 `.gitignore` 里，所以放进去**不会**出现在 `git status`，也不会被误提交。
- 放好之后再启后端：页① 才会显示 `1308 个时刻 × 52 列`；没放时页① 是空态。
- **后端那批测试要的就是 `backend/` 下这一份。** 页① 的上传入口（落在
  `backend/configs/uploads/`）只给界面用，替代不了它。

## 快速开始

前置：一个活着的 MySQL（`127.0.0.1:3306`）。开两个终端：

```bash
# 终端 1：后端
cd backend
python -m uvicorn api.main:app --port 8503

# 终端 2：前端
cd frontend
npm run dev
```

打开 http://localhost:5173 —— 应当看到系统标题、`后端：ok`、以及数据集摘要
（`1308 个时刻 × 52 列`）。开发形态下 Vite 把 `/api` 代理到 `127.0.0.1:8503`。

只想起一个进程（生产形态）见「部署」。

## 使用示例

**界面走一遍（训练模式）**

1. 页① 看数据：数据集身份、三项检查、测点在棚里的位置、昼夜与残差。
2. 页② 标定：一次几十秒；跑完可以「保存进模型库」，也可以先不保存直接看效果。
3. 页③ 构场：断面与三维两种看法，时间轴可拖。
4. 标题条右边的档案盒图标 → 模型库：换一份成品就切过去，不重训。

**实时模式**

顶部模式开关切到「实时」，或直接开 `/live`。第一次点「准备实时源」要等**几十秒**
（建一次管线），之后每帧是秒级的。**帧历史在内存里**：重启后端就回到第 0 帧。

四件容易误解的事：

1. **末 144 帧是留出段。** 从 2026-07-27 12:00 起的那 144 帧，模型**没见过**；
   重标定只在其余 **1164 帧**上做过一次。实时模式演的就是这 144 帧 ——
   模型对它是外推，而这正是这一屏要看的东西。
2. **页③ 的时间轴因此止于 2026-07-27 11:55。** 这是留出的代价，不是 bug：
   模型的世界到那里为止。页③ 拉不到 12:00 以后，只有实时模式拉得到。
3. **页② 的最优参数与 A/B 指标是「新包」里的数。** 它们来自同折族、**不同参数**
   的那一次标定，与旧记录里的数**不可直接比大小** —— 与「兜底参数 vs 标定参数」
   是同一条口径：世界换了，数的意思就换了。
4. **帧号与页③ 的时间轴不是同一个东西。** 实时模式的帧号 `n` 是**留出段的下标**
   （0 至 143），页③ 的 `t_index` 是管线时间轴（1164 至 1307）。两个数在界面上都
   出现，别混。

**命令行**

```bash
curl -s http://127.0.0.1:8503/api/health
curl -s http://127.0.0.1:8503/api/dataset | head -40
curl -s http://127.0.0.1:8503/api/field/sections | head -40
```

接口全部挂在 `/api` 下，`/docs` 有 FastAPI 自带的交互式文档：

| 组 | 路径 |
|---|---|
| 数据集 | `GET /dataset`、`/dataset/timeseries`、`/dataset/layer-timeheight`、`/dataset/preview`、`POST /dataset/upload` |
| 特征与标定 | `GET /features`、`/calibration`；`POST /calibration/jobs`、`/calibration/diagnostics`；`GET /calibration/jobs/{job_id}` |
| 空间场 | `GET /field/arch`、`/field/sections`、`/field/curve`、`/field/compare`、`/field/volume` |
| 模型库 | `GET /models`、`/models/{model_id}`；`POST /models`、`/models/{model_id}/current` |
| 实时模式 | `GET /live/status`、`/live/frame/{n}`、`/live/volume/{n}`；`POST /live/prepare`、`/live/start`、`/live/pause`、`/live/next` |

### 三维视图的人眼验收

三维画面**拿不到任何自动证据**：测试环境是 jsdom，没有 canvas / WebGL，而这一版不
引入 headless WebGL（它脆、慢，在 Windows 上装不上是常态）。所以下面两件事**只能
人眼看**。**不接受截图当验收依据** —— 冻结的渲染器不构成独立证据。

1. **一座棚转起来对不对。** 拱壳的形状像不像那座棚；场在壳**里面**（不是穿出去）；
   混合出来的片确实在**逐层变透**，最远的那几片**还看得见**（不是消失）；拱顶下那
   一层确实是**空的**（无测量带没填色）；测点只出现在有实测的棚上。
2. **剖切刀切开之后，悬停读的是切开面上的点，不是已经切掉的那一片。** 把刀拉到
   中间，对着切面附近悬停：读数的时间与位置要跟着**看得见的那一面**走。这一条最
   容易错、也最难自己发现 —— 错的时候画面上一切正常，只有一个不该存在的温度。

（自动测试钉住的是另一半：体网格与后端库**逐位相等**、拱形掩膜与无测量带的下标
对账、悬停解算含「被切掉那一片被滤掉」、以及「Three 不在入口 chunk 里」。）

## 配置项

### 环境变量（后端）

| 变量 | 默认 | 用途 |
|---|---|---|
| `TFIELD_MYSQL_HOST` | `127.0.0.1` | MySQL 主机 |
| `TFIELD_MYSQL_PORT` | `3306` | 端口 |
| `TFIELD_MYSQL_USER` | `root` | 用户 |
| `TFIELD_MYSQL_PASSWORD` | `123456` | 口令 |
| `TFIELD_MYSQL_DB` | `tfield_models` | 存模型的库 |

⚠️ `root` / `123456` 是**本机演示**的默认值（也明文写在 `backend/api/models_store.py`
里），是个明知故犯的取舍 —— 换到别人连得到的机器上先改掉，用上面几个变量覆盖即可。

连不上 MySQL 时接口报 **500 并带上原始报错**，不静默答成「一个模型都没有」：
「库里空着」与「数据库连不上」在屏上长得一模一样，而这两件事要人做的事完全不同。

### 端口

| 端口 | 谁 |
|---|---|
| **8503** | 本项目的 FastAPI |
| **5173** | Vite 开发服务器（仅开发时） |

### 数据集

位置、文件名与 `.gitignore` 的情况见「安装步骤 / 第二步」。名字由
`backend/src/tfield/config.py` 的 `DATA_FILENAME` 定。

## 目录结构

```
backend/
  api/                FastAPI 服务层：路由、依赖、模型库、上传
    routes/           数据集、特征、标定、空间场、模型库、实时模式
    ported.py         检查与文案的纯函数（在 API 层另写一份，见文件头的说明）
  src/tfield/         核心库，与 Web 框架解耦
    data/             读取、时间轴修复、类型
    models/           两个模型：IDW 与趋势
    field/            棚拱几何、体网格、约束、构场
    validation/       折划分、误差指标、报告
    calibration.py    标定与标定包（成品）
    pipeline.py       管线：一次构场的全过程
    artifact.py       成品的字节格式
  configs/            标定包（成品）与上传落点
  scripts/            sync_backend.py、relocate_bundle.py
  tests/              后端测试
frontend/
  src/
    views/            五屏：数据、训练、空间场、模型库、实时
    components/       标题条、导航栏、通用件
    charts/           ECharts 图与两条色标
    scene/            Three 三维
    design/           令牌（tokens.css）、文案（copy.ts）、守卫（guards.test.ts）
    api/  composables/  router/
```

## 测试

```bash
cd backend  && python -m pytest -q -m "not slow"      # 后端
cd frontend && npm run build && npm test               # 前端
```

跑之前三件事：**数据集要放在 `backend/` 下**、**MySQL 要活着**、**前端要先构建**。
当前基线：

| 命令 | 期望 |
|---|---|
| `pytest -q -m "not slow"`（数据集在位、前端构建过） | `492 passed, 104 deselected` |
| 同上，但**没构建过前端** | `482 passed, 10 skipped, 104 deselected` |
| `npm run build && npm test` | 51 files / 510 tests |
| `pytest -q`（把 `slow` 也带上） | 共 596 条，其中 104 条要真训练，单条 10 秒起 |

五个容易被当成「环境坏了」的地方：

- **没放数据集**：13 个用例文件带守卫（`test_data_path().exists()`）会**静默跳过**，
  另一批直接读数据集的会**红** —— 于是表现是红与跳过混在一起。先照
  「安装步骤 / 第二步」把文件放好。
- **没构建前端**：`test_spa_fallback.py` 那 10 条要 `frontend/dist/index.html` 才跑
  （生产形态的角色回退无从谈起），所以是 `482 passed, 10 skipped`。
- **后端测试也要 MySQL**，用的是另一个库 `tfield_models_test` —— `tests/conftest.py`
  里钉死了：谁把它指到 `tfield_models` 上会**当场报错**，不会去清你攒下来的模型。
  连不上时**不 skip**：让「这台机器上 MySQL 没了」长得跟「全都通过」一样，正是
  要避免的那件事。
- **前端要先构建再测**：`scene/lazy.test.ts` 断的是构建产物（入口 chunk 里不许有
  Three），读的就是 `dist/`。产物比源码旧、或 `dist/` 不在时它**红**，不是 skip ——
  那是「这次改动的产物对不上源码」，红才是对的答案。
- **后端测试一次只跑一个进程**：两条 pytest 同时跑会抢同一个测试库。

## 部署

生产形态是**一个端口**：前端构建产物由 FastAPI 一起发出去。

```bash
cd frontend && npm run build && cd ..
cd backend && python -m uvicorn api.main:app --host 0.0.0.0 --port 8503
```

`api/main.py` 在 `frontend/dist/` 存在时把它挂在 `/` 上。回退那层是个子类：真文件走
原来的响应（MIME 一个字节不变），**只有基类已经判 404、且路径不是 `/api`** 才回
`index.html` 交给前端路由。所以 F5 或直接粘 `/train` 都进得去，而 `/api/date` 这种
写错的接口名仍然是诚实的 404。**`dist/` 不在就不挂载**，此时只有 API。

## 贡献指南

1. **先跑一遍测试**（上面两条命令），改动要让基线恢复绿。
2. **`backend/src/tfield/**` 永远不许 import 任何 Web 框架**（FastAPI 也不行）——
   服务层只活在 `backend/api/`。有测试守着
   （`tests/test_tfield_framework_free.py::test_tfield_里不许出现框架导入`）。
3. **改样式与文案前先读一眼守卫** `frontend/src/design/guards.test.ts`：十六进制色值
   只许出现在 `design/tokens.css` 与 `charts/scale.ts`；阴影只有一档且只能写成
   `var(--shadow)`；系统标题全仓只定义一次；导航页名逐字一致。
4. **提交信息用中文**，与仓库既有格式一致（`类型(范围): 一句话`）。
5. **`tfield` 会漂，工具让它看得见。** 同一份核心库在别处可能也有一份，两份一定会
   漂。对账与搬运：

   ```bash
   python backend/scripts/sync_backend.py --a <另一棵 tfield 树> --check
   python backend/scripts/sync_backend.py --a <另一棵 tfield 树> --push --apply
   ```

   `--a` 必填（不猜路径 —— 悄悄猜错一棵树比当场报错贵得多），`--b` 默认是本仓这一棵。
   不带 `--apply` 是干跑；`--push` / `--pull` 只搬运、**不删除**。本仓这一份与别处
   「有意不同」的文件清单写死在 `KNOWN_DIVERGENCES` 里，默认不碰：`--push` 撞上它们
   会停下，要覆盖得显式加 `--overwrite-known`（覆盖掉实时构场能力是不可逆的，默认
   动作必须是「不做」）。清单只列**文件**、不列行 —— 行级白名单会让「清单内文件的新
   漂移」也悄悄通过。
6. **标定包的指纹含 mtime。** `dataset_signature(path)` =
   `sha1(绝对路径 | mtime | 大小)[:16]`：**绝对路径本身**就是数据集身份的一部分，
   所以数据集换了个位置之后，指纹跟着变，`load_for` 就再也找不到原来的标定包
   （界面上表现为「还没有标定包」）。搬家用：

   ```bash
   cd backend
   python scripts/relocate_bundle.py \
     --bundle configs/bundle_0000000000000000_d6294c09.json \
     --dataset "人参棚_多棚温湿度_气象时间对齐数据集.xlsx" \
     --original "<包原来所在的那个 configs>/bundle_9055b199eeee1293_d6294c09.json" \
     --original-dataset "<数据集原来的那个位置>/人参棚_多棚温湿度_气象时间对齐数据集.xlsx" \
     --apply
   ```

   它先用 sha256 证明两份数据集**内容逐字节相同**，再把包的指纹改写成新指纹；
   内容不同、或包里记的指纹与旧数据集现在对不上，一律**拒绝迁移**（那说明参数已经
   失效，必须重标）。`--bundle` 传的是**占位名**：真实文件名里嵌的新指纹由脚本自己
   算出来。脚本**不会删除** `--original` 那一侧的旧包。

## 许可证

仓库目前**没有 LICENSE 文件** —— 法律上默认「保留所有权利」：别人可以看、可以学，
但未经许可不得复制、分发或用于商业用途。要加开源许可（MIT / Apache-2.0 之类）说一声。

## 联系方式

- 问题与建议：[开一个 Issue](https://github.com/Gonyuanqian/Construction-of-the-spatial-temperature-field/issues)
- 维护者：[@Gonyuanqian](https://github.com/Gonyuanqian)

## 开发进度与待解决的问题

**已经能用**：页① 数据导入与检查、页② 模型训练、页③ 空间温度场的构建（断面 + 三维）、
模型库（成品的存取与切换）、实时模式（144 帧留出段逐帧构场）。

**还没做**

- 导航第四项**「影响分析」留位未做**：后端还没有逐点误差与按时段的接口，内容也还没定。
- 实时模式左栏那三条（首页 / 历史数据 / 系统设置）同样是留位，没有页面。
- 数据检查从后端算的八项**在界面上收到三项**（结构完整性 / 时间轴 / 缺失）。被砍的
  五项（值域 / 卡死 / 跨棚离群 / 质量标记 / 对齐）后端照算，界面上只剩一句说明。

**已知的取舍与待办**

- **数据集不进仓库**，成员自备。代价是：没放数据集时那批测试是**红**而不是跳过 ——
  详见「测试」那一节。README 把「先放数据集」写成第二步，就是为了让人不撞上它。
- **页② 的每个数原样来自标定包**（见「功能特性」末尾），不重算。
- **三维画面只能人眼看**（见「使用示例 / 三维视图的人眼验收」），不接受截图当证据。
- **标定包的指纹含 mtime**：数据集被重新导出一次都会让旧包找不到。搬家要走
  `scripts/relocate_bundle.py`（见「贡献指南」第 6 条）。
- **没有 LICENSE**；**设计文档没有随仓库发布**。
- 公开仓库目前只发布**快照**版本（单个提交，不带本机的开发历史），所以发现问题请
  开 Issue 说清楚；分支与 PR 的合并方式还没定。
