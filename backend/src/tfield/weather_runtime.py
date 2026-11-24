"""Immutable, locally provisioned weather model packages and stateless inference.

Pickles are deployment artifacts supplied by a trusted server administrator;
they are never accepted as user-supplied HTTP uploads. Every file is verified before loading.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import pickle
import uuid
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .artifact import PipelineArtifact
from .data.types import Dataset, FixReport, SensorPos
from .features import build_features
from .pipeline import FieldPipeline, PipelineConfig
from .weather_chain import WeatherNodeModel

FILES = ('current.pkl', 'history.pkl', 'field.bin')


def identifier(value: str) -> str:
    if str(uuid.UUID(value)) != value:
        raise ValueError('Invalid UUID')
    return value


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def model_root() -> Path:
    return Path(os.environ.get('TFIELD_WEATHER_MODEL_ROOT', Path(__file__).resolve().parents[2] / 'configs' / 'weather-models'))


def result_root() -> Path:
    return Path(os.environ.get('TFIELD_WEATHER_RESULT_ROOT', Path(__file__).resolve().parents[2] / 'configs' / 'weather-results'))


def _read(root: Path, package: str, name: str) -> bytes:
    base = root.resolve()
    folder = base / identifier(package)
    file = folder / name
    if folder.is_symlink() or file.is_symlink() or file.resolve().parent != folder.resolve() or folder.resolve().parent != base:
        raise ValueError('Package paths must stay in the deployment directory')
    if file.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Package file exceeds size limit')
    return file.read_bytes()


def inspect_package(package: str, expected: str | None = None) -> dict:
    raw = _read(model_root(), package, 'manifest.json')
    sha = digest(raw)
    if expected is not None and expected != sha:
        raise ValueError('Published package manifest changed')
    manifest = json.loads(raw)
    if manifest['version'] != 1 or manifest['package_id'] != package or manifest['geometry_key'] != 'ginseng_arch_v1' or manifest['external_schema'] not in ('two', 'full'):
        raise ValueError('Unsupported model package')
    for name in FILES:
        if digest(_read(model_root(), package, name)) != manifest['files'][name]:
            raise ValueError(f'Package checksum mismatch: {name}')
    return {**manifest, 'package_sha256': sha}


@lru_cache(maxsize=16)
def _load(root: str, package: str, sha: str):
    # Caller verified hashes immediately before this call. The deployment root
    # is trusted; normal users cannot choose paths or write package files.
    path = Path(root)
    manifest = json.loads(_read(path, package, 'manifest.json'))
    contents = {name: _read(path, package, name) for name in FILES}
    if digest(_read(path, package, 'manifest.json')) != sha or any(digest(raw) != manifest['files'][name] for name, raw in contents.items()):
        raise ValueError('Package changed during loading')
    current, history = (pickle.loads(contents[name]) for name in FILES[:2])
    humidity = manifest['external_schema'] == 'full'
    for model, historical in ((current, False), (history, True)):
        if not isinstance(model, WeatherNodeModel) or model.n_nodes != 24 or model.spec.humidity != humidity or model.spec.history != historical or not model.feature_names:
            raise ValueError('Virtual node model does not match manifest')
    artifact = PipelineArtifact.from_bytes(contents['field.bin'])
    return current, history, artifact


def package_models(root: Path, current: Path, history: Path, artifact: Path,
                   model_id: int, schema: str, bounds: dict | None = None) -> dict:
    if schema not in ('two', 'full') or model_id <= 0:
        raise ValueError('Positive field model id and two/full schema required')
    package = str(uuid.uuid4())
    folder = root / package
    folder.mkdir(parents=True, exist_ok=False)
    manifest = {'version': 1, 'package_id': package, 'model_id': model_id,
                'external_schema': schema, 'geometry_key': 'ginseng_arch_v1',
                'timezone': 'Asia/Shanghai', 'history_frames': 13,
                'bounds': bounds or {}, 'files': {}}
    for name, source in zip(FILES, (current, history, artifact)):
        raw = source.read_bytes()
        (folder / name).write_bytes(raw)
        manifest['files'][name] = digest(raw)
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')
    (folder / 'manifest.json').write_bytes(raw)
    _load(str(root.resolve()), package, digest(raw))  # fail before registration
    return {**manifest, 'package_sha256': digest(raw)}


def infer(package: str, expected: str, frames: list[dict]) -> dict:
    manifest = inspect_package(package, expected)
    current, historical, artifact = _load(str(model_root().resolve()), package, expected)
    if not 1 <= len(frames) <= 13:
        raise ValueError('Supply 1 to 13 weather frames')
    weather = pd.DataFrame(frames)
    ts = pd.to_datetime(weather['timestamp'], utc=True, errors='raise')
    if ts.isna().any() or ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise ValueError('Weather timestamps must be unique and increasing')
    when = ts.iloc[-1].isoformat()
    weather['timestamp'] = ts.dt.tz_convert(manifest['timezone']).dt.tz_localize(None)
    full = manifest['external_schema'] == 'full'
    required = ['bg_temp', 'bg_light'] + (['bg_rh'] if full else [])
    if not np.isfinite(weather[required].to_numpy(float)).all() or (weather.bg_light < 0).any():
        raise ValueError('Invalid external weather')
    if full and ((weather.bg_rh < 0) | (weather.bg_rh > 100)).any():
        raise ValueError('Humidity must be between 0 and 100')
    history_ready = len(weather) == 13 and (weather.timestamp.diff().iloc[1:] == pd.Timedelta(minutes=5)).all()
    selected = historical if history_ready else current
    predictions, humidity = selected.predict_with_humidity(weather if history_ready else weather.tail(1))
    nodes, rh = predictions[-1], float(humidity[-1])
    row = weather.iloc[-1]
    wide = pd.DataFrame([{C.COL_TIMESTAMP: row.timestamp, C.BG_TEMP: float(row.bg_temp),
                          C.BG_LIGHT: float(row.bg_light), C.BG_RH: rh}])
    for value, (shed, position) in zip(nodes, ((s, p) for s in C.SHED_ORDER for p in C.SENSOR_LAYOUT)):
        wide[C.sensor_columns(shed, position)[0]] = float(value)
    layout = {p: SensorPos(*values) for p, values in C.SENSOR_LAYOUT.items()}
    ds = Dataset(wide, layout, C.SHED_Y, pd.DataFrame(index=wide.index),
                 FixReport(1, (), True, True, None, ()), f'virtual-{package}')
    cfg = PipelineConfig(feature_groups=artifact.feature_groups, trend_kind=artifact.trend_kind,
                         metric=artifact.metric, cross_shed=artifact.cross_shed)
    pipe = FieldPipeline(cfg, ds).restore(artifact, fs=build_features(ds, artifact.feature_groups))
    pipe.calibrated = True
    from api.routes.field import volume_payload
    volume = volume_payload(pipe, t_index=0, preset='standard', monotonic=True,
                            y_step=.5, y_min=0, y_max=18)
    # Existing renderer calls source planes measured; these sources are virtual.
    for plane in volume['planes']:
        plane['measured'] = False
        plane['virtual_source'] = plane['shed'] is not None
    bounds, bounds_source = training_bounds(manifest)
    provenance = {'source': 'virtual_weather_prediction', 'package_id': package,
                  'package_sha256': expected, 'model_id': manifest['model_id'],
                  'external_schema': manifest['external_schema'],
                  'stage1_mode': 'history_1h' if history_ready else 'current_only',
                  'humidity_source': 'observed_external' if full else 'predicted_external',
                  'background_humidity_used': rh, 'node_temperatures': nodes.tolist(),
                  'prediction_target': getattr(selected, 'prediction_target', 'absolute'),
                  'warnings': [], 'training_bounds': bounds, 'training_bounds_source': bounds_source}
    volume.update({'time': when, 'provenance': provenance,
                   'geometry': {'radius':float(C.ARCH_R),'center_x':float(C.ARCH_XC),'offset_z':float(C.ARCH_K)},
                   'note': '由外部气象预测虚拟测点后构场；不是棚内传感器实测。沿 y 的源平面以外沿用边界值。'})
    summary = {'time': when, 'mean': volume['mean'], 'vmin': volume['vmin'],
               'vmax': volume['vmax'], **provenance}
    return {'summary': summary, 'field': volume,
            'input': {'timestamp':when,'bg_temp':float(row['bg_temp']),'bg_light':float(row['bg_light'])}}


def training_bounds(manifest: dict) -> tuple[dict, str]:
    """Read old packages' omitted bounds from their matching, trusted G training record.

    Never rewrite a published manifest or guess a range from the prediction itself.
    The fallback must reference the exact G artifacts and original dataset.
    """
    bounds, source = manifest.get('bounds', {}), 'package'
    if not bounds and manifest.get('g_training_job_id'):
        try:
            job = identifier(manifest['g_training_job_id'])
            root = Path(os.environ.get('TFIELD_WEATHER_TRAINING_ROOT', Path(__file__).resolve().parents[2] / 'configs' / 'weather-training')).resolve()
            folder, path = root / job, root / job / 'state.json'
            if folder.is_symlink() or path.is_symlink() or path.resolve().parent != folder or path.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('Invalid training record')
            state = json.loads(path.read_text(encoding='utf-8'))
            if state['id'] != job or state['state'] != 'done' or state['dataset_sha256'] != manifest['g_dataset_sha256']:
                raise ValueError('Unmatched training record')
            if any(state['artifacts'][key] != manifest['files'][key + '.pkl'] for key in ('current', 'history')):
                raise ValueError('Unmatched G artifacts')
            bounds, source = state['result']['bounds'], 'g_training_record'
        except (OSError, ValueError, KeyError, TypeError):
            return {}, 'unavailable'
    if not isinstance(bounds, dict) or not bounds:
        return {}, 'unavailable'
    for key, limits in bounds.items():
        if key not in ('bg_temp', 'bg_light', 'bg_rh') or not isinstance(limits, (list, tuple)) or len(limits) != 2:
            return {}, 'unavailable'
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) for v in limits) or limits[0] > limits[1]:
            return {}, 'unavailable'
    return bounds, source


def save_result(frame_id: str, result: dict) -> None:
    root = result_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f'{identifier(frame_id)}.json.gz'
    temporary = root / f'{frame_id}.{uuid.uuid4().hex}.tmp'
    try:
        with gzip.open(temporary, 'wt', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def read_result(frame_id: str) -> dict:
    file = result_root() / f'{identifier(frame_id)}.json.gz'
    if file.is_symlink():
        raise ValueError('Invalid result path')
    with gzip.open(file, 'rt', encoding='utf-8') as stream:
        result = json.load(stream)
    # Older snapshots retain their predictions, but no longer expose range alerts.
    for metadata in (result.get('summary', {}), result.get('field', {}).get('provenance', {})):
        if isinstance(metadata.get('warnings'), list):
            metadata['warnings'] = [code for code in metadata['warnings']
                                    if not (isinstance(code, str) and
                                            (code.endswith('_outside_training_range') or code == 'training_range_unavailable'))]
    return result
