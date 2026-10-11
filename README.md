# 棚式空间温度场重建系统

FastAPI 后端 + Vue 3 前端的棚体空间温度场重建与可视化系统：导入一份棚里的
温湿度与气象数据，标定出一套模型，然后把整个棚的空间温度场构建出来、并跟着
实时帧一帧一帧回放。

## 先放数据集

**本仓库不带数据集** —— 克隆下来第一件事是把你手上那份 xlsx 放进 `backend/`：

```
backend/人参棚_多棚温湿度_气象时间对齐数据集.xlsx
```

- **位置**：`backend/` 下，与 `api/`、`src/`、`configs/` 同级。
- **文件名**：必须逐字是这样。名字由 `backend/src/tfield/config.py` 的
  `DATA_FILENAME` 写死，改一个字后端就找不到它。
- 放好之后启动后端，页① 才会显示 `1308 个时刻 × 52 列`；没放时页① 是空态。
- 它在 `.gitignore` 里，所以放进去**不会**出现在 `git status`，也不会被误提交。
- 另有一个入口是页① 的上传（落在 `backend/configs/uploads/`）。但**后端那批
  测试要的是 `backend/` 下这一份** —— 只靠上传的那一份跑不了测试。

## 端口

| 端口 | 谁 |
|---|---|
| **8503** | 本项目的 FastAPI |
| **5173** | Vite 开发服务器（仅开发时） |

## 跑起来

**前置：一个活着的 MySQL** —— `127.0.0.1:3306`，`root` / `123456`。
2026-10-08 起「这次用哪一份模型」存在库里，页②③⑤ 与**每一条走 `get_pipeline`
的路由**（`/api/field*`、`/api/calibration*`、`/api/live*`）都要读它。MySQL 不在时
接口报 **500 并带上原始报错**：静默答成「一个模型都没有」会让「库里空着」与
「数据库连不上」在屏上长得一模一样，而这两件事要人做的事完全不同。
库与表在**第一次连接时自建**，不用手工 `CREATE DATABASE`。
连别的机器用 `TFIELD_MYSQL_HOST` / `TFIELD_MYSQL_PORT` / `TFIELD_MYSQL_USER` /
`TFIELD_MYSQL_PASSWORD` / `TFIELD_MYSQL_DB` 覆盖。

⚠️ `root` / `123456` 是**本机演示**的默认值（明文也写在
`backend/api/models_store.py` 里），是个明知故犯的取舍 —— 换到别人连得到的
机器上先改掉。

```bash
# 后端（终端 1）
cd backend
python -m pip install -r requirements-api.txt
python -m uvicorn api.main:app --port 8503

# 前端（终端 2）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 —— 应当看到标题、`后端：ok`、以及数据集摘要
（`1308 个时刻 × 52 列`）。

## 界面上有什么

顶部标题常驻 + 左侧四项导航，另加顶部那个模式开关（训练 / 实时）。
流水线上开着**三页**：

| 页 | 内容 | 接口 |
|---|---|---|
| ① 数据导入与检查 | 数据集身份、**三项**检查、测点空间分布（V1）、昼夜与残差（V2） | `/api/dataset`、`/api/field/arch`、`/api/dataset/timeseries`、`/api/dataset/layer-timeheight` |
| ② 模型训练 | 特征构造表、最优参数、逐折与逐点误差 | `/api/features`、`/api/calibration` |
| ③ 空间温度场的构建 | 断面（V5）与三维棚体两种看法 —— 三维**懒加载**，切过去才下载 Three | `/api/field/sections`、`/api/field/curve`、`/api/field/compare`、`/api/field/volume` |

「影响分析」在导航里**留位并说明**，不是空页 —— 后端还没有逐点误差与按时段的
接口，内容也还没定下来。

模式开关的另一半（实时模式）**不在**这个导航里，见下一节。

两处口径对盘时会用到：

- 数据检查从后端的八项**收到三项**（结构完整性 / 时间轴 / 缺失）。
  被砍的五项（值域 / 卡死 / 跨棚离群 / 质量标记 / 对齐）后端照算，
  但界面上只剩一句说明 —— 这是有意的，理由写在那句话里。
- 页② 的每一个数**原样来自标定包**。重算一遍会得到略微不同的数，
  于是页面上的数与 `configs/` 里那个包对不上。

`api/ported.py` 是**在 API 层另写一份**的检查与文案：那些纯函数与字符串原本
长在早先那份实现里，而那一份的模块顶层就 import 了 Web 框架，Vue 侧 import
不进来、塞进 `tfield` 又会与别处的副本永久漂移，所以照原样移植到 API 层。
它是一个新的漂移面，靠 `tests/test_ported.py` 盯着。

## 实时模式

路由是 `/live`（**不在**左侧导航里 —— 实时模式要收起导航，那一屏唯一提数据的
控件就是它自己那几个按钮）。它把数据集**留出段**的 144 帧一帧一帧接进时间轴。
下面四件都是**可见后果**，不是内部细节：

1. **末 144 帧是留出段。** 从 2026-07-27 12:00 起的那 144 帧，模型**没见过**；
   重标定只在其余 **1164 帧**上做过一次。实时模式演的就是这 144 帧 ——
   模型对它是外推，而这正是这一屏要看的东西。
2. **页③ 的时间轴因此止于 2026-07-27 11:55。** 这是留出的代价，不是 bug：
   模型的世界到那里为止。页③ 拉不到 12:00 以后，只有实时模式拉得到。
3. **页② 的最优参数与 A/B 指标是「新包」里的数。** 它们来自同折族、**不同参数**
   的那一次标定，与旧文档里记的那几个数**不可直接比大小** —— 与「兜底参数 vs
   标定参数」是同一条口径：世界换了，数就换了意思。
4. **帧历史在内存里。** 重启后端就回到第 0 帧（页面上写着这一句，不靠用户猜）。
   第一次进实时模式点「准备实时源」要等**几十秒**（建一次管线），之后每帧是秒级的。

接口是 `/api/live/{status,prepare,start,pause,next,frame/{n},volume/{n}}`。
⚠️ 帧号 `n` 是**留出段的下标**（0..143），与页③ 的 `t_index`（管线时间轴，
1164..1307）**不是同一个东西** —— 两个数在界面上都出现，别混。

## 跑测试

```bash
cd backend  && python -m pytest -q -m "not slow"    # 后端
cd frontend && npm run build && npm test             # 前端
```

**跑后端测试之前先把数据集放到 `backend/` 下**（见开头那一节）：那批用例要真读
那份 xlsx，没放就会**红**。另有 13 个用例文件带了守卫（`test_data_path().exists()`），
数据集不在时**静默跳过** —— 于是「没放数据集」的表现是红与跳过混在一起，
别把它当成环境坏掉。

同一种静默跳过还有一处：`test_spa_fallback.py` 那 10 条要
`frontend/dist/index.html` 在才跑（生产形态的角色回退无从谈起），
所以没构建过前端时后端是 `492 passed, 10 skipped`，构建过之后才满。

后端的测试**同样要 MySQL**，用的是另一个库 `tfield_models_test`
（`tests/conftest.py` 里钉死：谁把它指到 `tfield_models` 上会**当场报错**，不会去清
用户攒下来的模型）。连不上时**不 skip** —— 让「这台机器上 MySQL 没了」长得跟
「全都通过」一样，正是要避免的那件事。`-m "not slow"` 会略掉 104 条慢的
（含 `test_api_diagnostics.py` 整个文件）。

前端**要先构建再测**：`scene/lazy.test.ts` 断的是构建产物（入口 chunk 里不许有
Three），读的是 `dist/`。产物比源码旧、或 `dist/` 不存在时它**红**，不是 skip ——
那是「这次改动的产物对不上源码」，红才是对的答案。所以裸 `npm test` 在新克隆里
会红在那句「先跑 npm run build」上（消息本身是可操作的）。

## 三维视图（页③「三维」）的人眼验收

三维画面**拿不到任何自动证据**：jsdom 没有 canvas/WebGL（`frontend/vite.config.ts`
的测试环境就是 jsdom），而这一版不引入 headless WebGL —— 它脆、慢、在 Windows 上
装不上是常态。所以下面两件事**只能人眼看**，写在这里由人来看，不由测试签字。
**不接受截图当验收依据**：冻结的渲染器不构成独立证据。

自动验过的那些：

- 后端套件（`python -m pytest -q -m "not slow"`，另加 `-m slow` 那一组）：
  体网格与后端库**逐位相等**（`tests/test_api_volume.py`，是 `==` 不是 `almost`）、
  拱形掩膜与无测量带的下标对账、实测片与可用断面对账、参数越界与格子数上限。
- 前端套件（`npm run build && npm test`）：悬停解算（**含剖切刀切掉的那一片被滤掉**）、
  场景描述对象（密度即可信度、空腔、测点范围）、值到颜色的插值、坐标查询的吸附，
  以及「Three 不在入口 chunk 里」这条构建产物断言。

人眼看这两件：

1. **一座棚转起来对不对。** 拱壳的形状像不像那座棚；场在壳**里面**（不是穿出去）；
   混合出来的那些片确实在**逐层变透**，而且最远的那几片**还看得见**（不是消失）；
   拱顶下那一层确实是**空的**（无测量带没填色）；测点只出现在 `available_sheds`
   里那几座棚上。
2. **剖切刀切开之后，悬停读的是切开面上的点，不是已经切掉的那一片。**
   把刀拉到中间，对着切面附近悬停：读数的时间与位置要跟着**看得见的那一面**走。
   这一条最容易错，也最难自己发现 —— 错的时候画面上一切正常，只有一个
   不该存在的温度。（自动测试里钉着算法那一半，没钉几何那一半。）

## `tfield` 会漂，工具让它看得见

`backend/src/tfield/` 是与 API 层解耦的核心库。同一份库在别的地方可能也有一份，
两份一定会漂。漂移**不被阻止，但一定看得见**：

```bash
python backend/scripts/sync_backend.py --a <另一棵 tfield 树> --check
python backend/scripts/sync_backend.py --a <另一棵 tfield 树> --push --apply
python backend/scripts/sync_backend.py --a <另一棵 tfield 树> --pull --apply
```

`--a` 是另一棵树，`--b` 默认是本仓的 `backend/src/tfield`。**两个路径都必须给全**
—— 没有猜的默认值，因为悄悄猜错一棵树比当场报错贵得多。

不带 `--apply` 就是干跑。`--push` / `--pull` 只搬运、**不删除**。

**本仓这一份与别处是「有意不同」的。** 实时模式那几处改动不该出现在别的树上，
清单写死在 `backend/scripts/sync_backend.py` 的 `KNOWN_DIVERGENCES` 里：

| 文件 | 本仓这一份多了什么 |
|---|---|
| `data/loader.py` | 留出切分（`split_holdout`）与派生指纹 |
| `pipeline.py` | `append_live_frame` 与时间轴访问器（`n_times` / `timestamps` / `time_at` / `bg_light_at`） |
| `validation/report.py` | 时间轴长度按实际行数算（训练段只剩 1164 行） |
| `field/constraints.py` | `light_at` 走管线而不是宽表（实时帧不在宽表里） |
| `artifact.py` | 整个文件：成品的字节格式（别处的实现不存成品，它每页现训） |
| `data/types.py` | `FixReport` 多了 `duplicate_count`（页① 要报原始文件的重复时刻数） |
| `data/timestamp.py` | `repair_axis` 里数原始轴的重复时刻，填进 `FixReport` |

`--push` / `--pull` **默认不碰**清单里的文件：`--push` 撞上它们会停下，
要显式加 `--overwrite-known` 才覆盖（覆盖掉实时构场能力是不可逆的，
默认动作必须是「不做」）；`--pull` 反过来，默认**排除**它们，要一起搬得加
`--include-known`。清单之外任何差异照旧报警 —— 仍然是要看的那些。

清单只列**文件**、不列行：行级白名单会让「清单内文件的新漂移」也悄悄通过，
那时清单就不是安全阀，而是一张免死金牌。

## 标定包为什么在 `configs/` 里是那个怪名字

`dataset_signature(path)` = `sha1(绝对路径 | mtime | 大小)[:16]` ——
**绝对路径是数据集身份的一部分**。数据集连同标定包一起换了个位置之后，路径变了，
指纹跟着变，`load_for` 就再也找不到原来的标定包（界面上表现为「还没有标定包」）。

`scripts/relocate_bundle.py` 处理这件事：先用 sha256 证明两份数据集**内容逐字节相同**，
再把包的 `dataset_sig` 改写成新指纹。**内容不同就拒绝迁移** —— 那必须重标。

```bash
cd backend
python scripts/relocate_bundle.py \
  --bundle configs/bundle_0000000000000000_d6294c09.json \
  --dataset "人参棚_多棚温湿度_气象时间对齐数据集.xlsx" \
  --original "<包原来所在的那个 configs>/bundle_9055b199eeee1293_d6294c09.json" \
  --original-dataset "<数据集原来的那个位置>/人参棚_多棚温湿度_气象时间对齐数据集.xlsx" \
  --apply
```

`--bundle` 传的是**占位名**：真实文件名里嵌的新指纹由脚本自己算出来，
调用方不需要预先知道它。（所以上面这个包里没有真指纹的那串数字 —— 是故意的。）

脚本**不会删除** `--original` 那一侧的旧包，所以旧位置上的标定成果不受影响。
真正决定删不删的是「旧包在不在**新数据集所属的那一份工程**里」——
不是「跨不跨目录」，更不是调用方给的 `--bundle` 说在哪。
（`--bundle` 的语义只是「新包写到哪」；重迁移时最顺手的写法是「写回原处」，
所以拿它当删除判据，一刀就会落在别处不可逆的标定成果上。）

脚本还会核对**包里记的指纹 == 旧数据集现在的指纹**。对不上就拒绝迁移 ——
那说明旧数据集在标定之后被重新导出过，包里那套参数对它已经失效，
必须重标。

## `tfield` 必须保持框架无关

`backend/src/tfield/**` **永远不得 import 任何 Web 框架**（FastAPI 也不行）。
服务层只活在 `backend/api/`。这条有测试守着
（`tests/test_tfield_framework_free.py::test_tfield_里不许出现框架导入`）。
