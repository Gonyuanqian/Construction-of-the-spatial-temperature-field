"""标定包迁移的契约。

最重要的一条是**拒绝**：内容不同的数据集绝不允许继承别人的参数。
第二重要的一条也是拒绝：**绝不许删掉别人项目里的包**。
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

sys.path.insert(0, str(BACKEND / "src"))
from tfield.data.loader import dataset_signature          # noqa: E402

PAYLOAD = b"PK\x03\x04 fake xlsx payload"

# 一份最小的合法标定包 —— 只要字段都在，迁移脚本不关心值的语义
MINIMAL_BUNDLE = {
    "dataset_sig": "0000000000000000",   # 每个 fixture 会替换成旧数据集的**真**指纹
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


def _write_bundle(path: pathlib.Path, sig: str) -> str:
    """写一份 dataset_sig = sig 的包，返回它写下去的原文。"""
    text = json.dumps({**MINIMAL_BUNDLE, "dataset_sig": sig}, ensure_ascii=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def _fixture(tmp_path: pathlib.Path, *, same_content: bool = True):
    """一组 (旧数据集, 旧包, 新数据集)，**跨目录**：模拟项目搬家。

    ⚠️ 包里的 `dataset_sig` 必须是旧数据集的**真指纹**：脚本现在会核对这一点
    （见 `test_包与旧数据集对不上时拒绝`）。随手编一个假值会直接撞在那条上，
    于是这条 fixture 下的每个测试都在测别的失败，而不是它自己的断言。
    """
    old_ds = tmp_path / "old" / "数据.xlsx"
    old_ds.parent.mkdir(parents=True)
    old_ds.write_bytes(PAYLOAD)

    new_ds = tmp_path / "new" / "数据.xlsx"
    new_ds.parent.mkdir(parents=True)
    new_ds.write_bytes(PAYLOAD if same_content else b"PK\x03\x04 DIFFERENT payload")

    sig = dataset_signature(old_ds)
    old_bundle = old_ds.parent / "configs" / f"bundle_{sig}_d6294c09.json"
    _write_bundle(old_bundle, sig)
    return old_ds, old_bundle, new_ds


def test_内容相同则迁移成功且除指纹外逐字段不变(tmp_path):
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    old_sig = dataset_signature(old_ds)
    before = json.loads(old_bundle.read_text(encoding="utf-8"))

    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr

    written = json.loads(
        next((new_ds.parent / "configs").glob("bundle_*_d6294c09.json"))
        .read_text(encoding="utf-8"))
    assert written["dataset_sig"] != old_sig, "指纹必须被改写成新数据集的"
    for key, value in before.items():
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
    before = old_bundle.read_text(encoding="utf-8")
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
    assert old_bundle.read_text(encoding="utf-8") == before


def test_包与旧数据集对不上时拒绝(tmp_path):
    """Review Focus #2 的另一面（审阅 Important #2）。

    前面那条只比「新旧数据集内容是否相同」。但还有一种情况：
    包在、新旧数据集也确实一样，而这**根本不是这个数据集标出来的包** ——
    旧数据集在标定之后被重新导出过，指纹早就变了，包里那套参数对它已经失效。
    `CalibrationBundle.matches()` 不会拦（指纹是脚本自己新算的），
    所以必须在这里拦：包里的 dataset_sig 得等于**旧数据集现在**的指纹。
    """
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    tampered = json.loads(old_bundle.read_text(encoding="utf-8"))
    tampered["dataset_sig"] = "deadbeefdeadbeef"     # 与旧数据集现在的指纹对不上
    old_bundle.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "拒绝迁移" in r.stderr
    assert "不是这个数据集标出来的" in r.stderr
    cfg = new_ds.parent / "configs"
    assert not cfg.exists() or list(cfg.iterdir()) == [], "拒绝时不许留下任何文件"


def test_不带_apply_时不写盘(tmp_path):
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds))
    assert r.returncode == 1
    assert not new_bundle.exists()


def test_同一个项目里重迁移会清掉旧包(tmp_path):
    """数据集在**项目内**挪了位置 → 旧的死包要清掉，
    否则 configs/ 里留一个永远匹配不上的包，误导后来的人。

    注意 fixture 的形状：新旧数据集同属一个项目目录，configs/ 在项目根下 ——
    这才是「同一个项目里重迁移」的样子。跨目录的那组见上面 `_fixture`。
    """
    proj = tmp_path / "proj"
    (proj / "configs").mkdir(parents=True)
    (proj / "data").mkdir()
    old_ds = proj / "data" / "数据.xlsx"
    old_ds.write_bytes(PAYLOAD)
    old_bundle = proj / "configs" / f"bundle_{dataset_signature(old_ds)}_d6294c09.json"
    _write_bundle(old_bundle, dataset_signature(old_ds))

    new_ds = proj / "数据.xlsx"          # 挪到项目根，configs/ 没动
    new_ds.write_bytes(PAYLOAD)

    r = _run("--bundle", str(proj / "configs" / "bundle_X_d6294c09.json"),
             "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not old_bundle.exists(), "项目内的旧包应该被清掉"
    assert len(list((proj / "configs").glob("bundle_*_d6294c09.json"))) == 1


def test_旧包在另一个目录时绝不删除(tmp_path):
    """原处零改动（spec §〇/§九）。

    这是搬家的实际情形：--original 指向**另一份工程**的 configs/…。
    那条路径上躺着别人的标定成果（几十分钟的训练），删了不可逆。
    """
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    before = old_bundle.read_text(encoding="utf-8")
    new_bundle = new_ds.parent / "configs" / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(new_bundle), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert old_bundle.exists(), "另一份工程里的标定包被删了 —— 这是不可逆的"
    assert old_bundle.read_text(encoding="utf-8") == before, "旧包被改动了"


def test_把_bundle_误指到别处也绝不删旧包(tmp_path):
    """审阅 Important #1 —— **这一条钉死那个不可逆的路径。**

    「删不删」原来是用 `old_bundle.parent == expected.parent` 判断的，
    而 `expected.parent` 完全来自调用方给的 `--bundle`。
    于是把 `--bundle` 误指到**别人那份工程**的 configs/ 里（它的语义是
    「新包写到哪」，而重迁移时最顺手的写法正是「写回原处」），两个 parent
    就相等了，unlink 落在别人那份不可逆的标定成果上。

    判据必须是**数据集在哪**，不是 `--bundle` 说在哪。
    """
    old_ds, old_bundle, new_ds = _fixture(tmp_path)
    before = old_bundle.read_text(encoding="utf-8")

    # 这正是最危险的调用：--bundle 落在别人那份工程的 configs/ 里
    misdirected = old_bundle.parent / "bundle_X_d6294c09.json"
    r = _run("--bundle", str(misdirected), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")

    assert old_bundle.exists(), (
        "别人那份工程的标定包被删了 —— 不可逆。删不删不能由调用方给的 --bundle 决定。")
    assert old_bundle.read_text(encoding="utf-8") == before, "旧包被改动了"


# ── 端到端：Review Focus #3（指纹与复制的先后顺序）──
#
# ⚠️ 用的是**本仓自带**的那份真实标定包的全套内容，只把它的 `dataset_sig`
# 换成下面那份副本的指纹。为什么非改一下不可：指纹里含 **mtime**，数据集被复制过
# 一次就对不上了 —— 不改的话这一条会因为「这份文件的 mtime 不是当初那一个」而跳过，
# 与它要钉的东西毫无关系。包里其余字段一个不动：下面那句 `load_for` 要吃的正是
# **真包的形状**，不是为测试编的壳。
_REAL_DS = BACKEND / "人参棚_多棚温湿度_气象时间对齐数据集.xlsx"
_REAL_BUNDLE = (BACKEND / "configs" /
                "bundle_6145fa9261e89f1b_d6294c09.json")


@pytest.mark.skipif(not (_REAL_DS.exists() and _REAL_BUNDLE.exists()),
                    reason="需要仓库下那份数据集与 configs/ 里那份真实标定包")
def test_真实的标定包迁移后_load_for_找得到(tmp_path):
    """这一条同时钉死三件事：
    (a) 迁移真的能让 load_for 找到包；
    (b) 指纹是在数据集**已经落到最终位置之后**算的 ——
        先算指纹后复制，mtime 一变指纹就过期，load_for 依然返回 None，
        而脚本会报告成功。只有真的调一次 load_for 才能发现；
    (c) 迁移出来的包 **`load_for` 真的吃得下** —— 不是只有迁移脚本认得它的 JSON。
    """
    from tfield.calibration import load_for
    from tfield.config import DEFAULT_FEATURE_GROUPS
    from tfield.data.loader import load_dataset

    old_ds = tmp_path / "old" / _REAL_DS.name
    new_ds = tmp_path / "new" / _REAL_DS.name
    for p in (old_ds, new_ds):
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_REAL_DS, p)

    old_bundle = old_ds.parent / "configs" / "bundle_9055b199eeee1293_d6294c09.json"
    old_bundle.parent.mkdir(parents=True, exist_ok=True)
    old_bundle.write_text(json.dumps(
        {**json.loads(_REAL_BUNDLE.read_text(encoding="utf-8")),
         "dataset_sig": dataset_signature(old_ds)}, ensure_ascii=False), encoding="utf-8")

    cfg = tmp_path / "configs"
    cfg.mkdir()
    r = _run("--bundle", str(cfg / "bundle_X_d6294c09.json"), "--dataset", str(new_ds),
             "--original", str(old_bundle), "--original-dataset", str(old_ds),
             "--apply")
    assert r.returncode == 0, r.stdout + r.stderr

    ds = load_dataset(new_ds)
    bundle = load_for(ds, DEFAULT_FEATURE_GROUPS, root=cfg)
    assert bundle is not None, "迁移后 load_for 仍然找不到包 —— 指纹或顺序错了"
    assert bundle.created_at == json.loads(
        old_bundle.read_text(encoding="utf-8"))["created_at"], "created_at 不该被改写"
