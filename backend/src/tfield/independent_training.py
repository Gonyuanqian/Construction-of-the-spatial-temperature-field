"""Protocol v2: three independent houses, eight local section positions per house.

House identity is a grouping variable, never a spatial coordinate or a feature.
No longitudinal measurements are invented from distances between houses.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import numpy as np
import pandas as pd

from . import config as C
from .models.idw import AnisoMetric, IDWCorrector
from .weather_chain import WeatherFeatureSpec, WeatherNodeModel

PROTOCOL = 'independent_house_section_v2'
GEOMETRY = dict(length_m=6., width_m=2.1, height_m=1.3017,
                longitudinal_sampling='single_cross_section', section_y_m=None, dimensionality='cross_section',
                supported_geometry='reference_only')


def local_positions() -> np.ndarray:
    return np.array([[x / GEOMETRY['width_m'], z / GEOMETRY['height_m']]
                     for x, z, _ in C.SENSOR_LAYOUT.values()])


def field_features(weather: pd.DataFrame, positions: np.ndarray) -> pd.DataFrame:
    """The local x/z frame is shared by fitting and querying. No house/global y."""
    pts = np.asarray(positions, float)
    if pts.ndim != 2 or pts.shape[1] != 2 or not np.isfinite(pts).all():
        raise ValueError('F 位置必须是有限的归一化横向/高度坐标。')
    n = len(pts)
    u, w = np.tile(pts.T, len(weather))
    out = pd.DataFrame({'u': u, 'w': w, 'w2': w*w, 'w3': w*w*w})
    for key in ('bg_temp', 'bg_rh', 'bg_light'):
        out[key] = np.repeat(weather[key].to_numpy(float), n)
    hour = (pd.to_datetime(weather.timestamp).dt.hour + pd.to_datetime(weather.timestamp).dt.minute / 60).to_numpy(float)
    out['hour_sin'] = np.repeat(np.sin(2*np.pi*hour/24), n)
    out['hour_cos'] = np.repeat(np.cos(2*np.pi*hour/24), n)
    out['temp_w'] = out.bg_temp * w
    out['light_w'] = out.bg_light * w
    out['temp_light'] = out.bg_temp * out.bg_light
    return out


@dataclass
class SectionFieldModel:
    """Frozen common trend; IDW sources must be supplied for ONE house at a time."""
    trend: object
    metric: AnisoMetric
    geometry: dict
    protocol: str = PROTOCOL
    interpolation: str = 'idw'
    rbf_smoothing: float = .01

    def predict(self, weather, source_temperatures, *, source_indices=None, target_positions=None):
        points = local_positions()
        sources = np.arange(len(points)) if source_indices is None else np.asarray(source_indices, int)
        if not len(sources) or len(np.unique(sources)) != len(sources) or np.any((sources < 0) | (sources >= len(points))):
            raise ValueError('F 来源必须是同一棚内互不重复的有效测点编号。')
        values = np.asarray(source_temperatures, float)
        if values.shape != (len(weather), len(points)) or not np.isfinite(values[:, sources]).all():
            raise ValueError('F 每次只接收一座棚的 8 列测点值；隐藏位置不进入 IDW 来源。')
        target = points if target_positions is None else np.asarray(target_positions, float)
        base_source = self.trend.predict(field_features(weather, points[sources])).reshape(len(weather), len(sources))
        base_target = self.trend.predict(field_features(weather, target)).reshape(len(weather), len(target))
        coords = lambda p: np.column_stack([p[:, 0], np.zeros(len(p)), p[:, 1]])
        if getattr(self,'interpolation','idw')=='rbf':
            from scipy.interpolate import RBFInterpolator
            scales=np.array([self.metric.lx,self.metric.lz])
            residual=RBFInterpolator(points[sources]/scales,(values[:,sources]-base_source).T,
                kernel='linear',smoothing=self.rbf_smoothing)
            return base_target+residual(target/scales).T
        residual = IDWCorrector(self.metric, cross_shed=False).fit(
            coords(points[sources]), (values[:, sources] - base_source).T)
        return base_target + residual.predict(coords(target)).T


def fit_field(weather, houses: dict[str, np.ndarray], available, cfg, candidate):
    from xgboost import XGBRegressor
    points = local_positions()[available]
    features = field_features(weather, points)
    trend = XGBRegressor(n_estimators=cfg['n_estimators'], max_depth=candidate['max_depth'],
        learning_rate=.08, objective='reg:squarederror', n_jobs=2, random_state=cfg['seed'])
    trend.fit(pd.concat([features] * len(houses), ignore_index=True),
              np.concatenate([np.asarray(y)[:, available].ravel() for y in houses.values()]))
    return SectionFieldModel(trend, AnisoMetric(lx=candidate['lx'], ly=1, lz=candidate['lz'], power=candidate['power']), GEOMETRY.copy())


def fit_nodes(features, weather, houses, cfg, spec):
    from sklearn.ensemble import ExtraTreesRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    target = np.concatenate(list(houses.values()))
    X = pd.concat([features] * len(houses), ignore_index=True)
    if not spec.humidity:
        target = np.column_stack([target, np.tile(weather.bg_rh.to_numpy(float), len(houses))])
    estimator = ExtraTreesRegressor(n_estimators=cfg['n_estimators'], max_depth=cfg['max_depth'],
        min_samples_leaf=cfg['min_samples_leaf'], random_state=cfg['seed'], n_jobs=2) if cfg['algorithm'] == 'extra_trees' else make_pipeline(StandardScaler(), Ridge(alpha=cfg['alpha']))
    estimator.fit(X, target)
    return WeatherNodeModel(spec, estimator, tuple(features.columns), 8)


def train(ds, cfg, checkpoint=lambda _: None):
    from .weather_training import arrays, causal_features, describe, scores
    weather, raw, _ = arrays(ds)
    description = describe(ds)
    if not description['ready']:
        raise ValueError(description['reason'])
    if weather.timestamp.isna().any() or weather.timestamp.duplicated().any() or not weather.timestamp.is_monotonic_increasing:
        raise ValueError('纠正训练需要严格递增且不重复的时间轴。')
    houses = {house: raw[:, i*8:(i+1)*8] for i, house in enumerate(C.SHED_ORDER)}
    split = int(len(weather) * (1-cfg['validation_fraction']))
    prefix = weather.iloc[:split].reset_index(drop=True)
    future = weather.iloc[split:].reset_index(drop=True)
    train_houses = {house: y[:split] for house, y in houses.items()}
    result = dict(protocol_version=2, spatial_protocol=PROTOCOL, options=cfg, dataset=description,
        geometry=GEOMETRY.copy(), house_ids=list(houses), nodes_per_house=8, output_nodes=8,
        split=dict(method='chronological_and_leave_house_out', train_frames=split, validation_frames=len(future),
            train_start=weather.timestamp.iloc[0].isoformat(), train_end=weather.timestamp.iloc[split-1].isoformat(),
            validation_start=weather.timestamp.iloc[split].isoformat(), validation_end=weather.timestamp.iloc[-1].isoformat()),
        baseline=scores(np.concatenate([y[split:] for y in houses.values()]),
                        np.tile(future.bg_temp.to_numpy()[:, None], (len(houses), 8))), variants=[])

    # Only A positions and only training times select F parameters. B is untouched.
    tuning = [i for i, key in enumerate(C.SENSOR_LAYOUT) if key in C.TUNING_POSITIONS]
    reporting = [i for i in range(8) if i not in tuning]
    candidates = [dict(max_depth=depth, lx=.5, lz=.2, power=power) for depth in (3, 5) for power in (1., 2.)]
    trials = []
    for number, candidate in enumerate(candidates):
        actual, predicted = [], []
        for held in tuning:
            checkpoint(f'F 参数优选 {number+1}/{len(candidates)}，隐藏位置 {held+1}/8')
            sources = [i for i in range(8) if i != held]
            model = fit_field(prefix, train_houses, sources, cfg, candidate)
            for house, y in train_houses.items():
                # The excluded label is never in either the trend fit or IDW inputs.
                visible = y.copy(); visible[:, held] = np.nan
                predicted.append(model.predict(prefix, visible, source_indices=sources, target_positions=local_positions()[[held]]))
                actual.append(y[:, [held]])
        trials.append(dict(params=candidate, **scores(np.concatenate(actual), np.concatenate(predicted))))
    best = min(trials, key=lambda entry: entry['mae'])['params']
    per_point = []
    for held in reporting:
        checkpoint(f'F 独立 B 组时间留出验证：位置 {held+1}/8')
        sources = [i for i in range(8) if i != held]
        model = fit_field(prefix, train_houses, sources, cfg, best)
        for house, y in houses.items():
            visible = y[split:].copy(); visible[:, held] = np.nan
            predicted = model.predict(future, visible, source_indices=sources, target_positions=local_positions()[[held]])
            per_point.append(dict(house_id=house, position=list(C.SENSOR_LAYOUT)[held],
                **scores(y[split:, [held]], predicted)))
    # Pool errors with sample counts, rather than averaging RMSE values.
    total = sum(p['n'] for p in per_point)
    result['field_validation'] = dict(selection='A_positions_training_times', reporting='B_positions_future_times',
        source_policy='same_house_only', trials=trials, best_params=best, per_point=per_point,
        mae=sum(p['mae']*p['n'] for p in per_point)/total,
        rmse=float(np.sqrt(sum(p['rmse']**2*p['n'] for p in per_point)/total)), n=total)
    checkpoint('正在拟合冻结的单棚 F 模型')
    field = fit_field(prefix, train_houses, list(range(8)), cfg, best)
    models = {'field': field}
    for historical in (False, True):
        key = 'history' if historical else 'current'
        spec = WeatherFeatureSpec(cfg['external_schema'] == 'full', historical)
        X = causal_features(weather, spec)
        checkpoint(f'正在训练单棚 8 点 G：{key}')
        node = fit_nodes(X.iloc[:split], prefix, train_houses, cfg, spec)
        prediction = node.estimator.predict(X)[:, :8]
        validation = scores(np.concatenate([y[split:] for y in houses.values()]), np.tile(prediction[split:], (len(houses), 1)))
        cross_house = []
        for held, y in houses.items():
            checkpoint(f'整棚留出验证：{key} / {held}')
            remaining = {h: values for h, values in train_houses.items() if h != held}
            outside = fit_nodes(X.iloc[:split], prefix, remaining, cfg, spec)
            predicted_raw = outside.estimator.predict(X.iloc[split:])
            virtual = predicted_raw[:, :8]
            # Outer held house must not influence parameter selection, either.
            # At source points IDW is exact, so use a predeclared F configuration
            # for this G->F node check instead of reusing the all-house optimum.
            frozen = fit_field(prefix, remaining, list(range(8)), cfg, candidates[0])
            inputs = future.copy()
            if not spec.humidity: inputs['bg_rh'] = np.clip(predicted_raw[:, -1], 0, 100)
            chain = frozen.predict(inputs, virtual)
            cross_house.append(dict(house_id=held, training_houses=list(remaining), field_params=candidates[0],
                                    prediction_sha256=hashlib.sha256(chain.tobytes()).hexdigest(),
                                    **scores(y[split:], chain)))
        per_node = [dict(key=f'{house}/{position}', **scores(y[split:, i:i+1], prediction[split:, i:i+1]))
                    for house, y in houses.items() for i, position in enumerate(C.SENSOR_LAYOUT)]
        result['variants'].append(dict(key=key, label='一小时历史版' if historical else '单时刻版',
            training=scores(np.concatenate(list(train_houses.values())), np.tile(prediction[:split], (len(houses), 1))),
            validation=validation, per_node=per_node, feature_names=list(X.columns), humidity_mae_pct=None,
            cross_house=cross_house))
        models[key] = node
    result['bounds'] = {name: [float(prefix[name].min()), float(prefix[name].max())] for name in ('bg_temp', 'bg_light', 'bg_rh')}
    result['note'] = ('三座独立棚作为分组样本，G 输出单棚 8 点，F 的 IDW 只接收同棚来源。'
        'F 参数仅由训练时段 A 位置选择，B 位置在未来时段报告；整棚留出采用预先固定的 F 参数，同时隔离被测棚和未来时间。'
        '使用现有时间对齐数据，未进行新增现场独立试验。历史版需要连续 5 分钟气象序列。'
        '现有数据不记录棚内纵向坐标，不证明纵向三维、跨尺寸或跨季节精度。'
        '在虚拟来源点处 F 精确复现 G，测点链路成绩不能当作棚内未测区域的精度。')
    return result, models
