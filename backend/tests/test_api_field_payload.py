"""载荷装配只有一份 —— 路由与实时模式复用同一个函数。

页③ 的判定（三格共享色标、无测量带的下标、1/dy 混合出来的断面算不算实测）
一条都不许在实时模式里重写。这个文件钉的是「路由只是薄薄一层壳」。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import deps
from api.main import create_app
from api.routes.field import sections_payload, volume_payload


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_sections_接口的载荷就是_sections_payload_给的(client):
    body = client.get("/api/field/sections?t_index=7").json()
    mine = sections_payload(deps.get_pipeline(), t_index=7,
                            preset="standard", monotonic=True)
    assert mine == body


def test_volume_接口的载荷就是_volume_payload_给的(client):
    body = client.get("/api/field/volume?t_index=7&y_step=6.0").json()
    mine = volume_payload(deps.get_pipeline(), t_index=7, preset="standard",
                          monotonic=True, y_step=6.0, y_min=0.0, y_max=18.0)
    # 只有耗时是每次不同的
    assert mine.pop("elapsed_ms") >= 0
    assert body.pop("elapsed_ms") >= 0
    assert mine == body


def test_载荷的_n_times_读的是访问器而不是数据集行数(monkeypatch):
    """`pipe.ds.wide.shape[0]` 在实时帧接进来之后就是错的（会拒掉合法的帧）。

    把访问器改成另一个数：载荷跟着变，说明它读的是访问器。
    """
    from tfield.pipeline import FieldPipeline
    monkeypatch.setattr(FieldPipeline, "n_times", property(lambda self: 9999))
    body = sections_payload(deps.get_pipeline(), t_index=7,
                            preset="standard", monotonic=True)
    assert body["n_times"] == 9999
