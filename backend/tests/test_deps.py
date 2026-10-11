"""数据集缓存的契约。

这个缓存存在的理由只有一条：`load_dataset()` 实测 0.96–1.00 秒
（三个全新进程各冷加载一次）。
所以测试问的不是「缓存能不能命中」，而是**该重新加载的时候有没有重新加载** ——
一个永远命中的缓存比没有缓存更糟：数据集换了、页面还是旧的，而且一声不响。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api.deps import DatasetCache                      # noqa: E402


class _Fake:
    """一个假的 Dataset —— 缓存不关心内容，只关心身份。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag


def _counting_loader(calls: list[pathlib.Path]):
    def load(path):
        calls.append(pathlib.Path(path))
        return _Fake(f"load#{len(calls)}")

    return load


def test_同一个文件只加载一次(tmp_path):
    p = tmp_path / "数据.xlsx"
    p.write_bytes(b"PK\x03\x04 fake")
    calls: list[pathlib.Path] = []
    c = DatasetCache(loader=_counting_loader(calls))

    a, b = c.get(p), c.get(p)
    assert a is b
    assert len(calls) == 1
    assert c.n_loads == 1


def test_文件被换掉后必须重新加载(tmp_path):
    """数据集的**文件身份** = (路径, mtime_ns, 大小)。三者任一变了就是另一份数据。

    只比路径的话，用户重新导出一次数据集（同名覆盖），页面上会一直显示旧数据。
    """
    p = tmp_path / "数据.xlsx"
    p.write_bytes("PK\x03\x04 第一版".encode("utf-8"))
    calls: list[pathlib.Path] = []
    c = DatasetCache(loader=_counting_loader(calls))

    first = c.get(p)
    p.write_bytes("PK\x03\x04 第二版，长了几个字节".encode("utf-8"))   # mtime 与 size 都变
    second = c.get(p)

    assert first is not second
    assert len(calls) == 2


def test_大小与_mtime_都没变时不会重复加载(tmp_path):
    """反向的一条：别把一个没变的文件当成变了。"""
    p = tmp_path / "数据.xlsx"
    p.write_bytes("PK\x03\x04 同样的内容".encode("utf-8"))
    calls: list[pathlib.Path] = []
    c = DatasetCache(loader=_counting_loader(calls))
    c.get(p)
    c.get(p)
    assert len(calls) == 1


def test_超过容量按_LRU_淘汰(tmp_path):
    calls: list[pathlib.Path] = []
    c = DatasetCache(loader=_counting_loader(calls), capacity=2)
    paths = []
    for i in range(3):
        p = tmp_path / f"d{i}.xlsx"
        p.write_bytes(b"PK\x03\x04 " + bytes([i]))
        paths.append(p)
        c.get(p)
    # d0 被挤出去了 —— 再取它要重新加载
    c.get(paths[0])
    assert len(calls) == 4


def test_文件不存在时抛_FileNotFoundError(tmp_path):
    c = DatasetCache(loader=_counting_loader([]))
    with pytest.raises(FileNotFoundError):
        c.get(tmp_path / "没有这个文件.xlsx")


def test_api_的数据集接口真的走了缓存(monkeypatch):
    """Review Focus #2 的落点：接口层必须用缓存，不能各自 load 一遍。

    这条测的是**接线**，不是缓存本身 —— 缓存写得再好，没人用它也白搭。
    """
    from fastapi.testclient import TestClient

    from api import deps
    from api.main import create_app
    from tfield.data.loader import load_dataset

    calls: list[pathlib.Path] = []

    # 这条不走 `_Fake`：路由拿到 Dataset 之后要读 wide / sheds / layout 才拼得出响应体，
    # 一个只有 `.tag` 的假对象会在路由里以 AttributeError 收场（500），
    # 那样测的就是「假对象不够真」而不是「接口用没用缓存」。
    # 计数装在真加载器外面，返回真 Dataset，断言仍然只看「加载了几次」。
    def counting_real_loader(path):
        calls.append(pathlib.Path(path))
        return load_dataset(path)

    monkeypatch.setattr(deps, "_CACHE", DatasetCache(loader=counting_real_loader))

    client = TestClient(create_app())
    assert client.get("/api/dataset").status_code == 200
    assert client.get("/api/dataset").status_code == 200
    assert len(calls) == 1, "两次请求加载了两遍数据集 —— 接口没有走缓存"



@pytest.fixture(autouse=True)
def _current_dataset():
    """空态成为默认之后，这个文件也必须**显式声明**它测的是哪一份数据集。

    2026-10-06 起，「当前在用哪一份数据集」是一个进程级的模块变量，启动时为空
    （规格书 §1.1 的空态）。不声明的话，这个模块里凡是碰数据集的用例都会拿到 409，
    而报错位置离现场很远。

    写成 autouse 而不是改各文件形状各异的 `client` 夹具，是因为本仓还有 **6 处**
    在测试里**内联**建 `TestClient(create_app())`（test_api.py ×2、
    test_api_train.py ×3、test_deps.py ×1）—— 它们同样要碰数据集，
    而只改 `client` 夹具会漏掉它们。一段代码、12 个文件、一模一样。
    """
    from api import deps, paths
    deps.set_current_dataset(paths.dataset_path())
