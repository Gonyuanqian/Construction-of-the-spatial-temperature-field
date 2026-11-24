"""连续场插值与 HTTP 接口；解析线性场做独立数值对照，不接数据库。"""
import pathlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from api.routes import field, live as live_routes
from api.main import create_app
from fastapi.testclient import TestClient
from tfield.field.sample import axis_weights, sample_grid
from tfield.field.arch import arch_mask


def test_trilinear_reproduces_linear_field_between_all_three_axes():
    xs, ys, zs = [0, 1, 2], [0, 2, 4], [0, 1]
    plane = lambda iy: np.array([[10 + 2*x + 3*ys[iy] + 4*z for x in xs] for z in zs])
    got = sample_grid(xs, ys, zs, (0.3, 1.2, 0.4), plane, lambda *_: False)
    assert got == pytest.approx(15.8)


def test_exact_node_does_not_require_unused_missing_neighbors():
    plane = lambda iy: np.array([[21.25, np.nan], [np.nan, np.nan]])
    assert sample_grid([0, 1], [0, 1], [0, 1], (0, 0, 0), plane, lambda *_: False) == 21.25
    assert sample_grid([0, 1], [0, 1], [0, 1], (.5, .5, .5), plane, lambda *_: False) is None
    assert sample_grid([0, 1], [0, 1], [0, 1], (0, 0, 0), plane, lambda *_: True) is None


@pytest.mark.parametrize('v', [-1, 2, float('nan'), float('inf')])
def test_no_clamping_outside_grid(v):
    with pytest.raises(ValueError):
        axis_weights([0, 1], v)


@pytest.fixture
def setup_field(monkeypatch):
    pipe = SimpleNamespace(n_times=5, time_at=lambda t: f'time-{t}')
    monkeypatch.setattr(field.deps, 'get_pipeline', lambda: pipe)
    monkeypatch.setattr(field, 'available_sheds', lambda _: ('p1', 'p2', 'p3'))
    calls = []
    def at(_pipe, y, t, grid, *, monotonic):
        calls.append((y, t, monotonic))
        X, Z = grid.mesh()
        values = 10 + 2*X + 3*y + 4*Z + t
        return SimpleNamespace(values=np.where(arch_mask(X, Z), values, np.nan))
    monkeypatch.setattr(field, 'field_at', at)
    return pipe, calls


def test_endpoint_returns_original_coordinate_and_matches_grid(setup_field):
    pipe, calls = setup_field
    client = TestClient(create_app())
    out = client.get('/api/field/point?x=1.025&y=6.2&z=0.625&t_index=2').json()
    assert out['kind'] == 'value'
    assert (out['x'], out['y'], out['z']) == (1.025, 6.2, .625)
    assert out['value'] == pytest.approx(35.15)
    assert out['time'] == 'time-2'
    assert [c[0] for c in calls] == [6.0, 6.5]
    assert all(c[2].enabled for c in calls)


def test_outside_and_unmeasured_remain_distinct(setup_field):
    pipe, calls = setup_field
    outside = field.point_payload(pipe, x=2.05, y=6.2, z=1.25, t_index=0)
    unmeasured = field.point_payload(pipe, x=1.05, y=6.2, z=1.2, t_index=0)
    assert outside['kind'] == 'outside' and outside['value'] is None
    assert unmeasured['kind'] == 'unmeasured' and unmeasured['value'] is None
    assert not calls


def test_invalid_coordinates_do_not_prepare_model(monkeypatch):
    def fail():
        pytest.fail('invalid coordinate must not load a pipeline')
    monkeypatch.setattr(field.deps, 'get_pipeline', fail)
    client = TestClient(create_app())
    for query in ('x=-1&y=6&z=.5', 'x=1&y=99&z=.5', 'x=1&y=6&z=nan'):
        assert client.get('/api/field/point?' + query).status_code == 400


def test_rejects_query_after_model_or_dataset_changes(setup_field):
    pipe, calls = setup_field
    reference = field._field_ref(pipe)
    pipe.cfg = 'different-model-configuration'
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        field.point_payload(pipe, x=1, y=6.2, z=.5, t_index=0, expected_ref=reference)
    assert error.value.status_code == 409
    assert not calls


def test_point_matches_actual_projected_volume_at_fractional_coordinates():
    # 使用真实 field_at 和竖直投影，独立从整卷八角点对拍。
    class Pipe:
        n_times = 1
        def time_at(self, t): return 'time-0'
        def source_y_levels(self): return [3., 9., 15.]
        def bg_light_at(self, t): return 100.
        def trend_at_coords(self, coords, times):
            x, y, z = coords.T
            return (20 + x + .1*y + np.where(z > .6, -3., 3.))[:, None]
        def residual_at_coords(self, coords, times): return np.zeros((len(coords), len(times)))
    pipe = Pipe()
    volume = field.volume_payload(pipe, t_index=0, preset='standard', monotonic=True,
                                  y_step=.5, y_min=0., y_max=18.)
    expected = 0.
    for iy, wy in [(12, .6), (13, .4)]:
        for iz in [13, 14]:
            for ix in [20, 21]:
                expected += wy*.5*.5*volume['planes'][iy]['values'][iz][ix]
    result = field.point_payload(pipe, x=1.025, y=6.2, z=.675, t_index=0)
    assert result['value'] == pytest.approx(expected)
    assert result['field_ref'] == volume['field_ref']


def test_live_uses_frame_time_mapping_and_rejects_unwalked_frames(setup_field, monkeypatch):
    pipe, calls = setup_field
    source = SimpleNamespace(pipeline=pipe, running=False, total=5, cursor=lambda: 2,
                             frame=lambda n: {'timestamp': '2026-07-27 12:10:00'})
    monkeypatch.setattr(live_routes.live, 'get_live_source', lambda: source)
    monkeypatch.setattr(live_routes, '_require_ready', lambda _: None)
    monkeypatch.setattr(live_routes, '_advance', lambda src, n: n + 2)
    out = live_routes.get_point(2, x=1, y=6.2, z=.5)
    assert out['time'] == 'time-4'
    assert out['frame']['n'] == 2
    assert all(t == 4 for _, t, _ in calls)
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        live_routes.get_point(3, x=1, y=6.2, z=.5)
