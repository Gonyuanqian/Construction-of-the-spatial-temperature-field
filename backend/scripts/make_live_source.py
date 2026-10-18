"""把交付数据集切成页⑤ **自己的**两份数据源（规格书 2026-10-16 §四）。

    backend/configs/live/train.xlsx   1164 行   timestamp <  2026-07-27 12:00
    backend/configs/live/live.xlsx     144 行   timestamp >= 2026-07-27 12:00

**一次性命令，产物是死件**：不挂在任何启动路径上，也不在导入流程里自动生成
（用户 2026-10-16：「这个不用」）。演示前手工跑一次：

    python backend/scripts/make_live_source.py

⚠️ **切之前先把时间轴修好，并且把修好的值写出去。** `repair_axis` 修的是
「某一行比下一行还大」（减 8 小时），它需要**下一个邻居**才算出该修成多少。
在没修的轴上切，落在边界上的那一行会带着差 8 小时的值悄悄进文件 —— 它是那
一段的最后一行，后面没东西可比，单调性检查不会报。切完再修则要回头重写两份。
`repair_axis` 幂等，所以产物再加载时报告「无需修复」是**如实**的。

⚠️ 两份产物**各自**都是合法数据集：三张表齐全、宽表 52 列。`SHEET_DICT`
逐字复制 —— 两份文件的测点字典必须一字不差，页⑤ 的模型徽章靠的正是这一点
（`groups_signature` 相同 → `compatible` 相同）。

⚠️ 产物**不进仓库**（`.gitignore`：`backend/configs/live/*.xlsx`），理由与
`uploads/` 一样：它们是从那份不进仓库的数据集上切下来的，内容与它等量齐观。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BACKEND), str(BACKEND / "src")]

import pandas as pd  # noqa: E402

from api import paths                                   # noqa: E402
from tfield import config as C                          # noqa: E402
from tfield.data.loader import HOLDOUT_CUTOFF, load_dataset  # noqa: E402
from tfield.data.timestamp import repair_axis           # noqa: E402

TRAIN_NAME = "train.xlsx"
LIVE_NAME = "live.xlsx"


def make_live_source(src: pathlib.Path | str,
                     out: pathlib.Path | str) -> tuple[int, int]:
    """把 `src` 切两份写进 `out` 目录，返回 `(训练段行数, 实时段行数)`。

    两侧任何一侧为空都**直接拒绝**：一个空的 `live.xlsx` 会让页⑤ 悄悄演成
    「0 帧」，而一个空的 `train.xlsx` 会让管线在几十秒后死在 fit 里 ——
    两种错都离现场很远，所以卡在这儿。
    """
    src, out = pathlib.Path(src), pathlib.Path(out)
    sheets = pd.read_excel(src, sheet_name=None)
    main = sheets[C.SHEET_MAIN]
    quality = sheets[C.SHEET_QUALITY]

    # 第 2、3 步：在**修好的**轴上切，并且把修好的值写出去（见模块注释）。
    idx, _report = repair_axis(main[C.COL_TIMESTAMP])
    main = main.copy()
    main[C.COL_TIMESTAMP] = idx.to_numpy()
    quality = quality.copy()
    quality[C.COL_TIMESTAMP] = idx.to_numpy()

    # `DatetimeIndex < Timestamp` 直接给 numpy bool 数组（不再是 Series，
    # 所以这里没有 `.to_numpy()`）；`.iloc[ndarray]` 与 `~` 都认它。
    keep = idx < HOLDOUT_CUTOFF
    n_train = int(keep.sum())
    n_live = int((~keep).sum())
    if n_train == 0:
        raise RuntimeError(
            f"这份文件整份都在切点 {HOLDOUT_CUTOFF} 之后：训练段是空的，切不了。")
    if n_live == 0:
        raise RuntimeError(
            f"这份文件整份都在切点 {HOLDOUT_CUTOFF} 之前：实时段是空的，切不了。")

    out.mkdir(parents=True, exist_ok=True)
    for name, mask in ((TRAIN_NAME, keep), (LIVE_NAME, ~keep)):
        part = dict(sheets)                    # 其余 sheet（字典/说明）原样带过去
        part[C.SHEET_MAIN] = main.iloc[mask]
        part[C.SHEET_QUALITY] = quality.iloc[mask]
        with pd.ExcelWriter(out / name) as w:
            for sheet, df in part.items():
                df.to_excel(w, sheet_name=sheet, index=False)

    _check(out, n_src=len(main), n_train=n_train, n_live=n_live)
    return n_train, n_live


def _check(out: pathlib.Path, *, n_src: int, n_train: int, n_live: int) -> None:
    """写完**读回来**自检。断言的是结构性质，不是 1164/144 那两个数 ——
    那两个数属于交付数据集，而这条命令对任何数据集都该成立。"""
    train = load_dataset(out / TRAIN_NAME)
    live = load_dataset(out / LIVE_NAME)
    if len(train.wide) != n_train or len(live.wide) != n_live:
        raise RuntimeError("写出去的行数与切分结果对不上。")
    if n_train + n_live != n_src:
        raise RuntimeError("两份并起来不等于源文件的行数。")
    for name, ds in ((TRAIN_NAME, train), (LIVE_NAME, live)):
        if ds.fix.fixed_indices:
            raise RuntimeError(f"{name} 里还有 {len(ds.fix.fixed_indices)} 行没修好。")
        if not ds.fix.monotonic_before:
            raise RuntimeError(f"{name} 写出去的仍是没修过的轴。")
        if not ds.dict_layout():
            raise RuntimeError(f"{name} 的「测点字典」读不出任何坐标。")
    end = train.wide[C.COL_TIMESTAMP].max()
    start = live.wide[C.COL_TIMESTAMP].min()
    if not end < start:
        raise RuntimeError(f"两份在切点上重叠了：训练段到 {end}，实时段从 {start}。")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="切出页⑤ 自己的两份数据源。")
    ap.add_argument("--src", type=pathlib.Path, default=None,
                    help="源 xlsx（默认：仓库根下那份交付数据集）")
    ap.add_argument("--out", type=pathlib.Path, default=None,
                    help="输出目录（默认：backend/configs/live/）")
    a = ap.parse_args(argv)
    src = a.src or paths.dataset_path()
    out = a.out or paths.LIVE_DIR
    if not src.exists():
        print(f"源文件不在：{src}", file=sys.stderr)
        return 2
    n_train, n_live = make_live_source(src, out)
    print(f"{out / TRAIN_NAME}  {n_train} 行")
    print(f"{out / LIVE_NAME}  {n_live} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
