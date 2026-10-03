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

脚本**不会删除** `../../空间温度场的构建/configs/` 里的旧包（跨目录一律保留），
所以旧项目的标定成果不受影响。

## `tfield` 必须保持框架无关

`backend/src/tfield/**` **永远不得 `import fastapi` 或 `import streamlit`**。
FastAPI 只活在 `backend/api/`。这条有测试守着
（`tests/test_copy_fidelity.py::test_tfield_里不许出现框架导入`）。
