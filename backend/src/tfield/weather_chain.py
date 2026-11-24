"""Weather-only virtual sensors feeding an independently frozen FieldPipeline.

Online inputs contain external weather only. Indoor temperatures are training
labels for WeatherNodeModel and never enter its feature builder. All values
passed to append_live_frame by WeatherFieldChain are explicitly predictions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

WEATHER_COLUMNS = ('timestamp', 'bg_temp', 'bg_rh', 'bg_light')


@dataclass(frozen=True)
class WeatherFeatureSpec:
    humidity: bool = True
    history: bool = False


def weather_features(weather: pd.DataFrame, spec: WeatherFeatureSpec) -> pd.DataFrame:
    """Deterministic, causal external features; history uses at most one hour.

    The dataset used in the experiment has a 5-minute interval. History therefore
    requires contiguous 5-minute frames. At the very beginning, lagged values
    use the first available external reading, with no indoor initial condition.
    """
    required = ['timestamp', 'bg_temp', 'bg_light'] + (['bg_rh'] if spec.humidity else [])
    missing = set(required) - set(weather.columns)
    if missing:
        raise ValueError(f'Missing external inputs: {sorted(missing)}')
    ts = pd.to_datetime(weather['timestamp'])
    if ts.isna().any() or ts.duplicated().any() or not ts.is_monotonic_increasing:
        raise ValueError('Weather timestamps must be unique and increasing')
    if not np.isfinite(weather[required[1:]].to_numpy(float)).all():
        raise ValueError('External weather must be finite')
    if spec.history and len(ts) > 1 and not (ts.diff().iloc[1:] == pd.Timedelta(minutes=5)).all():
        raise ValueError('One-hour history requires contiguous 5-minute external frames')
    out = pd.DataFrame(index=weather.index)
    out['bg_temp'] = weather['bg_temp'].astype(float)
    out['bg_light'] = weather['bg_light'].astype(float)
    out['log_light'] = np.log1p(np.maximum(out['bg_light'], 0))
    if spec.humidity:
        out['bg_rh'] = weather['bg_rh'].astype(float)
    hour = ts.dt.hour + ts.dt.minute / 60
    out['hour_sin'] = np.sin(2*np.pi*hour/24)
    out['hour_cos'] = np.cos(2*np.pi*hour/24)
    if spec.history:
        for name in ['bg_temp', 'log_light'] + (['bg_rh'] if spec.humidity else []):
            values = out[name]
            for lag in (3, 6, 12):
                out[f'{name}_lag{lag}'] = values.shift(lag).fillna(float(values.iloc[0]))
            out[f'{name}_mean1h'] = values.rolling(12, min_periods=1).mean()
            out[f'{name}_delta1h'] = values-out[f'{name}_lag12']
    return out


@dataclass
class WeatherNodeModel:
    """A separately fitted estimator producing all fixed-layout virtual nodes."""
    spec: WeatherFeatureSpec
    estimator: Any
    feature_names: tuple[str, ...] = ()
    n_nodes: int = 0
    prediction_target: str = 'absolute'

    def fit(self, weather: pd.DataFrame, temperatures: np.ndarray) -> 'WeatherNodeModel':
        X = weather_features(weather, self.spec)
        y = np.asarray(temperatures, dtype=float)
        if y.ndim != 2 or len(y) != len(X) or not np.isfinite(y).all():
            raise ValueError('Training labels must be finite (n_frames, n_nodes)')
        self.feature_names = tuple(X.columns)
        self.n_nodes = y.shape[1]
        if self.prediction_target not in ('absolute', 'delta'):
            raise ValueError('Unknown temperature prediction target')
        if self.prediction_target == 'delta':
            y = y - weather['bg_temp'].to_numpy(float)[:, None]
        if not self.spec.humidity:
            # Predict the humidity required by the frozen second stage, without
            # reading the test humidity in this two-input configuration.
            rh = weather['bg_rh'].to_numpy(float)
            if not np.isfinite(rh).all():
                raise ValueError('Training requires background humidity labels')
            y = np.column_stack([y, rh])
        self.estimator.fit(X, y)
        return self

    def predict_with_humidity(self, weather: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        if not self.feature_names:
            raise RuntimeError('Virtual node model must be fitted first')
        X = weather_features(weather, self.spec)
        if tuple(X.columns) != self.feature_names:
            raise ValueError('External feature schema changed')
        result = np.asarray(self.estimator.predict(X), dtype=float)
        expected = self.n_nodes + (not self.spec.humidity)
        if result.shape != (len(weather), expected) or not np.isfinite(result).all():
            raise ValueError('Invalid virtual node predictions')
        rh = weather['bg_rh'].to_numpy(float) if self.spec.humidity else np.clip(result[:, -1], 0, 100)
        temperatures = result[:, :self.n_nodes].copy()
        # Old deployment pickles do not carry this field and remain absolute models.
        if getattr(self, 'prediction_target', 'absolute') == 'delta':
            temperatures += weather['bg_temp'].to_numpy(float)[:, None]
        return temperatures, rh

    def predict(self, weather: pd.DataFrame) -> np.ndarray:
        return self.predict_with_humidity(weather)[0]


class WeatherFieldChain:
    """Sequential weather -> virtual nodes -> existing frozen field pipeline.

    Construction requires a fitted/restored second-stage pipeline and its last
    external frames. The second stage is never fitted by this adapter. In the
    two-input configuration, stage one also predicts background humidity.
    """
    def __init__(self, nodes: WeatherNodeModel, field_pipeline: Any,
                 history_weather: pd.DataFrame):
        if not field_pipeline.fitted:
            raise ValueError('Second-stage model must already be fitted')
        if nodes.n_nodes != len(field_pipeline.coords):
            raise ValueError('Virtual node count does not match the fixed layout')
        self.nodes = nodes
        self.field = field_pipeline
        self._history = history_weather.loc[:, list(WEATHER_COLUMNS)].tail(12).copy().reset_index(drop=True)
        if self._history.empty or pd.Timestamp(self._history.timestamp.iloc[-1]) != self.field.time_at(self.field.n_times-1):
            raise ValueError('External history must end at the second-stage cursor')

    def step(self, *, timestamp, bg_temp: float, bg_light: float, bg_rh: float | None = None) -> dict:
        values = np.asarray([bg_temp, bg_light] + ([bg_rh] if self.nodes.spec.humidity else []), dtype=float)
        if not np.isfinite(values).all():
            raise ValueError('Required external weather must be finite')
        when = pd.Timestamp(timestamp)
        if pd.isna(when) or when <= self.field.time_at(self.field.n_times-1):
            raise ValueError('New weather timestamp must follow the current cursor')
        row = pd.DataFrame([[when, float(bg_temp), bg_rh if self.nodes.spec.humidity else np.nan, float(bg_light)]], columns=WEATHER_COLUMNS)
        history = pd.concat([self._history, row], ignore_index=True)
        predictions, humidity = self.nodes.predict_with_humidity(history)
        virtual = predictions[-1]
        rh = float(humidity[-1])
        index = self.field.append_live_frame(bg_temp=float(bg_temp), bg_rh=rh,
            bg_light=float(bg_light), ts=when, sensor_temps=virtual)
        self._history = history.tail(12).reset_index(drop=True)
        return {'t_index': index, 'timestamp': when, 'source': 'virtual_weather_prediction',
                'node_temperatures': virtual.copy(), 'background_humidity_used': rh}
