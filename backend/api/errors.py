"""两种「没有数据集」的错，以及它们各自的说法。

**为什么单独一个模块，不放在 `api/deps.py` 里**：`api/main.py` 要注册
exception handler，就得拿到这个类；而 `backend/tests/test_routes_use_cache.py`
那条源码守卫规定「`api/**` 从 `api.deps` 取名字时只许白名单里那几个」。
把异常放在这里，`main.py` 从 `api.errors` 取 —— 那条守卫一个字节不用改，
白名单也不必再长一个名字。少一次「要不要放行」的裁量，就少一次将来放错的口子。
"""
from __future__ import annotations

#: 空态的**唯一一句**中文。四个 router 加起来十几个接口都报这一句。
#:
#: 各接口各写一句会漂成三种说法（「还没有数据集」「请先上传」「缺少数据集」），
#: 而界面会把它们当成三件不同的事 —— 这是 T1 逐条比对同一句话的理由。
NO_DATASET_DETAIL = "还没有导入数据集。到「数据导入与检查」那一页导入一份 xlsx。"


class NoDatasetError(RuntimeError):
    """还没有在用任何数据集。

    **这是系统的起点，不是故障。** 路由层把它翻成 `409`，
    与「数据集文件不见了」（`404`）分开 —— 见规格书 §二.1。
    """

    def __init__(self) -> None:
        super().__init__(NO_DATASET_DETAIL)
