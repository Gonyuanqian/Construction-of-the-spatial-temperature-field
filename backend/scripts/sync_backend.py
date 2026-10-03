"""两份 tfield 副本的保真校验与显式同步。

`tfield` 是这个项目最值钱的东西，Vue 版复制了一份出去，两份一定会漂。
目标不是阻止漂移（用户可能就是想在这边改着玩），是让漂移**在任何时候都看得见**。

方向：A = 真源（旧项目的 `src/tfield`），B = 副本（新项目的 `backend/src/tfield`）。
`--push` 是 A → B，`--pull` 是 B → A。

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
            lines.append(f"  只在 B（副本）：{key}")
        elif key not in b:
            lines.append(f"  只在 A（真源）：{key}")
        elif a[key] != b[key]:
            lines.append(f"  内容不同：{key}")
    return lines


def main(argv: list[str] | None = None) -> int:
    here = pathlib.Path(__file__).resolve()
    # here = <新项目>/backend/scripts/sync_backend.py
    project = here.parents[2]                       # <新项目>
    desktop = project.parent
    ap = argparse.ArgumentParser(description="两份 tfield 副本的保真校验与同步")
    ap.add_argument("--a", default=str(desktop / "空间温度场的构建" / "src" / "tfield"),
                    help="真源（旧项目），默认按两个项目相邻推算")
    ap.add_argument("--b", default=str(project / "backend" / "src" / "tfield"),
                    help="副本（新项目）")
    ap.add_argument("--check", action="store_true", help="只校验（默认动作）")
    ap.add_argument("--push", action="store_true", help="A → B")
    ap.add_argument("--pull", action="store_true", help="B → A")
    ap.add_argument("--apply", action="store_true", help="真的写盘；不带则只打印")
    args = ap.parse_args(argv)

    a_dir, b_dir = pathlib.Path(args.a), pathlib.Path(args.b)
    for name, d in (("真源 A", a_dir), ("副本 B", b_dir)):
        if not d.is_dir():
            print(f"{name} 目录不存在：{d}", file=sys.stderr)
            return 2

    hashes_a, hashes_b = tree_hashes(a_dir), tree_hashes(b_dir)
    lines = diff(hashes_a, hashes_b)
    if not lines:
        print(f"无差异：{a_dir} 与 {b_dir}")
        return 0

    print(f"两份 tfield 有 {len(lines)} 处差异：")
    print("\n".join(lines))

    if not (args.push or args.pull):
        print("\n加 --push（A → B）或 --pull（B → A）可以同步；不带 --apply 只打印。")
        return 1

    src, dst, hashes = (a_dir, b_dir, hashes_a) if args.push else (b_dir, a_dir, hashes_b)
    verb = "A → B" if args.push else "B → A"
    if not args.apply:
        print(f"\n上面这些就是 {verb} 会做的改动。加 --apply 才真的写。")
        return 1

    for key in hashes:
        d = dst / key
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / key, d)
    print(f"\n已按 {verb} 覆盖 {len(hashes)} 个文件（只搬运，不删除）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
