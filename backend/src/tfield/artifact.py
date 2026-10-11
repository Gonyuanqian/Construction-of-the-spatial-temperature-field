"""一份训练好的模型**成品**：怎么存成字节、怎么装回来。

## 成品里有什么

只有**拟合好的趋势**，以及「这一份是在什么条件下拟合的」（版本、特征组、
列名、度量、是否跨棚）。0.895 MB。**没有 `FeatureSet`、没有残差矩阵。**

## 成品里为什么**不能**有残差矩阵

残差矩阵必须从**当前**数据重算。IDW 是**精确插值**：`IDWCorrector.fit` 只存
坐标与残差数组，`predict` 在源点上原样返回存进去的那个值。把 A 那份数据算出的
残差搬到 B 那份数据的测点位置上，屏上显示的是 **A 实测的温度**，而它长得完全
正常 —— 没有一处会报错。

所以：**趋势进成品，残差永远现算。** `_fs` 也永远来自当前数据集。
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass

from .models.idw import AnisoMetric
from .models.trend import TrendModel

#: 字节的抬头。**认它，而不是认 pickle 的协议头。**
#: 一份 `bundle` 的 JSON、或者随便一张图片，被猜成「成品」之后报的会是
#: 「版本不对」，而真相是「这根本不是成品」—— 两种错的屏上那句话不一样。
MAGIC = b"TFART\x00"

#: 这份字节的格式版本。**改它等于宣布旧成品读不动。**
#: 读不动不是崩，是回落现训（`deps._build_pipeline`），并在屏上标出来。
FORMAT_VERSION = 1

_VERSION_BYTES = 4


class ArtifactError(Exception):
    """成品读不动。

    **分成两个子类**：对策一样（回落现训），但屏上那句理由不一样 ——
    一个是「这个格式我还不认识」，一个是「这份字节坏了」。
    """


class ArtifactVersionError(ArtifactError):
    """字节是好的，版本对不上。"""

    def __init__(self, found: int, expected: int) -> None:
        super().__init__(f"成品是第 {found} 版，这份代码只认第 {expected} 版。")
        self.found = int(found)
        self.expected = int(expected)


class ArtifactCorruptError(ArtifactError):
    """字节本身不对：抬头不对、截断、或者正文根本不是成品。"""


@dataclass(frozen=True)
class PipelineArtifact:
    """成品里属于「模型」的那些。理由见模块 docstring。"""

    tool_version: str
    trend_kind: str
    feature_groups: tuple[str, ...]
    feature_names: tuple[str, ...]
    metric: AnisoMetric
    cross_shed: bool
    n_times: int
    trend: TrendModel

    @property
    def format_version(self) -> int:
        """这份字节的格式版本。**只有一份拷贝** —— 就是抬头里那四个字节。

        写成属性而不是字段：字段会在「抬头说第 2 版、正文说第 1 版」的时候
        活着回来，而那正是最该炸的时候。
        """
        return FORMAT_VERSION

    def to_bytes(self) -> bytes:
        body = pickle.dumps(self, protocol=pickle.HIGHEST_PROTOCOL)
        return MAGIC + FORMAT_VERSION.to_bytes(_VERSION_BYTES, "big") + body

    @classmethod
    def from_bytes(cls, raw: bytes) -> "PipelineArtifact":
        """字节 → 成品。读不动时抛 `ArtifactError` 的两个子类之一。

        **先读版本、再解正文**（规格书 D8）。
        """
        if not raw.startswith(MAGIC):
            raise ArtifactCorruptError("这不是一份成品字节（抬头对不上）。")
        rest = raw[len(MAGIC):]
        if len(rest) < _VERSION_BYTES:
            raise ArtifactCorruptError("成品字节被截断了（版本号都不完整）。")
        found = int.from_bytes(rest[:_VERSION_BYTES], "big")
        if found != FORMAT_VERSION:
            raise ArtifactVersionError(found, FORMAT_VERSION)
        try:
            got = pickle.loads(rest[_VERSION_BYTES:])
        except Exception as e:          # noqa: BLE001 —— 任何解不开都算坏
            raise ArtifactCorruptError(f"成品的正文解不开：{e}") from e
        if not isinstance(got, cls):
            raise ArtifactCorruptError(
                f"成品的正文不是 {cls.__name__}，是 {type(got).__name__}。")
        return got
