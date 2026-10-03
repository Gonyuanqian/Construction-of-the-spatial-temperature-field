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

⚠️ 包还得**确实属于那个旧数据集**（`dataset_sig` == 旧数据集现在的指纹）。
    包在、新旧数据集也一样，但旧数据集在标定之后被重新导出过 ——
    这种情况下那套参数早就失效了，同样必须拒绝。

**删除规则**：只清理**新数据集所属项目目录里**的旧包。
    判据是「数据集在哪」，**不是**调用方给的 `--bundle` 说在哪 ——
    后者可以被误指到旧项目的 configs/ 上，那一刀就落在别人几十分钟的
    标定成果上，而且不可逆。
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


def is_within(child: pathlib.Path, parent: pathlib.Path) -> bool:
    """child 是否在 parent 这棵树里面。"""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


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

    raw = json.loads(old_bundle.read_text(encoding="utf-8"))

    # 2) 包必须**确实属于这个旧数据集**。
    #
    # 上一步只证明了「新旧数据集内容相同」，没说包跟旧数据集对得上。
    # 旧数据集若在标定之后被重新导出过（哪怕只是多了一行），它的指纹就变了，
    # 包里那套参数对当前数据已经失效 —— 而 `CalibrationBundle.matches()` 不会拦，
    # 因为指纹是**本脚本自己新算的**，一路放行、不报任何错。
    old_sig = dataset_signature(old_ds)
    if raw.get("dataset_sig") != old_sig:
        print("拒绝迁移：这份标定包不是这个数据集标出来的。", file=sys.stderr)
        print(f"  包里的 dataset_sig：{raw.get('dataset_sig')}", file=sys.stderr)
        print(f"  旧数据集现在的指纹：{old_sig}", file=sys.stderr)
        print("  旧数据集在标定之后变过，参数对它已经失效，必须重新标定。",
              file=sys.stderr)
        return 2

    # 3) 指纹必须在数据集**已经落到最终位置之后**算 —— mtime 是指纹的一部分
    new_sig = dataset_signature(new_ds)

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

    # 4) 清理旧包 —— 两道条件都满足才删。
    #
    # (a) 同一个目录：新旧包写在同一个 configs/ 里，才谈得上「清掉旧的」。
    # (b) 同一个项目：那个目录得在**新数据集所属的项目**里。
    #
    # 只看 (a) 是不够的，而且是危险的：`expected.parent` 完全来自调用方给的
    # `--bundle`，把它误指到旧项目的 configs/（它的语义是「新包写到哪」，
    # 而重迁移时最顺手的写法正是「写回原处」），(a) 就成立了，
    # unlink 直接落在旧项目那份不可逆的标定成果上。
    # 所以 (b) 的判据取**数据集的位置**，那是调用方没法用 --bundle 绕开的。
    same_dir = old_bundle.parent.resolve() == expected.parent.resolve()
    same_project = is_within(old_bundle.parent, new_ds.parent)

    if same_dir and same_project and old_bundle != expected and old_bundle.exists():
        old_bundle.unlink()
        print(f"  已删除旧包 {old_bundle}")
    elif old_bundle.exists():
        print(f"  旧包原样保留（不在新数据集所属的项目目录内）：{old_bundle}")
    print(f"\n迁移完成：{expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
