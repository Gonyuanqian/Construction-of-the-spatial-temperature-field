"""标定包迁移的契约。

最重要的一条是**拒绝**：内容不同的数据集绝不允许继承别人的参数。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "relocate_bundle.py"
BACKEND = pathlib.Path(__file__).resolve().parents[1]

# 一份最小的合法标定包 —— 只要字段都在，迁移脚本不关心值的语义
MINIMAL_BUNDLE = {
    "dataset_sig": "0000000000000000",
    "groups_sig": "d6294c09",
    "created_at": "2026-10-03T13:22:00+00:00",
    "tool_version": "0.1.0",
    "feature_groups": ["coord", "zbasis", "meteo", "interaction"],
    "trend_kind": "xgboost",
    "trend_params": {"n_estimators": 300},
    "metric": {"a": 0.1, "b": 0.1, "c": 0.1},
    "cross_shed": False,
    "tuned_keys": ["Lx"],
    "search": {"trials": []},
    "folds": ["position:x0.15_z0.4"],
    "metrics": [],
    "per_point": [],
    "ab": {"mae_a": 0.1, "mae_b": 0.2, "gap": -0.1},
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # 同 test_sync_backend.py：Windows 控制台 cp936，强制子进程走 utf-8。
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


def _fixture(tmp_path: pathlib.Path, *, same_content: bool = True):
    """造一组 (旧数据集, 旧包, 新数据集, 目标包路径)。"""
    old_ds = tmp_path / "old" / "数据.xlsx"
    old_ds.parent.mkdir(parents=True)
    old_ds.write_bytes(b"PK\x03\x04 fake xlsx payload")

    new_ds = tmp_path / "new" / "数据.xlsx"
    new_ds.parent.mkdir(parents=True)
    new_ds.write_bytes(b"PK\x03\x04 fake xlsx payload"
                       if same_content else b"PK\x03\x04 DIFFERENT payload")

    old_bundle = tmp_path / "old" / "configs" / "bundle_0000000000000000_d6294c09.json"
    old_bundle.parent.mkdir(parents=True)
    old_bundle.write_text(json.dumps(MINIMAL_BUNDLE, ensure_ascii=False),
                          encoding="utf-8")
    return old_ds, old_bundle, new_ds


def test_内容相同则迁移成功且除指纹外逐字段不变(tmp_path):
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr

    written = json.loads(
        next((new_ds.parent / "configs").glob("bundle_*_d6294c09.json"))
        .read_text(encoding="utf-8"))
    assert written["dataset_sig"] != "0000000000000000", "指纹必须被改写成新数据集的"
    for key, value in MINIMAL_BUNDLE.items():
        if key == "dataset_sig":
            continue
        assert written[key] == value, f"字段 {key} 不该被改动"


def test_内容不同则拒绝且磁盘上什么都不留(tmp_path):
    """Review Focus #2 —— 这一条是整套迁移的安全阀。

    ⚠️ 必须断言**拒绝的理由**，不能只看退出码：脚本压根不存在时返回的也是 2，
    而「没跑过」跟「跑过并拒绝了」都让 configs/ 不存在 —— 只验退出码与目录
    的话，这条最重要的测试在实现之前就通过了，等于没测。
    """
    old_ds, old_bundle, new_ds = _fixture(tmp_path, same_content=False)
    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "拒绝迁移" in r.stderr, "拒绝的理由要写在 stderr 上，不能只给个退出码"
    assert "内容不一致" in r.stderr
    cfg = new_ds.parent / "configs"
    assert not cfg.exists() or list(cfg.iterdir()) == [], "拒绝时不许留下任何文件"
    # 旧包也必须原封不动 —— 拒绝是「什么都不做」，不是「做了一半」
    assert old_bundle.read_text(encoding="utf-8") == json.dumps(
        MINIMAL_BUNDLE, ensure_ascii=False)


def test_不带_apply_时不写盘(tmp_path):
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds))
    assert r.returncode == 1
    assert not new_bundle.exists()


def test_同一个_configs_内的旧包被清掉(tmp_path):
    """否则 configs/ 里会留一个永远匹配不上的死包，误导后来的人。"""
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    _run("--bundle", str(old_bundle), "--dataset", str(new_ds),
         "--original", str(old_bundle), "--original-dataset", str(old_ds),
         "--apply")
    assert not old_bundle.exists()


def test_旧包在另一个目录时绝不删除(tmp_path):
    """旧项目零改动（spec §〇/§九）。

    这是 P1 的实际情形：--original 指向 ../空间温度场的构建/configs/…。
    那条路径上躺着别人的标定成果（几十分钟的训练），删了不可逆。
    本条钉住「清理只发生在同一个 configs/ 目录内」。
    """
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert old_bundle.exists(), "旧项目里的标定包被删了 —— 这是不可逆的"
    assert old_bundle.read_text(encoding="utf-8") == json.dumps(
        MINIMAL_BUNDLE, ensure_ascii=False), "旧包被改动了"


# ── 端到端：Review Focus #3（指纹与复制的先后顺序）──
_REAL_DS = BACKEND / "人参棚_多棚温湿度_气象时间对齐数据集.xlsx"
_SOURCE_ROOT = BACKEND.parent.parent / "空间温度场的构建"
_HAS_REAL = _REAL_DS.exists() and (_SOURCE_ROOT / "configs").is_dir()


@pytest.mark.skipif(not _HAS_REAL, reason="需要真实数据集与旧项目的标定包")
def test_真实的标定包迁移后_load_for_找得到(tmp_path):
    """这一条同时钉死两件事：
    (a) 迁移真的能让 load_for 找到包；
    (b) 指纹是在数据集**已经落到最终位置之后**算的 ——
        先算指纹后复制，mtime 一变指纹就过期，load_for 依然返回 None，
        而脚本会报告成功。只有真的调一次 load_for 才能发现。
    """
    from tfield.calibration import load_for
    from tfield.config import DEFAULT_FEATURE_GROUPS
    from tfield.data.loader import load_dataset

    cfg = tmp_path / "configs"
    cfg.mkdir()
    shutil.copy(_REAL_DS, tmp_path / _REAL_DS.name)
    ds_path = tmp_path / _REAL_DS.name

    old_bundle = next((_SOURCE_ROOT / "configs").glob("bundle_*_d6294c09.json"))
    old_ds_path = _SOURCE_ROOT / _REAL_DS.name

    r = _run("--bundle", str(cfg / "bundle_X_d6294c09.json"), "--dataset", str(ds_path),
             "--original", str(old_bundle), "--original-dataset", str(old_ds_path),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr

    ds = load_dataset(ds_path)
    bundle = load_for(ds, DEFAULT_FEATURE_GROUPS, root=cfg)
    assert bundle is not None, "迁移后 load_for 仍然找不到包 —— 指纹或顺序错了"
    assert bundle.created_at == json.loads(
        old_bundle.read_text(encoding="utf-8"))["created_at"], "created_at 不该被改写"
