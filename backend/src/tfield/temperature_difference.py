"""Per-node daylight temperature-difference baseline, fitted on training rows only.

The light scale uses the input dataset's units, never an assumed W/m² conversion.
This is a static empirical baseline, not a validated winter heat-balance model.
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class TemperatureDifferenceFormula:
    coefficients: np.ndarray | None = None

    @staticmethod
    def design(weather):
        light = weather['bg_light'].to_numpy(float)
        outside = weather['bg_temp'].to_numpy(float)
        if not np.isfinite(light).all() or not np.isfinite(outside).all() or (light < 0).any():
            raise ValueError('温差公式需要有限的外温和非负光照。')
        return np.column_stack([np.ones(len(weather)), light / 10000.])

    def fit(self, weather, temperatures):
        design = self.design(weather)
        values = np.asarray(temperatures, float)
        if values.ndim != 2 or len(values) != len(weather) or not np.isfinite(values).all():
            raise ValueError('温差公式需要二维有限测点温度标签。')
        delta = values - weather['bg_temp'].to_numpy(float)[:, None]
        self.coefficients = np.linalg.lstsq(design, delta, rcond=None)[0]
        return self

    def predict(self, weather):
        if self.coefficients is None:
            raise ValueError('温差公式尚未拟合。')
        return weather['bg_temp'].to_numpy(float)[:, None] + self.design(weather) @ self.coefficients

    def report(self):
        return dict(definition='T_i = T_out + intercept_i + light_coefficient_i × (light / 10000)',
                    light_unit='与训练数据一致的光照单位，除以 10000 仅作尺度调整',
                    intercept=self.coefficients[0].tolist(),
                    light_coefficient=self.coefficients[1].tolist(),
                    prediction_target='temperature_difference', winter_validated=False)
