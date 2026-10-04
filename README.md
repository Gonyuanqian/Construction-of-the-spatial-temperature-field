# 人参棚空间温度场重建系统 · Vue 版

同一份后端（`tfield`）的**第二种前端实现**，与 Streamlit 版并行存在、互不干扰。
本仓库独立于 `../空间温度场的构建/`。

- 后端库与规格书：`../空间温度场的构建/`
- **设计文档**：[`../空间温度场的构建/docs/superpowers/specs/2026-10-03-Vue前端-design.md`](../空间温度场的构建/docs/superpowers/specs/2026-10-03-Vue前端-design.md)

> ⚠️ **两个目录必须相邻**：设计文档不复制，靠相对路径引用。
> 移动任何一个目录都会断开这个链接。

## 端口

| 端口 | 谁 |
|---|---|
| 8501 | 另一个项目 `software-shiyan/前端系统开发` —— **不要占** |
| 8502 | Streamlit 版 —— **不要占** |
| **8503** | 本项目的 FastAPI |
| **5173** | Vite 开发服务器（仅开发时） |

## 跑起来

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

## 界面上有什么（计划 2 之后）

顶部标题常驻 + 左侧四项导航。本轮开放**前两页**：

| 页 | 内容 | 接口 |
|---|---|---|
| ① 数据导入与检查 | 数据集身份、**三项**检查、测点空间分布（V1）、昼夜与残差（V2） | `/api/dataset`、`/api/field/arch`、`/api/dataset/timeseries`、`/api/dataset/layer-timeheight` |
| ② 模型训练 | 特征构造表、最优参数、逐折与逐点误差 | `/api/features`、`/api/calibration` |

「空间温度场的构建」与「影响分析」在导航里**留位并说明**，不是空页 ——
前者排在下一份计划（要先有管线缓存与切面/体积接口），后者内容还没定。

两处口径对盘时会用到：

- 数据检查从后端的八项**收到三项**（结构完整性 / 时间轴 / 缺失）。
  被砍的五项（值域 / 卡死 / 跨棚离群 / 质量标记 / 对齐）后端照算，
  但界面上只剩一句说明 —— 这是有意的，理由写在那句话里。
- 页② 的每一个数**原样来自标定包**。重算一遍会得到略微不同的数，
  于是页面上的数与 `configs/` 里那个包对不上。

`api/ported.py` 是从旧项目 `app/app.py` **移植**过来的检查与文案。
它是一个新的漂移面，靠 `tests/test_ported.py` 的源码文本比对盯着。

## 跑测试

```bash
cd backend  && python -m pytest -q -m "not slow"    # 后端
cd frontend && npm test                              # 前端
```

## `tfield` 是复制来的，会漂

`backend/src/tfield/` 是 `../空间温度场的构建/src/tfield/` 的**逐字节副本**。
两份一定会漂。漂移**不被阻止，但一定看得见**：

```bash
python backend/scripts/sync_backend.py --check          # 0 = 一致，1 = 有差异（会列出文件）
python backend/scripts/sync_backend.py --push --apply   # 真源 → 副本
python backend/scripts/sync_backend.py --pull --apply   # 副本 → 真源
```

不带 `--apply` 就是干跑。`--push` / `--pull` 只搬运、**不删除**。

## 标定包为什么在 `configs/` 里是那个怪名字

`dataset_signature(path)` = `sha1(绝对路径 | mtime | 大小)[:16]` ——
**绝对路径是数据集身份的一部分**。项目复制过来之后路径变了，指纹跟着变，
`load_for` 就再也找不到原来的标定包（界面上表现为「还没有标定包」）。

`scripts/relocate_bundle.py` 处理这件事：先用 sha256 证明两份数据集**内容逐字节相同**，
再把包的 `dataset_sig` 改写成新指纹。**内容不同就拒绝迁移** —— 那必须重标。

```bash
cd backend
python scripts/relocate_bundle.py \
  --bundle configs/bundle_0000000000000000_d6294c09.json \
  --dataset "人参棚_多棚温湿度_气象时间对齐数据集.xlsx" \
  --original "../../空间温度场的构建/configs/bundle_9055b199eeee1293_d6294c09.json" \
  --original-dataset "../../空间温度场的构建/人参棚_多棚温湿度_气象时间对齐数据集.xlsx" \
  --apply
```

`--bundle` 传的是**占位名**：真实文件名里嵌的新指纹由脚本自己算出来，
调用方不需要预先知道它。（所以上面这个包里没有真指纹的那串数字 —— 是故意的。）

路径是 `../../` 而不是 `../`：两个项目是同级目录，从 `backend/` 往上两级才到桌面。

脚本**不会删除** `../../空间温度场的构建/configs/` 里的旧包，所以旧项目的标定成果不受影响。
真正决定删不删的是「旧包在不在**新数据集所属的项目**里」——
不是「跨不跨目录」，更不是调用方给的 `--bundle` 说在哪。
（`--bundle` 的语义只是「新包写到哪」；重迁移时最顺手的写法是「写回原处」，
所以拿它当删除判据，一刀就会落在别人不可逆的标定成果上。）

脚本还会核对**包里记的指纹 == 旧数据集现在的指纹**。对不上就拒绝迁移 ——
那说明旧数据集在标定之后被重新导出过，包里那套参数对它已经失效，
必须重标。

## `tfield` 必须保持框架无关

`backend/src/tfield/**` **永远不得 `import fastapi` 或 `import streamlit`**。
FastAPI 只活在 `backend/api/`。这条有测试守着
（`tests/test_copy_fidelity.py::test_tfield_里不许出现框架导入`）。
