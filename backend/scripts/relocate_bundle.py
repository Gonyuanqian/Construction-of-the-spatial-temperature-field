"""把标定包迁到一个新位置的同名数据集上。

**为什么需要**
    `dataset_signature(path)` = `sha1(f"{绝对路径}|{mtime_ns}|{大小}")[:16]`
    —— **绝对路径是数据集身份的一部分**。项目一复制，数据集的路径就变了，
    指纹跟着变，`load_for` 就再也找不到那个包（文件名里嵌了指纹，
    就算文件名对上了，`CalibrationBundle.matches()` 也会拦下）。
    界面上表现为「还没有标定包」。

**为什么可以迁**
    如果两份数据集的**内容逐字节相同**，参数就仍然适用 —— 差的只有路径与 mtime，
    而那两个是**缓存失效机制**，不是数据身份的语义。本脚本先用 sha256 证明内容相同。

⚠️ 内容不同就**拒绝**，一个字节都不写。内容变了必须重标，不许迁移 ——
    那正是 `load_for` 返回 None 本来想拦住的事。

**删除规则**：只清理**同一个 `configs/` 目录内**的旧包。
跨项目迁移（`--original` 指向另一个项目）时旧包原样保留 ——
那个项目必须零改动，而那些文件是别人几十分钟的标定成果，删了不可逆。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from tfield.data.loader import dataset_signature          # noqa: E402


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="标定包跨目录迁移")
    ap.add_argument("--bundle", required=True, help="新位置的目标包路径")
    ap.add_argument("--dataset", required=True, help="新位置的数据集")
    ap.add_argument("--original", required=True, help="旧位置的标定包")
    ap.add_argument("--original-dataset", required=True, help="旧位置的数据集")
    ap.add_argument("--apply", action="store_true", help="真的写盘；不带则只打印")
    args = ap.parse_args(argv)

    new_ds = pathlib.Path(args.dataset)
    old_ds = pathlib.Path(args.original_dataset)
    old_bundle = pathlib.Path(args.original)
    target = pathlib.Path(args.bundle)

    for name, p in (("新数据集", new_ds), ("旧数据集", old_ds), ("旧标定包", old_bundle)):
        if not p.exists():
            print(f"{name}不存在：{p}", file=sys.stderr)
            return 2

    # 1) 内容必须逐字节相同 —— 这是整个迁移的合法性依据
    h_new, h_old = sha256_file(new_ds), sha256_file(old_ds)
    if h_new != h_old:
        print("拒绝迁移：两份数据集的内容不一致。", file=sys.stderr)
        print(f"  新：{h_new}\n  旧：{h_old}", file=sys.stderr)
        print("  内容变了就不是「搬了个家」，必须重新标定。", file=sys.stderr)
        return 2

    # 2) 指纹必须在数据集**已经落到最终位置之后**算 —— mtime 是指纹的一部分
    new_sig = dataset_signature(new_ds)

    raw = json.loads(old_bundle.read_text(encoding="utf-8"))
    groups_sig = raw["groups_sig"]
    expected = target.parent / f"bundle_{new_sig}_{groups_sig}.json"

    migrated = dict(raw)
    migrated["dataset_sig"] = new_sig

    print(f"数据集内容一致（sha256 {h_new[:16]}…）")
    print(f"  旧指纹：{raw['dataset_sig']}")
    print(f"  新指纹：{new_sig}")
    print(f"  旧包：{old_bundle.name}")
    print(f"  新包：{expected.name}")
    print(f"  除 dataset_sig 外，其余 {len(raw) - 1} 个字段逐字保留"
          f"（created_at = {raw['created_at']} 不改）")

    if not args.apply:
        print("\n加 --apply 才真的写。")
        return 1

    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_text(json.dumps(migrated, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    # 3) 清理旧包 —— **只在同一个 configs/ 目录里才清理**。
    #
    # 跨项目迁移时旧包住在**另一个项目**里（P1 的实际情形：
    # --original ../空间温度场的构建/configs/…）。那个项目必须零改动，
    # 删掉它就等于抹掉别人几十分钟的标定成果，而且不可逆。
    # 同一目录内的重迁移（数据集在项目内挪了位置）才该清理 ——
    # 否则 configs/ 里留一个永远匹配不上的死包，误导后来的人。
    if old_bundle.parent == expected.parent and old_bundle != expected \
            and old_bundle.exists():
        old_bundle.unlink()
        print(f"  已删除旧包 {old_bundle}")
    elif old_bundle.exists() and old_bundle.parent != expected.parent:
        print(f"  旧包在另一个目录，原样保留：{old_bundle}")
    print(f"\n迁移完成：{expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
