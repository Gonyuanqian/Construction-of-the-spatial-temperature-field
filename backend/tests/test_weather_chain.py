"""Weather-only boundary tests; no DB, network or production model writes."""
import numpy as np
import pandas as pd
import pytest

from tfield.weather_chain import WeatherFeatureSpec, WeatherNodeModel, WeatherFieldChain, weather_features


class MeanEstimator:
    def fit(self, X, y):
        self.mean = np.asarray(y).mean(axis=0)
        return self

    def predict(self, X):
        return np.tile(self.mean, (len(X), 1))


def external():
    return pd.DataFrame({'timestamp': pd.date_range('2026-07-23', periods=20, freq='5min'),
        'bg_temp': np.linspace(20, 25, 20), 'bg_rh': np.linspace(60, 80, 20),
        'bg_light': np.arange(20)*10.0})


class FrozenField:
    fitted = True
    coords = np.zeros((2, 3))

    def __init__(self, weather):
        self.n_times = len(weather)
        self.last = weather.timestamp.iloc[-1]
        self.received = []

    def time_at(self, index):
        return self.last

    def append_live_frame(self, **inputs):
        self.received.append(inputs)
        result = self.n_times
        self.n_times += 1
        self.last = inputs['ts']
        return result


def test_two_inputs_ignore_hidden_test_humidity_and_indoor_columns():
    w = external()
    model = WeatherNodeModel(WeatherFeatureSpec(False, True), MeanEstimator()).fit(w, np.ones((20, 2))*25)
    hidden = w.drop(columns='bg_rh').assign(indoor_temp=-999, indoor_rh=999)
    prediction, humidity = model.predict_with_humidity(hidden)
    np.testing.assert_array_equal(prediction, model.predict(w))
    np.testing.assert_array_equal(humidity, np.full(20, 70))


def test_future_weather_does_not_change_past_features():
    w = external()
    changed = w.copy()
    changed.loc[15:, ['bg_temp', 'bg_light', 'bg_rh']] += 10000
    pd.testing.assert_frame_equal(weather_features(w, WeatherFeatureSpec(True, True)).iloc[:15],
        weather_features(changed, WeatherFeatureSpec(True, True)).iloc[:15])


def test_history_rejects_unexplained_time_gaps():
    with pytest.raises(ValueError, match='contiguous'):
        weather_features(external().drop(index=10), WeatherFeatureSpec(True, True))


def test_two_input_stream_uses_predicted_humidity_and_marks_virtual_source():
    w = external()
    model = WeatherNodeModel(WeatherFeatureSpec(False, True), MeanEstimator()).fit(w, np.ones((20, 2))*25)
    field = FrozenField(w)
    chain = WeatherFieldChain(model, field, w)
    result = chain.step(timestamp=w.timestamp.iloc[-1]+pd.Timedelta(minutes=5), bg_temp=24, bg_light=100)
    assert field.received[0]['bg_rh'] == pytest.approx(70)
    assert result['source'] == 'virtual_weather_prediction'
    assert result['t_index'] == 20
    np.testing.assert_array_equal(field.received[0]['sensor_temps'], [25, 25])


@pytest.mark.parametrize('bad', ['duplicate', 'nan', 'missing_humidity'])
def test_invalid_online_frame_does_not_advance_second_stage(bad):
    w = external()
    model = WeatherNodeModel(WeatherFeatureSpec(True, True), MeanEstimator()).fit(w, np.ones((20, 2))*25)
    field = FrozenField(w)
    chain = WeatherFieldChain(model, field, w)
    inputs = {'timestamp': w.timestamp.iloc[-1]+pd.Timedelta(minutes=5), 'bg_temp': 24, 'bg_light': 100, 'bg_rh': 60}
    if bad == 'duplicate': inputs['timestamp'] = w.timestamp.iloc[-1]
    if bad == 'nan': inputs['bg_light'] = np.nan
    if bad == 'missing_humidity': inputs.pop('bg_rh')
    with pytest.raises(ValueError):
        chain.step(**inputs)
    assert field.n_times == 20
    assert field.received == []
