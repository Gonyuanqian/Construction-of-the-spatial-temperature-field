"""两棵 tfield 树之间的保真校验与显式同步。

`tfield` 是这个项目最值钱的东西，它可能在别的地方也有一份，两份一定会漂。
目标不是阻止漂移（用户可能就是想在这边改着玩），是让漂移**在任何时候都看得见**。

方向：A = 另一棵树，B = 本仓的 `backend/src/tfield`。`--push` 是 A → B，
`--pull` 是 B → A。

⚠️ **`--a` 必填，没有推算出来的默认值。** 两棵树相邻只是个巧合，
而这个工具猜错一棵树的代价是覆盖掉另一侧的成果 —— 那比当场报错贵得多。

⚠️ 写盘一律要 `--apply`。不带就是干跑，但退出码仍然反映差异。
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import sys

SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}

#: **已知有意差异**：相对路径 → 一句为什么。
#:
#: 「只改本仓这一份」的代价必须认：两份 `tfield` 从此有意不同，而
#: 这个工具因此从报警器变成一把上膛的枪 —— `--push` 会静默覆盖掉实时构场能力。
#: 这份清单是那个代价的安全阀：已知的差异明写出来，**其余任何差异照旧报警**。
#:
#: ⚠️ 只列**文件**，不列行。行级白名单会让「清单内文件的新漂移」也悄悄通过 ——
#: 那时清单就不是安全阀，而是一张免死金牌。
#:
#: 计划原本算的是三条。Task 9 追加了第四条 `field/constraints.py`（见下）——
#: 它不在计划枚举的范围里，是**接完实时帧再算场**时才暴露的：`light_at` 直接读
#: `ds.wide[C.BG_LIGHT].iloc[t_index]`，而实时帧不在宽表里。
#:
#: 2026-10-06 页① 改版又追加了最后两条（用户裁定：那排卡片换成
#: 样本数 / 样本时间范围 / 缺失样本量 / 重复样本量）。「重复样本量」要报
#: **原始文件**里的重复时刻数，而修复前的轴在 `repair_axis` 里用完就丢了 ——
#: 要留住它，公开类型 `FixReport` 得多一个字段。那一个决定同时落在两个文件上，
#: 是这次改版唯一动到库的地方。
#: （`api/` 是本仓自己的邻居包，不在 `sync_backend.py` 的比较范围里。）
KNOWN_DIVERGENCES: dict[str, str] = {
    "data/loader.py":
        "本仓这一份多了留出切分 split_holdout / derived_signature（实时模式用）",
    "pipeline.py":
        "本仓这一份多了 append_live_frame、时间轴访问器 n_times / timestamps /"
        " time_at 与 bg_light_at",
    "artifact.py":
        "本仓这一份多了整个文件：训练好的模型的成品字节格式（模型库存成品用）。"
        "另一棵树不存成品 —— 它每页现训。与 pipeline.py 那一条同性质："
        "本仓多出来的东西，是有意的。",
    "validation/report.py":
        "本仓这一份的 ti 用 len(ds.wide) 而不是写死的 C.EXPECTED_ROWS"
        "（训练段只有 1164 行）；本仓这一份多了 out_of_fold_predictions 与"
        " OOF_COLUMNS（页② 的精度图表要逐点逐时刻的折外预测，而 evaluate 只留聚合）",
    "field/constraints.py":
        "本仓这一份的 light_at 走 pipe.bg_light_at 而不是 ds.wide.iloc"
        "（实时帧不在宽表里）",
    "data/types.py":
        "本仓这一份的 FixReport 多了 duplicate_count（页① 要报原始文件的重复时刻数）",
    "data/timestamp.py":
        "本仓这一份在 repair_axis 里数原始轴的重复时刻，填进 FixReport",
}


def changed_keys(a: dict[str, str], b: dict[str, str]) -> list[str]:
    """有差异（只在一边或内容不同）的相对路径。"""
    out: list[str] = []
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b or a[key] != b[key]:
            out.append(key)
    return out


def tree_hashes(root: pathlib.Path | str) -> dict[str, str]:
    """相对路径 → 文件内容的 sha256。跳过缓存目录与字节码。

    只比内容，不比 mtime —— 复制会让所有 mtime 变掉，拿它比会满屏假差异。
    """
    root = pathlib.Path(root)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix in SKIP_SUFFIXES:
            continue
        parts = p.relative_to(root).parts
        if any(part in SKIP_DIR_NAMES for part in parts):
            continue
        out["/".join(parts)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def diff(a: dict[str, str], b: dict[str, str]) -> list[str]:
    """人类可读的差异行。空列表 = 两份一致。"""
    lines: list[str] = []
    for key in sorted(set(a) | set(b)):
        if key not in a:
            lines.append(f"  只在 B（本仓这一棵）：{key}")
        elif key not in b:
            lines.append(f"  只在 A（另一棵树）：{key}")
        elif a[key] != b[key]:
            lines.append(f"  内容不同：{key}")
    return lines


def main(argv: list[str] | None = None) -> int:
    here = pathlib.Path(__file__).resolve()
    # here = <本仓>/backend/scripts/sync_backend.py
    project = here.parents[2]                       # <本仓>
    ap = argparse.ArgumentParser(description="两棵 tfield 树的保真校验与同步")
    ap.add_argument("--a", required=True,
                    help="另一棵树（必填；本工具不猜路径）")
    ap.add_argument("--b", default=str(project / "backend" / "src" / "tfield"),
                    help="本仓这一棵（默认就是它）")
    ap.add_argument("--check", action="store_true", help="只校验（默认动作）")
    ap.add_argument("--push", action="store_true", help="A → B")
    ap.add_argument("--pull", action="store_true", help="B → A")
    ap.add_argument("--apply", action="store_true", help="真的写盘；不带则只打印")
    ap.add_argument("--overwrite-known", action="store_true",
                    help="--push 时连**已知有意差异**的文件一起覆盖（默认拒绝）")
    ap.add_argument("--include-known", action="store_true",
                    help="--pull 时连**已知有意差异**的文件一起搬（默认排除）")
    args = ap.parse_args(argv)

    a_dir, b_dir = pathlib.Path(args.a), pathlib.Path(args.b)
    for name, d in (("另一棵树 A", a_dir), ("本仓这一棵 B", b_dir)):
        if not d.is_dir():
            print(f"{name} 目录不存在：{d}", file=sys.stderr)
            return 2

    hashes_a, hashes_b = tree_hashes(a_dir), tree_hashes(b_dir)
    lines = diff(hashes_a, hashes_b)
    keys = changed_keys(hashes_a, hashes_b)
    known = [k for k in keys if k in KNOWN_DIVERGENCES]
    other = [k for k in keys if k not in KNOWN_DIVERGENCES]

    if not lines:
        print(f"无差异：{a_dir} 与 {b_dir}")
        return 0

    print(f"两份 tfield 有 {len(lines)} 处差异：")
    print("\n".join(lines))

    if known:
        print(f"\n其中 {len(known)} 处是**已知有意差异**（清单在 scripts/sync_backend.py）：")
        for k in known:
            print(f"  {k} —— {KNOWN_DIVERGENCES[k]}")
    if other:
        print(f"\n另有 {len(other)} 处**意外差异**（清单之外，这才是要看的）：")
        print("\n".join(f"  {k}" for k in other))

    if not (args.push or args.pull):
        if not other:
            print("\n清单之外的差异一处都没有。")
            return 0
        print("\n加 --push（A → B）或 --pull（B → A）可以同步；不带 --apply 只打印。")
        return 1

    src, dst, hashes = (a_dir, b_dir, hashes_a) if args.push else (b_dir, a_dir, hashes_b)
    verb = "A → B" if args.push else "B → A"

    # 清单是安全阀，不是免死金牌：它放行「两份不同」，但**不许**顺手变成
    # 「谁都能拿 A 盖掉 B」—— 那正是它要防的事。B 侧那几处差异就是实时构场能力
    # 本身（留出切分、append_live_frame、光照门禁的访问器），拿 A 盖掉就是把它删了，
    # 而且删得没有任何报错。
    if args.push and not args.overwrite_known:
        hit = [k for k in keys if k in KNOWN_DIVERGENCES]
        if hit:
            print("\n拒绝 --push：下面这些文件是**已知有意差异**，覆盖它们会抹掉"
                  "实时构场能力：")
            for k in hit:
                print(f"  {k} —— {KNOWN_DIVERGENCES[k]}")
            print("\n确实要覆盖请显式加 --overwrite-known。")
            return 1

    # 反方向同理：`--pull` 是拿 B 盖 A，而清单内的差异**只该留在 B**。
    # 默认排除，要搬得自己说。
    if args.pull and not args.include_known:
        excluded = [k for k in keys if k in KNOWN_DIVERGENCES]
        keys = [k for k in keys if k not in KNOWN_DIVERGENCES]
        if excluded:
            print(f"\n--pull 默认排除 {len(excluded)} 个清单内的文件"
                  f"（要一起搬请加 --include-known）：{excluded}")

    if not args.apply:
        print(f"\n上面这些就是 {verb} 会做的改动。加 --apply 才真的写。")
        return 1

    # **只搬 `keys` 里的，且源里也得有**（上面可能已经把清单内的滤掉了）：
    # - 原来是遍历 `hashes` 的全集，那等于把清单内的文件也一起搬走，
    #   `--pull` 的排除就成了摆设；
    # - 但也不能只按 `keys` 走：`keys` 里有**只在对面**的文件（单向同步不做删除），
    #   `copy2(A / "只在B" )` 是 FileNotFoundError —— 那是把「不删除」写成了崩溃。
    moved = [k for k in keys if k in hashes]
    for key in moved:
        d = dst / key
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / key, d)
    print(f"\n已按 {verb} 覆盖 {len(moved)} 个文件（只搬运，不删除）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
