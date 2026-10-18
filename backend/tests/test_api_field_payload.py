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


@pytest.fixture(autouse=True)
def _library(current_model):
    """这一整个文件都要求模型库里存着交付那一份模型（见 `tests/conftest.py`）。

    本文件的要害是「两边拿到的**必须是同一份**」：路由里那条
    `deps.get_pipeline()` 与用例里手写的那条都要读模型库。库里空着两边也
    一致（都退到兜底参数），断言照样绿 —— 但这三张载荷就与页③ 实际跑的那
    一份脱了钩：兜底参数与标定参数**同折族、不同参数**，形状一样、数不一样。
    """
    return current_model


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


def test_体网格载荷的几何两格由后端算好(client):
    """页⑤ 右栏「环境参数」那两格几何（2026-10-12 规格书 §五）。

    ⚠️ **由后端算**：本仓的硬约束是前端不做任何数值计算，所以屏上不许出现
    `x_max - x_min` 这种减法 —— 它在两边都不会报错，只会慢慢漂开。

    两个数与 `tfield.config` 的常量逐位相等，也与载荷自己报的
    `x_min` / `x_max` 自洽（后者是同一个常量的另一处出口）。
    """
    from tfield import config as C

    body = client.get("/api/field/volume?t_index=7").json()
    assert body["shed_width"] == float(C.SHED_X_MAX - C.SHED_X_MIN)
    assert body["shed_height"] == float(C.SHED_Z_MAX)
    assert body["shed_width"] == body["x_max"] - body["x_min"]
