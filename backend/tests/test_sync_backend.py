"""保真校验器的契约：退出码与差异输出。

走 CLI（subprocess）而不是 import —— 这个工具的价值就在退出码，
测试要测的正是「人能不能靠退出码判断」。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "sync_backend.py"
BASE = {"config.py": "X = 1\n", "data/loader.py": "def f():\n    return 1\n"}


def _tree(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # Windows 控制台的默认编码是 cp936，子进程会把中文输出写成 GBK，
    # 用 utf-8 解码就崩在 helper 里 —— 那样测的是编码，不是契约。
    # 强制子进程走 utf-8；errors="replace" 只是兜底，免得解码错误
    # 把一条断言失败伪装成 TypeError。
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


def test_两份完全相同的树退出码为零(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", BASE)
    r = _run("--a", str(a), "--b", str(b), "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "无差异" in r.stdout


def test_内容不同时退出码非零并指出是哪个文件(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "config.py": "X = 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--check")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "config.py" in r.stdout


def test_只在一边存在的文件会被指出(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "extra.py": "pass\n"})
    r = _run("--a", str(a), "--b", str(b), "--check")
    assert r.returncode == 1
    assert "extra.py" in r.stdout


def test_缓存目录不参与比较(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", BASE)
    _tree(b, {"__pycache__/config.cpython-311.pyc": "junk",
              "data/__pycache__/loader.cpython-311.pyc": "junk"})
    assert _run("--a", str(a), "--b", str(b), "--check").returncode == 0


def test_push_不带_apply_只打印不写盘(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "config.py": "X = 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--push")
    assert r.returncode == 1
    assert (b / "config.py").read_text(encoding="utf-8") == "X = 2\n"   # 没被覆盖


def test_push_带_apply_把_A_覆盖到_B(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "config.py": "X = 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--push", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (b / "config.py").read_text(encoding="utf-8") == "X = 1\n"
    assert _run("--a", str(a), "--b", str(b), "--check").returncode == 0


def test_push_不会删掉只在_B_的文件(tmp_path):
    """单向同步只搬运，不删除 —— 删除是另一个决定，不该藏在 push 里。

    必须同时断言「该搬的搬了」：只断言 extra.py 还在的话，
    脚本根本没跑（或跑挂了）时这条也会通过 —— 那就什么都证明不了。
    """
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "extra.py": "pass\n",
                               "config.py": "X = 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--push", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (b / "config.py").read_text(encoding="utf-8") == "X = 1\n"  # 真的搬了
    assert (b / "extra.py").exists()                                  # 没被删


# ── 已知有意差异清单：挡住误覆盖 ──


def test_清单内的差异算已知_退出码为零(tmp_path):
    """`data/loader.py` 在清单里（实时模式的留出切分）。它俩不同**不该**报警。"""
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "data/loader.py": "def f():\n    return 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "已知" in r.stdout
    assert "data/loader.py" in r.stdout


def test_清单外的差异照旧非零(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "other.py": "pass\n"})
    r = _run("--a", str(a), "--b", str(b), "--check")
    assert r.returncode == 1
    assert "other.py" in r.stdout


def test_两种差异混在一起时_仍然非零(tmp_path):
    """**这条最要紧**：意外漂移不许躲在已知差异后面。"""
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE,
                               "data/loader.py": "def f():\n    return 2\n",
                               "other.py": "pass\n"})
    r = _run("--a", str(a), "--b", str(b), "--check")
    assert r.returncode == 1
    assert "loader.py" in r.stdout and "other.py" in r.stdout


def test_push_拒绝覆盖清单内的文件(tmp_path):
    """清单存在的全部意义：`--push` 不许静默抹掉实时构场能力。"""
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "data/loader.py": "def f():\n    return 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--push", "--apply")
    assert r.returncode == 1
    assert "拒绝" in r.stdout
    assert (b / "data/loader.py").read_text(encoding="utf-8") == "def f():\n    return 2\n"


def test_pull_默认排除清单内的文件(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "data/loader.py": "def f():\n    return 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--pull", "--apply")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (a / "data/loader.py").read_text(encoding="utf-8") == "def f():\n    return 1\n"


def test_push_显式带上_overwrite_known_才真的覆盖(tmp_path):
    """逃生口本身也要钉住：守卫写歪了（比如判到别的属性上），
    想正经重同步的人会**永远搬不动**清单内的文件，而且看不出为什么。"""
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "data/loader.py": "def f():\n    return 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--push", "--apply", "--overwrite-known")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (b / "data/loader.py").read_text(encoding="utf-8") == "def f():\n    return 1\n"


def test_pull_显式带上_include_known_才真的搬(tmp_path):
    a = _tree(tmp_path / "a", BASE)
    b = _tree(tmp_path / "b", {**BASE, "data/loader.py": "def f():\n    return 2\n"})
    r = _run("--a", str(a), "--b", str(b), "--pull", "--apply", "--include-known")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (a / "data/loader.py").read_text(encoding="utf-8") == "def f():\n    return 2\n"
