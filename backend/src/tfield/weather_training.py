"""Train G on external weather only, with a chronological temperature holdout."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config as C
from .weather_chain import WeatherFeatureSpec, WeatherNodeModel, weather_features


DEFAULTS = dict(name='气象映射模型 G', external_schema='full', algorithm='extra_trees',
                validation_fraction=.2, n_estimators=120, max_depth=12,
                min_samples_leaf=2, alpha=10., seed=42, spatial_protocol='legacy_multi_house_v1', workbench=None)


def options(raw: dict) -> dict:
    if set(raw) - set(DEFAULTS):
        raise ValueError('G 训练包含未知配置。')
    value = DEFAULTS | raw
    if value['spatial_protocol'] not in ('legacy_multi_house_v1', 'independent_house_section_v2'):
        raise ValueError('训练空间协议无效。')
    if not isinstance(value['name'], str) or not 1 <= len(value['name'].strip()) <= 120:
        raise ValueError('G 模型名称需为 1 至 120 个字符。')
    value['name'] = value['name'].strip()
    if value['workbench'] is not None:
        if value['spatial_protocol']!='independent_house_section_v2':raise ValueError('新训练工作台仅支持独立单棚数据。')
        from .training_workbench import configuration
        value['workbench']=configuration(value['workbench'])
    if value['external_schema'] not in ('two', 'full') or value['algorithm'] not in ('extra_trees', 'ridge'):
        raise ValueError('G 输入方案或算法无效。')
    for key, low, high in (('n_estimators', 16, 300), ('max_depth', 2, 24), ('min_samples_leaf', 1, 20), ('seed', 0, 2147483647)):
        if isinstance(value[key], bool) or not isinstance(value[key], int) or not low <= value[key] <= high:
            raise ValueError(f'{key} 超出允许范围。')
    for key, low, high in (('validation_fraction', .1, .4), ('alpha', .001, 10000.)):
        if isinstance(value[key], bool) or not isinstance(value[key], (int, float)) or not np.isfinite(value[key]) or not low <= value[key] <= high:
            raise ValueError(f'{key} 超出允许范围。')
    return value


def arrays(ds):
    wide = ds.wide.reset_index(drop=True)
    weather = pd.DataFrame({'timestamp': pd.to_datetime(wide[C.COL_TIMESTAMP]),
        'bg_temp': wide[C.BG_TEMP], 'bg_light': wide[C.BG_LIGHT], 'bg_rh': wide[C.BG_RH]})
    columns = [f'{s}_{p}_{C.VAR_TEMP}' for s in C.SHED_ORDER for p in C.SENSOR_LAYOUT]
    return weather, wide[columns].to_numpy(float), columns


def describe(ds):
    weather, y, columns = arrays(ds)
    x = weather[['bg_temp', 'bg_light', 'bg_rh']].to_numpy(float)
    invalid = (~np.isfinite(x).all(axis=1) | ~np.isfinite(y).all(axis=1)
               | (x[:, 1] < 0) | (x[:, 2] < 0) | (x[:, 2] > 100))
    n = len(weather)
    return dict(n_frames=n, n_nodes=len(columns), invalid_rows=int(invalid.sum()),
        time_start=weather.timestamp.iloc[0].isoformat() if n else None,
        time_end=weather.timestamp.iloc[-1].isoformat() if n else None,
        ready=n >= 80 and not invalid.any(),
        reason='至少需要 80 个时刻。' if n < 80 else '外部气象或棚内温度存在缺失、非有限值或无效湿度/光照，请先清理数据。' if invalid.any() else '',
        inputs=[dict(key='bg_temp', label='背景温度', unit='℃'), dict(key='bg_light', label='背景光照强度', unit='源数据单位'), dict(key='bg_rh', label='背景湿度', unit='%')])


def causal_features(weather, spec):
    if not spec.history:
        return weather_features(weather, spec)
    # 时间断档后重新冷启动；只用当前与过去的外部数据，不跨缺口借用历史。
    segments = weather.timestamp.diff().ne(pd.Timedelta(minutes=5)).cumsum()
    return pd.concat([weather_features(group, spec) for _, group in weather.groupby(segments, sort=False)]).sort_index()


def scores(actual, predicted):
    error = np.asarray(predicted) - np.asarray(actual)
    mse = np.mean(error ** 2)
    centered = np.asarray(actual) - np.mean(actual, axis=0)
    denominator = np.sum(centered ** 2, axis=0)
    mask = denominator > 0
    r2 = np.mean(1 - np.sum(error ** 2, axis=0)[mask] / denominator[mask]) if mask.any() else None
    return dict(mae=float(np.mean(np.abs(error))), rmse=float(np.sqrt(mse)),
                r2=float(r2) if r2 is not None else None, n=int(error.size))


def train(ds, raw: dict, checkpoint=lambda _: None):
    cfg = options(raw)
    if cfg['workbench'] is not None:
        from .training_workbench import train as train_workbench
        return train_workbench(ds,cfg,checkpoint)
    if cfg['spatial_protocol'] == 'independent_house_section_v2':
        from .independent_training import train as train_independent
        return train_independent(ds, cfg, checkpoint)
    description = describe(ds)
    if not description['ready']:
        raise ValueError(description['reason'])
    weather, y, columns = arrays(ds)
    ts = weather.timestamp
    if ts.isna().any() or ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise ValueError('G 训练需要严格递增且不重复的时间轴。')
    split = int(len(weather) * (1 - cfg['validation_fraction']))
    humidity = cfg['external_schema'] == 'full'
    target = y if humidity else np.column_stack([y, weather.bg_rh])
    result = dict(protocol_version=1, options=cfg, dataset=description,
        split=dict(method='chronological', train_frames=split, validation_frames=len(weather)-split,
            train_start=ts.iloc[0].isoformat(), train_end=ts.iloc[split-1].isoformat(),
            validation_start=ts.iloc[split].isoformat(), validation_end=ts.iloc[-1].isoformat()),
        baseline=scores(y[split:], np.repeat(weather.bg_temp.to_numpy()[split:, None], 24, axis=1)), variants=[])
    models = {}
    for historical in (False, True):
        key = 'history' if historical else 'current'
        checkpoint('正在训练一小时历史版 G' if historical else '正在训练单时刻版 G')
        spec = WeatherFeatureSpec(humidity=humidity, history=historical)
        X = causal_features(weather, spec)
        estimator = ExtraTreesRegressor(n_estimators=cfg['n_estimators'], max_depth=cfg['max_depth'],
            min_samples_leaf=cfg['min_samples_leaf'], random_state=cfg['seed'], n_jobs=2) if cfg['algorithm'] == 'extra_trees' else make_pipeline(StandardScaler(), Ridge(alpha=cfg['alpha']))
        model = WeatherNodeModel(spec, estimator, tuple(X.columns), 24)
        # 留出段的棚内标签和湿度标签不参与拟合；仅外部气象用于因果历史特征。
        estimator.fit(X.iloc[:split], target[:split])
        checkpoint('正在计算时间留出验证')
        pred = estimator.predict(X)
        per_node = [dict(key=column, **scores(y[split:, i:i+1], pred[split:, i:i+1])) for i, column in enumerate(columns)]
        result['variants'].append(dict(key=key, label='一小时历史版' if historical else '单时刻版',
            training=scores(y[:split], pred[:split, :24]), validation=scores(y[split:], pred[split:, :24]),
            humidity_mae_pct=float(np.mean(np.abs(weather.bg_rh.to_numpy()[split:] - np.clip(pred[split:, -1], 0, 100)))) if not humidity else None,
            per_node=per_node, feature_names=list(X.columns)))
        models[key] = model
    result['bounds'] = {key: [float(weather[key].iloc[:split].min()), float(weather[key].iloc[:split].max())] for key in ('bg_temp', 'bg_light', 'bg_rh')}
    result['note'] = '成品仅使用前段训练数据；尾部按时间留出，不参与拟合。该结果不代表跨地区或全空间精度。'
    checkpoint('正在保存 G 模型成品')
    return result, models
