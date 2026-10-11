"""实时帧接进时间轴：时间轴访问器 + append_live_frame。

⚠️ 这个文件用一个**只够用的假数据集**（12 帧），不读那个 1308 × 52 的 xlsx：
`fit` 在 24 × 12 = 288 行的长表上跑，整组测试是秒级的，
而它要验的性质（旧帧逐位不变、幂等、乱序抛错）与数据集的规模无关。
真数据集上的验收在 `tests/test_api_live.py`。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tfield import config as C
from tfield.data.loader import required_sensor_columns
from tfield.data.types import Dataset, FixReport, SensorPos
from tfield.features import build_features
from tfield.field.constraints import light_at
from tfield.pipeline import FieldPipeline, PipelineConfig


def tiny_dataset(n_times: int = 12) -> Dataset:
    """一份最小可用的数据集：必要的列齐、时间戳 5 分钟一格、无修复。"""
    ts = pd.date_range("2026-07-23 11:00:00", periods=n_times, freq="5min")
    cols: dict[str, np.ndarray] = {
        C.COL_TIMESTAMP: ts.to_numpy(),
        C.BG_TEMP: np.linspace(20.0, 30.0, n_times),
        C.BG_RH: np.full(n_times, 60.0),
        C.BG_LIGHT: np.tile([0.0, 800.0], n_times // 2 + 1)[:n_times],
    }
    rng = np.random.default_rng(0)
    for col in required_sensor_columns():
        cols[col] = 20.0 + rng.normal(0.0, 0.5, n_times)
    wide = pd.DataFrame(cols).set_index(C.COL_TIMESTAMP, drop=False)
    quality = pd.DataFrame({
        C.COL_TIMESTAMP: ts.to_numpy(),
        "p1_p1_temp_C": np.zeros(n_times, dtype=int),
    })
    layout = {k: SensorPos(x=v[0], z=v[1], layer=v[2])
              for k, v in C.SENSOR_LAYOUT.items()}
    return Dataset(wide=wide, layout=layout, sheds=dict(C.SHED_Y), quality=quality,
                   fix=FixReport(n_rows=n_times, fixed_indices=(),
                                 monotonic_before=True, monotonic_after=True,
                                 spacing_seconds=300.0, gaps=()),
                   signature="tiny0000", _dict_layout={})


@pytest.fixture(scope="module")
def tiny() -> Dataset:
    return tiny_dataset()


def test_不追加时_时间轴与数据集逐位相同(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    assert pipe.n_times == len(tiny.wide)
    assert pipe.timestamps() == list(pd.to_datetime(tiny.wide[C.COL_TIMESTAMP]))


def test_time_at_给的是那一帧的时间(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    assert pipe.time_at(0) == pd.Timestamp("2026-07-23 11:00:00")
    assert pipe.time_at(pipe.n_times - 1) == pd.Timestamp("2026-07-23 11:55:00")


def test_time_at_越界抛_而不是返回_none(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    with pytest.raises(IndexError):
        pipe.time_at(pipe.n_times)
    with pytest.raises(IndexError):
        pipe.time_at(-1)


def test_没有实时帧时_n_live_是零(tiny):
    pipe = FieldPipeline(PipelineConfig.fallback(), tiny)
    assert pipe.n_live == 0


# ── append_live_frame ──


@pytest.fixture(scope="module")
def fitted(tiny) -> FieldPipeline:
    """在假数据集上 fit 一次（288 行长表，秒级）。"""
    groups = C.DEFAULT_FEATURE_GROUPS
    return FieldPipeline(PipelineConfig.fallback(), tiny).fit(
        build_features(tiny, groups), tiny)


def _append(pipe, i=0, *, temps=None, ts=None, bg=31.0):
    """接一帧。

    ⚠️ 默认时间戳是**当前时间轴末尾 + 5 分钟**，不是「12:00 + 5i」。

    `fitted` 是 module 级夹具（288 行长表 fit 一次，秒级），**多条用例共用同一个
    实例、一条接一条往尾巴上加帧**。写死的时间表会在第二条用例上撞车：12:00 在
    第一条里已经接进去了，第二条再递一次就是自己撞自己 —— 而它要验的明明是别的事
    （旧帧逐位不变）。取「末尾 + 5 分钟」让每条用例对「下一次追加」都成立。
    """
    when = (pipe.time_at(pipe.n_times - 1) + pd.Timedelta(minutes=5)
            if ts is None else ts)
    return pipe.append_live_frame(
        bg_temp=bg, bg_rh=55.0, bg_light=850.0, ts=when,
        sensor_temps=(np.full(C.EXPECTED_N_SENSORS, 25.0) if temps is None else temps))


def test_接一帧之后_时间轴长一格_时间戳是新的(fitted):
    n0 = fitted.n_times
    last_before = fitted.time_at(n0 - 1)
    t_new = _append(fitted, 0)
    assert t_new == n0
    assert fitted.n_times == n0 + 1
    assert fitted.n_live == 1
    # 接着网格往后走一格……
    assert fitted.time_at(t_new) == last_before + pd.Timedelta(minutes=5)
    # ……而数据集末尾正是 11:55，所以第一帧落的就是 12:00。
    assert last_before == pd.Timestamp("2026-07-23 11:55:00")
    assert fitted.time_at(t_new) == pd.Timestamp("2026-07-23 12:00:00")
    assert len(fitted.timestamps()) == n0 + 1


def test_追加不改动旧的_t_index(fitted):
    """**这是整条设计最要紧的一条性质**：实时帧不许污染已经答得出来的那一段。"""
    coords = np.asarray(fitted.coords, dtype=float)
    ti = np.arange(fitted.n_times)
    trend_before = fitted.trend_at_coords(coords, ti)
    resid_before = fitted.residual_at_coords(coords, ti)

    _append(fitted, 0)
    _append(fitted, 1)

    assert np.array_equal(fitted.trend_at_coords(coords, ti), trend_before)
    assert np.array_equal(fitted.residual_at_coords(coords, ti), resid_before)


def test_接进来的那一路读数真的进了场(fitted):
    """在某个测点自己的坐标上问那一帧，答出来就该是那个测点的读数。

    IDW 在这个点上距离为零，它的残差原样落在自己头上 —— 所以这既是物理检验，
    也是「append 真的接到了场的那条链上」的证据。少了它，
    「接口返回的数与库里一致」这种测试在两个实现都错的情况下照样绿。
    """
    shed_i, pos_i = 0, 0
    shed = C.SHED_ORDER[shed_i]
    pos = list(C.SENSOR_LAYOUT)[pos_i]
    x, z, _ = C.SENSOR_LAYOUT[pos]
    y = float(C.SHED_Y[shed])

    temps = np.full(C.EXPECTED_N_SENSORS, 25.0)
    temps[shed_i * len(C.SENSOR_LAYOUT) + pos_i] = 31.5
    t_new = _append(fitted, 0, temps=temps)

    got = fitted.predict_points(np.array([[x, y, z]]), np.array([t_new]))[0, 0]
    assert abs(float(got) - 31.5) < 1e-6


def test_光照门禁在实时帧上也答得出来(fitted):
    """`light_at` 走**管线的访问器**，不读宽表。

    它原来读的是 `pipe.ds.wide[C.BG_LIGHT].iloc[t_index]` —— 宽表只有训练段那些行，
    而实时帧接在**时间轴**尾部。于是接完一帧再算场（`apply_monotonic` 要这个门禁量）
    就在那一行 `IndexError`：越界读的是宽表，不是时间轴。

    ⚠️ **越界断言不是装饰**：下标必须真的越出宽表，这条用例才钉到了东西 ——
    它越不出宽表就说明实时帧没接在尾部，那这条测试守的是别的事。
    """
    # 先钉住「训练段那一头仍然逐位同值」：访问器换掉了读法，读数不能跟着变。
    assert light_at(fitted, 0) == fitted.ds.wide[C.BG_LIGHT].iloc[0]

    t = _append(fitted)                       # `_append` 的 bg_light 是 850.0
    assert t >= len(fitted.ds.wide), "这个下标没越出宽表，用例钉不到东西"
    assert fitted.bg_light_at(t) == 850.0
    assert light_at(fitted, t) == 850.0


def test_同一时间戳接两次直接抛(fitted):
    n = fitted.n_times
    used = _append(fitted, 0)
    with pytest.raises(ValueError):
        _append(fitted, 0, ts=fitted.time_at(used))
    assert fitted.n_times == n + 1, "被拒的那一帧还是接进去了"


def test_乱序帧直接抛(fitted):
    with pytest.raises(ValueError):
        _append(fitted, 0, ts=pd.Timestamp("2026-07-23 11:00:00"))


def test_路数不对直接抛(fitted):
    with pytest.raises(ValueError):
        _append(fitted, 0, temps=np.full(23, 25.0))


def test_非有限读数直接抛(fitted):
    """IDW 的 predict 是稠密的 `w @ resid`：一路 NaN 会让**整帧**变 NaN。

    数据里实测一路 NaN 都没有（24 列全量 0 缺失），所以这是纯粹的守卫 ——
    但守卫必须在入口上，事后没法把那一格摘出去。
    """
    bad = np.full(C.EXPECTED_N_SENSORS, 25.0)
    bad[7] = np.nan
    with pytest.raises(ValueError):
        _append(fitted, 0, temps=bad)
    bad[7] = np.inf
    with pytest.raises(ValueError):
        _append(fitted, 0, temps=bad)


def test_追加不改动_source_y_levels(fitted):
    """合法的 y 集是 **fit 的属性**，帧是时间轴上的东西，两者无关。

    这条一破，R2（只在见过的断面上查趋势）就跟着破 —— 而它破得很安静。
    """
    before = fitted.source_y_levels().copy()
    _append(fitted, 0)
    assert np.array_equal(fitted.source_y_levels(), before)
