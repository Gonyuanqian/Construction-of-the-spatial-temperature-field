"""`/api/field/volume` 的拒绝路径。**这个文件不是 slow。**

参数的合法性判定（preset、y_step、y_min/y_max、格子数上限）全部在
`deps.get_pipeline()` **之前**完成，所以这一整组不需要 fit —— 而 fit 要几十秒。
把拒绝路径从 slow 里分出来，是为了让「上限挡住 export」这条能在每次改动后
几秒内跑一遍：用户敲错一个参数，不该等一次 fit 才听到「参数不对」。

⚠️ 这一组里**唯一**那条会走到管线的测试是 `test_拒绝路径不碰管线`，
它反过来把管线钉死：校验没做完就去取管线，测试立刻红。
"""
from __future__ import annotations

import sys
import pathlib

import pytest
from fastapi.testclient import TestClient

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from api.main import create_app                                       # noqa: E402
from api.routes.field import (                                        # noqa: E402
    VOLUME_MAX_CELLS, _check_volume_size, _check_y_range, _measured_at, _y_planes,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(
    "y_min,y_max,y_step,n,last",
    [
        (0.0, 18.0, 1.0, 19, 18.0),
        (0.0, 18.0, 0.5, 37, 18.0),
        (0.0, 18.0, 0.25, 73, 18.0),
        # 除不尽：末片**不超过** y_max，不是硬凑到它。
        (0.0, 18.0, 0.7, 26, 17.5),
        # 起点不是 0 也行。
        (3.0, 15.0, 3.0, 5, 15.0),
        # y_min < y_max 但一步就跨过去了：至少给一片，不能是空卷。
        (0.0, 0.3, 0.5, 1, 0.0),
    ],
)
def test_片数是_y_min_加_k_乘_y_step_且末片不超过_y_max(y_min, y_max, y_step, n, last):
    ys = _y_planes(y_min, y_max, y_step)
    assert len(ys) == n, f"{y_min} 至 {y_max}，步长 {y_step}：期望 {n} 片，得到 {len(ys)}"
    assert ys[0] == pytest.approx(y_min)
    assert ys[-1] == pytest.approx(last)
    assert ys[-1] <= y_max + 1e-9
    assert list(ys) == sorted(ys)


def test_标准网格在_0_125_步长下仍在上限内_在_0_1_下越界():
    """规格书 §三 那两个数就是这条的依据。

    standard 是 43 × 27 = 1161 个格子一片（`GridSpec.nx/nz`，实测）。
    145 片 = 168345 ≤ 200000（放行）；181 片 = 210141 > 200000（挡住）。
    写成测试而不是注释：上限一旦被谁调大，这条会立刻说出来。
    """
    _check_volume_size(43, 27, 145)                     # 不抛就是放行
    with pytest.raises(Exception) as e:
        _check_volume_size(43, 27, 181)
    assert "200000" in str(e.value.detail)


def test_export_网格在默认步长下就被上限挡住():
    """`preset=export` 是 106 × 66 = 6996 个格子一片。

    默认 37 片 → 258852 > 200000。这条路上既没有大小上限也没有 gzip，
    不挡的话载荷是十几 MB。**这条测试的价值在于它几秒就跑完** ——
    整个判定只用到 `GridSpec` 的行列数，碰不到管线。
    """
    from tfield.field.grid import GridSpec

    g = GridSpec.from_preset("export")
    assert g.nx * g.nz == 6996, "export 的格子数变了 —— 规格书 §三 那个上限的依据要重算"
    with pytest.raises(Exception) as e:
        _check_volume_size(g.nx, g.nz, len(_y_planes(0.0, 18.0, 0.5)))
    assert "格子" in str(e.value.detail)


@pytest.mark.parametrize(
    "y_min,y_max,y_step",
    [
        (0.0, 18.0, 0.0),          # 零步长
        (0.0, 18.0, -0.5),         # 负步长
        (0.0, 18.0, 6.5),          # 太大
        (18.0, 0.0, 0.5),          # 倒过来
        (5.0, 5.0, 0.5),           # 空区间
    ],
)
def test_非法的_y_参数抛错(y_min, y_max, y_step):
    with pytest.raises(Exception):
        _check_y_range(y_min, y_max, y_step)


def test_实测判据吃的是可用断面不是常数():
    """**这条钉的就是规格书 §四.3 那个错。**

    原规格书写的是「`measured: true` 只出现在 y ∈ {3, 9, 15}」。留一断面时
    p2 整棚被排除，`field_at(y=9)` 会去混合 p1 与 p3 —— 那时 y = 9 是**算出来的**。
    按常数标 `measured: true`，界面就会把一个混合场标成实测断面，
    而「密度即可信度」这套语言的全部意义就是不许这样做。
    """
    assert _measured_at(9.0, ("p1", "p2", "p3")) == (True, "p2")
    # 留一折：p2 不在可用集里，y = 9 不再是实测断面。
    assert _measured_at(9.0, ("p1", "p3")) == (False, None)
    assert _measured_at(6.0, ("p1", "p2", "p3")) == (False, None)
    # y_step = 0.1 时 30 × 0.1 在浮点上是 3.0000000000000004 —— 容差要吃得下。
    assert _measured_at(3.0000000000000004, ("p1", "p2", "p3")) == (True, "p1")


@pytest.mark.parametrize(
    "params",
    [
        {"preset": "ultra"},                       # 认不出的网格档位
        {"y_step": "0"},                           # 零步长
        {"y_step": "-1"},                          # 负步长
        {"y_step": "9"},                           # 太大
        {"y_min": "5", "y_max": "1"},              # 倒过来
        {"preset": "export"},                      # 格子数超上限
        {"preset": "export", "y_step": "0.125"},   # 超得更狠
    ],
)
def test_坏参数是_400_不是_500(client, params):
    r = client.get("/api/field/volume", params=params)
    assert r.status_code == 400, f"{params} 返回 {r.status_code}：{r.text}"
    assert r.json()["detail"]


def test_拒绝路径不碰管线(client, monkeypatch):
    """**这条是这一组存在的意义。**

    若哪天有人把 `deps.get_pipeline()` 挪到校验之前，这一整组测试就会从「几秒」
    变成「几十秒」 —— 而更糟的是，用户敲错一个参数要等一次 fit 才听到「参数不对」。
    这里让 `get_pipeline` 直接炸：拒绝路径**根本不该走到那里**。

    `monkeypatch` 打得着，是因为路由写的是 `deps.get_pipeline()`（调用时取属性），
    不是 `from ..deps import get_pipeline`。
    """
    from api import deps

    def boom(*a, **k):
        raise AssertionError("参数校验还没做完就去取管线了")

    monkeypatch.setattr(deps, "get_pipeline", boom)
    for params in ({"preset": "ultra"}, {"y_step": "0"}, {"y_min": "5", "y_max": "1"},
                   {"preset": "export"}):
        assert client.get("/api/field/volume", params=params).status_code == 400, params
