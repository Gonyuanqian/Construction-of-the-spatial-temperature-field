"""数据集资源。"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from tfield import config as C
from tfield.data.loader import dataset_signature

from .. import deps, paths, ported, uploads

router = APIRouter(tags=["dataset"])


@router.get("/dataset")
def get_dataset() -> dict[str, Any]:
    # ⚠️ **不再显式传 path**。以前这里写 `deps.get_dataset(paths.dataset_path())`，
    # 于是它绕过了「空态」，永远读交付数据集 —— 与规格书 §1.1「不预置、不代劳」
    # 正相反，而且**不报错**：界面看起来一切正常，只是用的不是用户导的那一份。
    #
    # 现在问的是「现在在用哪一份」：
    #   空态      → `deps.current_dataset_path()` 抛 `NoDatasetError`，main.py 翻成 409
    #   文件不见了 → `get_dataset()` 抛 `FileNotFoundError`，下面接住翻成 404
    cur = deps.current_dataset_path()
    try:
        ds = deps.get_dataset()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"数据集不存在：{cur}")
    ts = ds.wide[C.COL_TIMESTAMP]
    codes = _point_codes(ds)
    return {
        "signature": ds.signature,
        "file": deps.current_dataset_name(),
        "n_times": int(ds.wide.shape[0]),
        "n_columns": int(ds.wide.shape[1]),
        # 页① 那排卡片要的另外两格。**都由后端算**：前端不做任何数值计算。
        #
        # `n_missing` 是缺失的**格子**数（不是「有缺失的行数」），与
        # `ported.check_missing` 同一口径 —— 同一屏上两个「缺失」必须是一个意思。
        #
        # `n_dup_times` 来自修复**前**的原始轴（`FixReport.duplicate_count`）。
        # 修完的轴严格递增（不递增就直接抛），拿它算这个数恒为 0 —— 那样这一格
        # 就成了一句永远不变的套话，而不是「这份数据从哪来」。
        "n_missing": int(ds.wide.isna().sum().sum()),
        "n_dup_times": int(ds.fix.duplicate_count),
        "time_start": ts.iloc[0].isoformat(),
        "time_end": ts.iloc[-1].isoformat(),
        "sheds": {s: float(y) for s, y in ds.sheds.items()},
        "positions": [
            {"id": pos, "x": float(p.x), "z": float(p.z), "layer": p.layer}
            for pos, p in ds.layout.items()
        ],
        # 测点编号单独一格，**不塞进 `positions`**：那一格是几何
        # （`test_测点的几何形状没有被这次改动动到` 守着），而编号是展示。
        # 混在一起的话，每个读 `positions` 的地方都要重新想一遍
        # 「多出来的那个字段是不是几何」。
        "point_codes": codes,
        "fix": {
            "n_rows": ds.fix.n_rows,
            "fixed_indices": list(ds.fix.fixed_indices),
            # 修复前后都报：① 页要拿「修复后单调」当作一条校验通过的证据，
            # 而「修复前不单调」正是这条校验存在的理由，缺一半就讲不清。
            "monotonic_before": ds.fix.monotonic_before,
            "monotonic_after": ds.fix.monotonic_after,
            "spacing_seconds": ds.fix.spacing_seconds,
            "n_gaps": len(ds.fix.gaps),
        },
        "checks": [
            {"no": r.no, "name": r.name, "what": r.what,
             "status": r.status, "evidence": r.evidence}
            for r in ported.dataset_checks(ds)
        ],
        "checks_note": ported.checks_note(),
        "temperature": _temperature_stats(ds),
    }


def _point_codes(ds) -> dict[str, str]:
    """测点的展示编号：`B1`、`B2`……（页① 切面图上点旁那一个）。

    **不来自数据集。** `测点字典` sheet 里只有设备通道号（`1, 0.15, 0.40`
    —— 1 是棚 1、3 是棚 2、5 是棚 3），没有 B 编号。这一套是用户给的那张
    切面图上的编号，次序从图上逐点抄下来：**先按高度分层、层从高到低
    （拱顶那层在前），同层按 x 从左到右。**

    为什么在后端算：编号是**屏上要显示的字符串**，而前端不做任何计算
    （spec §六 硬约束 1）。为什么落在这里而不是 `tfield` 库里：它是展示
    约定，不是数据 —— 库里放的是这个棚怎么长的，不是这张图怎么标。

    按规则算而不是写一张八行的表：换一份数据集时表会缺项，而缺项在图上
    表现为「有几个点没编号」，最容易被当成有意为之。规则永远覆盖得住，
    而规则本身由 `test_测点编号按参考图的次序排` 钉在参考图的那八个编号上。
    """
    order = sorted(ds.layout.items(), key=lambda kv: (-kv[1].z, kv[1].x))
    return {pos: f"B{i}" for i, (pos, _) in enumerate(order, start=1)}


def _finite(v: float) -> float | None:
    """把非有限浮点（NaN / ±Inf）翻成 None。

    ⚠️ 这不是洁癖：响应由 Starlette 的 `JSONResponse` 序列化，它用
    `json.dumps(..., allow_nan=False)`。任何 NaN/Inf 一旦进了响应体就是
    `ValueError` → HTTP 500，而不是 null —— 这件事在本项目上实测过。
    """
    f = float(v)
    return f if math.isfinite(f) else None


def _temperature_stats(ds) -> list[dict[str, Any]]:
    """每个 (棚, 测点) 的全时段均值 / 最小 / 最大。

    为什么由后端算：V1 要在测点旁边标 5 天均值，而「求个平均」是数值计算 ——
    前端不做（spec §六 硬约束 1）。

    为什么是 (棚, 测点) 而不是只有测点：三个棚并排画，同一个点位在三座棚里
    的均值是不一样的，只报一个数就把三座棚画成一样了。

    ⚠️ 退化输入必须挡住，否则会 500：全缺失列 → mean/min/max 全是 NaN；
    空列 → pandas 的 min()/max() 直接抛 ValueError。两者都翻成 None，
    因为 `JSONResponse(allow_nan=False)` 不吃 NaN/Inf（见 `_finite`）。
    """
    out: list[dict[str, Any]] = []
    for shed in C.SHED_ORDER:
        for pos in ds.layout:
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col not in ds.wide.columns:
                continue
            v = ds.wide[col].astype(float)
            if len(v) == 0:
                stat: dict[str, float | None] = {"mean": None, "min": None, "max": None}
            else:
                stat = {"mean": _finite(v.mean()), "min": _finite(v.min()),
                        "max": _finite(v.max())}
            out.append({"shed": shed, "position": pos, **stat})
    return out


# ── 页① 的两张图 ──


def _load() -> Any:
    """取当前在用的数据集；文件不在时翻成 404，与 `/api/dataset` 同一口径。

    走 `deps.get_dataset()`（无 path）—— 它问的是「现在在用哪一份」，
    空态会抛 `NoDatasetError`，由 `main.py` 的全局 handler 翻成 409。
    这里只接住 `FileNotFoundError`：那是另一种错，404。

    ⚠️ 404 的 detail 报的是**当前那份**的路径，不再是 `paths.dataset_path()`
    （交付数据集）。报错里给一个不是正在用的路径，等于把人指错地方。
    """
    try:
        return deps.get_dataset()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"数据集不存在：{deps.current_dataset_path()}",
        ) from None


def _sensor_keys(ds) -> list[tuple[str, str, str]]:
    """→ [(key, shed, position)]，key = "p1|x0.15_z0.4"。顺序固定。"""
    out: list[tuple[str, str, str]] = []
    for shed in C.SHED_ORDER:
        for pos in ds.layout:
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col in ds.wide.columns:
                out.append((f"{shed}|{pos}", shed, pos))
    return out


@router.get("/dataset/timeseries")
def get_timeseries() -> dict[str, Any]:
    """V2 的上格与下格。

    **下格那个「减去背景」是这里算的**，不是前端（spec §六 硬约束 1）。
    前端做这一步的话，界面上显示的数与后端算出的数就成了两条独立的计算路径 ——
    漂了不会报错，只会让人对着一个错的数做判断。

    `detrended_domain` 由后端给出 ±3 °C：纵轴范围也是判断的一部分，
    让前端各自去猜会得到三个棚不同的纵轴，并排看就失去意义。

    ⚠️ 每个数都过 `_finite`：任何非有限浮点（某列有缺失时，原始棚温与
    「棚温 − 背景」都会是 NaN）一旦进响应体，`JSONResponse(allow_nan=False)`
    就抛 `ValueError` → HTTP 500。翻成 None（JSON null）才是「这段没有值」。
    """
    ds = _load()
    wide = ds.wide
    bg = wide[C.BG_TEMP].to_numpy(float)

    sensors: dict[str, list[float | None]] = {}
    detrended: dict[str, list[float | None]] = {}
    means: dict[str, list[float | None]] = {}
    dmeans: dict[str, list[float | None]] = {}

    for key, shed, pos in _sensor_keys(ds):
        v = wide[f"{shed}_{pos}_{C.VAR_TEMP}"].to_numpy(float)
        sensors[key] = [_finite(a) for a in v]
        detrended[key] = [_finite(a - b) for a, b in zip(v, bg)]

    for shed in C.SHED_ORDER:
        cols = [f"{shed}_{pos}_{C.VAR_TEMP}" for pos in ds.layout
                if f"{shed}_{pos}_{C.VAR_TEMP}" in wide.columns]
        m = wide[cols].to_numpy(float).mean(axis=1)
        means[shed] = [_finite(a) for a in m]
        dmeans[shed] = [_finite(a - b) for a, b in zip(m, bg)]

    ts = pd.to_datetime(wide[C.COL_TIMESTAMP])
    return {
        "n_times": int(len(wide)),
        "time": [t.isoformat() for t in ts],
        "bg_temp": [_finite(a) for a in bg],
        "sensors": sensors,
        "shed_mean": means,
        "detrended": detrended,
        "detrended_mean": dmeans,
        "detrended_domain": [-3.0, 3.0],
        "note": ("下面那一格是棚温减背景温度；减法在后端做，前端只负责画。"
                 "减去昼夜之后剩下的才是空间信号。"),
    }


@router.get("/dataset/layer-timeheight")
def get_layer_timeheight(step: int | None = None) -> dict[str, Any]:
    """V2 的第三格：「时间 × 高度」热图。

    **数据源是实测棚温，不是模型预测。** 页① 回答的是「信号藏在哪」，
    那就该看实测值。走模型预测会让数据页依赖训练好的模型 ——
    一个还没标定的系统就不该画得出这一格。

    行 = 层：同一层的多个测点合成一行（z0.4 上有三个点），
    但**拱顶那两个测点高度同为 1.10 m、x 不同**，合成一行就把前坡后坡的差别抹了，
    所以它们按 x 分开列。行序按 (z, x) 升序 —— 低的在下面。

    1308 个时刻画不出条纹，等间隔抽稀到 300 列上下。

    ⚠️ 矩阵里的每个格子都过 `_finite`：某一层的三个测点若在某时刻全缺失，
    `groupby.mean()` 会给 NaN，直接进响应体就是 HTTP 500（非有限值必须在
    序列化之前翻成 null）。空出的一格仍是合法的热图输入。
    """
    ds = _load()
    wide = ds.wide
    n_t = len(wide)
    step = max(1, n_t // 300) if step is None else max(1, int(step))
    idx = list(range(0, n_t, step))
    ts = pd.to_datetime(wide[C.COL_TIMESTAMP])

    out: dict[str, Any] = {}
    for shed in C.SHED_ORDER:
        labels: list[str] = []
        zs: list[float] = []
        xs: list[float] = []
        rows: list[list[float]] = []
        for pos, sp in ds.layout.items():
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col not in wide.columns:
                continue
            # 拱顶两点 layer 都是 ztop —— 用 x 把标签分开
            labels.append(f"zH({sp.x:.2f})" if sp.layer == "ztop" else sp.layer)
            zs.append(float(sp.z))
            xs.append(float(sp.x))
            rows.append([float(a) for a in wide[col].to_numpy(float)[idx]])

        df = pd.DataFrame(rows, index=labels, columns=idx)
        order = (pd.DataFrame({"label": labels, "z": zs, "x": xs})
                 .drop_duplicates("label").sort_values(["z", "x"])["label"].to_numpy())
        z_of = {lb: z for lb, z in zip(labels, zs)}
        mat = df.groupby(level=0, sort=False).mean().reindex(order)
        out[shed] = {
            "labels": [str(v) for v in order],
            "z": [float(z_of[str(v)]) for v in order],
            "values": [[_finite(x) for x in row]
                       for row in mat.to_numpy(float).tolist()],
        }

    return {
        "step": step,
        "n_times": int(n_t),
        "n_columns": len(idx),
        "time": [ts.iloc[i].isoformat() for i in idx],
        "x_label": f"时刻（每 {step} 个时刻取一个）",
        # Ruling P2：这句会由前端直接渲染，属用户可见字符串 ——
        # brief 原文用的是带空格的破折号（禁用连接符），改成「；」，句意未变。
        "source": "实测棚温（每层各测点的实测值取均值），不是模型预测",
        "sheds": out,
    }


# ── 页① 的数据预览表 ──

#: 预览表一次给多少行。缺省，不是上限 —— 上限是总行数（见下面 `n` 那一行）。
PREVIEW_ROWS: int = 500


@router.get("/dataset/preview")
def get_preview(limit: int | None = None) -> dict[str, Any]:
    """页① 的数据预览表：**只读的头部切片**。

    为什么要有这条出口：页① 上「我导进来的确实是这份文件」这句话，四个统计数
    说不了 —— 得能看到行与列本身。而前端不做任何计算（spec §六 硬约束 1），
    宽表只能由后端切好送过来。

    为什么只给前 N 行：1308 × 25 全铺进 DOM 是 3.4 万个单元格。切片是**明写在
    屏上的** —— `n_rows` 与 `n_times` 一起给，页面上才写得出「前 500 行
    （共 1308 行）」。只回一个数组的话，屏幕上看不出看到的是全部还是一段，
    而那种沉默比截断本身更坏。

    为什么列名不照抄 xlsx：文件里的列名是 `p1_x0.15_z0.4_temp_C`，25 个这种
    名字并排没人读得动，且与切面图上的编号对不上。标签用 `p1·B1`：B 编号与
    切面图同源（同一个 `_point_codes`），棚前缀与 tooltip 同源（都是 shed id）。
    而 `key` **照旧是宽表里的列名** —— 表里任何一格因此都还追得回文件那一列。

    湿度列与光照列不进表：本系统没有一处读它们，摆进来只是把宽度翻倍。

    ⚠️ 每个数都过 `_finite`：缺失格子是 NaN，进了响应体就是
    `JSONResponse(allow_nan=False)` → HTTP 500（与上面两条出口同一个坑）。
    """
    ds = _load()
    wide = ds.wide
    n_times = int(len(wide))

    # 夹到 [0, n_times]：
    #   负数按 0（**不是**按缺省的 500 —— 静默放大是另一种撒谎）
    #   超出按总行数（这份数据 1308 行由契约钉死，不另设一个魔法上界）
    n = PREVIEW_ROWS if limit is None else int(limit)
    n = max(0, min(n, n_times))

    codes = _point_codes(ds)
    columns: list[dict[str, str]] = []
    if C.BG_TEMP in wide.columns:
        columns.append({"key": C.BG_TEMP, "label": "背景温度"})
    for shed in C.SHED_ORDER:
        # ⚠️ 走 `codes` 的次序，**不是** `ds.layout` 的。
        # `SENSOR_LAYOUT` 是按参考图上的坐标一条条写下来的（x0.15、x0.4、x0.8…），
        # 而 B 编号是「层从高到低、同层从左到右」**另排**出来的 —— 两者不是同一个
        # 次序，差得很远：照 `ds.layout` 排，表头会读成 B6、B3、B1、B7、B4、B2…
        # 并排摆着的那张切面图是按编号读的，表头也按编号排，两张才对得上。
        # （`dict` 保插入序，`_point_codes` 正是按编号次序插的。）
        for pos in codes:
            col = f"{shed}_{pos}_{C.VAR_TEMP}"
            if col in wide.columns:
                columns.append({"key": col, "label": f"{shed}·{codes[pos]}"})

    head = wide.iloc[:n]
    # 时间**单列一个字段**，不混进 `values`：它是行标、要在表里粘在左边，
    # 与那 25 个数值列不是一类东西（混一起就得往 `list[float]` 里塞字符串）。
    ts = pd.to_datetime(head[C.COL_TIMESTAMP])
    return {
        "n_times": n_times,
        "limit": n,
        "n_rows": n,
        "columns": columns,
        "time": [t.isoformat() for t in ts],
        "values": [[_finite(v) for v in row]
                   for row in head[[c["key"] for c in columns]].to_numpy(float).tolist()],
    }


# ── 上传（页① 的第一块）──


@router.post("/dataset/upload")
async def upload_dataset(request: Request, name: str = "") -> dict[str, Any]:
    """收一份 xlsx，换掉当前数据集（规格书 §四）。

    **原始请求体，不是 multipart。** `name` 走 query 不走请求头：`X-Filename`
    里的中文要走 RFC 5987 编码，而 query 天生是 UTF-8 —— 少一层编码就少一处
    「某些文件名会乱码」。

    ⚠️ **不预跑管线**（§4.2）：上传校验只做「能加载 + 切分两侧非空」。
    `fit` 一次要几十秒到几分钟，每传一次就卡一次，而这一步的职责只是
    「这份数据能不能跑」。

    失败时**当前数据集一个字节不改** —— 那由 `uploads.accept()` 的临时文件
    与 `deps.install_dataset()` 的顺序保证，这个函数里没有第二条改指针的路径。
    """
    reject = uploads.precheck(name, _content_length(request))
    if reject is not None:
        raise HTTPException(status_code=reject.status, detail=reject.detail)

    data = await request.body()
    try:
        info = uploads.accept(data, name, dest_dir=paths.UPLOADS)
    except uploads.Rejected as r:
        raise HTTPException(status_code=r.status, detail=r.detail)

    # 先清缓存、再改指针（顺序不可分割，所以合成 `install_dataset` 一个入口）。
    deps.install_dataset(info.path)

    # ⚠️ 签名**在改名之后**才算：`dataset_signature` 里带着**绝对路径**，
    # 拿临时名算出来的那个数与 `GET /api/dataset` 随后报的不是一个 ——
    # 而前端拿它作身份（页① 那张卡、Future 的「换没换」判断）。
    return {
        "signature": dataset_signature(info.path),
        "file": info.path.name,
        "n_times": info.n_times,
        "n_columns": info.n_columns,
        "time_start": info.time_start,
        "time_end": info.time_end,
    }


def _content_length(request: Request) -> int | None:
    """`Content-Length`，读不出来就当没有。

    **不做任何猜测**：没有这个头（chunked 传输）时返回 None，`precheck` 放行 ——
    放行的代价是那个 body 会被读进内存，而不放行的代价是**正常上传全被拒**。
    真实浏览器发 blob 一定带这个头。
    """
    raw = request.headers.get("content-length")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None
