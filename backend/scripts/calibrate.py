"""离线标定 CLI：位置二分 + 交替优化，产出 configs/bundle_<sig>_<groups>.json。

**不是运行时阶段。** 前端调的是 `tfield.calibration.calibrate_or_load()`，
本脚本只是它的一层 argparse 外壳 —— 命令行与前端跑的是同一份代码，
不存在「脚本里修好了、界面里没修」这种分叉。

阶段 1（秒级）：冻结趋势（兜底），把 IDW 扫透。
    残差**不依赖 IDW 参数** —— 每折的趋势只训练一次、缓存残差，
    之后每组参数只是一次加权求和。整片扫描秒级完成。
阶段 2（分钟级）：冻结 IDW，随机搜趋势参数。每次试验重训 4 折，用 --trials 调（默认 40）。
阶段 3（秒级）：在新趋势参数下回头再扫一次 IDW，确认最优没移动。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tfield import config as C                                      # noqa: E402
from tfield.calibration import (bundle_path, cache_folds,           # noqa: E402
                                calibrate_or_load, groups_signature,
                                plateau_of, sweep_idw)
from tfield.data.loader import load_dataset                         # noqa: E402
from tfield.features import build_features                          # noqa: E402
from tfield.pipeline import PipelineConfig                          # noqa: E402
from tfield.validation.folds import position_folds                  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="人参棚温度场后端标定")
    ap.add_argument("--data", default=str(Path(C.DATA_FILENAME)))
    ap.add_argument("--out", default="configs")
    ap.add_argument("--groups", default=",".join(C.DEFAULT_FEATURE_GROUPS),
                    help="逗号分隔的特征组；改了它就得重标，产物文件名会不同")
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--force", action="store_true", help="忽略已有标定包，重跑一遍")
    ap.add_argument("--stage1-only", action="store_true",
                    help="只扫 IDW 并写出参数曲面，不写标定包")
    args = ap.parse_args()

    ds = load_dataset(args.data)
    groups = tuple(g.strip() for g in args.groups.split(",") if g.strip())

    if args.stage1_only:
        fs = build_features(ds, groups)
        folds = position_folds(ds)
        a_folds = [f for f in folds if f.group == "A"]
        print(f"数据集指纹 {ds.signature}；特征组 {groups}（{groups_signature(groups)}）")
        print(f"A 组 {len(a_folds)} 折（选参）/ B 组 {len(folds) - len(a_folds)} 折（报数）")
        cached = cache_folds(ds, fs, a_folds, PipelineConfig.fallback(), progress=print)
        surface = sweep_idw(cached, progress=print)
        best = surface.iloc[0].to_dict()
        print(f"阶段 1 最优 MAE {best['mae']:.4f} @ power={best['power']} lx={best['lx']} "
              f"lz={best['lz']} cross_shed={best['cross_shed']}")
        print(f"平台（最优 +1% 以内）：{plateau_of(surface, ('power', 'lx', 'lz'))}")
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        csv = out / f"sensitivity_{ds.signature}_{groups_signature(groups)}.csv"
        surface.assign(stage=1).to_csv(csv, index=False, encoding="utf-8-sig")
        print(f"参数曲面已写入 {csv}；仅阶段 1，未写标定包。")
        return 0

    p = bundle_path(ds.signature, groups, args.out)
    cached = p.exists() and not args.force
    bundle = calibrate_or_load(ds, groups, n_trials=args.trials,
                               root=args.out, force=args.force, progress=print)
    p = bundle_path(bundle.dataset_sig, bundle.feature_groups, args.out)
    # calibrate_or_load 命中缓存时不会重算，说「已写入」是假话 —— 分开报。
    print(f"\n{'命中已有标定包，未重算' if cached else '已重新标定并写入'} {p}")
    if cached:
        print("（要重跑请加 --force）")
    print(f"特征组 {list(bundle.feature_groups)}（{bundle.groups_sig}）")
    print(f"A 组 {bundle.ab['mae_a']:.4f} / B 组 {bundle.ab['mae_b']:.4f} "
          f"→ 乐观偏差 {bundle.ab['gap']:+.4f} °C")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
