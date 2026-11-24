import math

import pytest

from tfield.field.profile import height_temperature_profile


def test_height_profile_pools_all_predictions_and_excludes_only_missing_values():
    planes = [
        {'values': [[10, 20, None], [30, 40, 50], [None, math.nan, None]]},
        {'values': [[40, None, None], [60, 70, math.inf], [None, math.inf, None]]},
    ]
    profile = height_temperature_profile([0, .5, 1.], planes)
    assert profile[0] == {'z': 0., 'mean': pytest.approx(70 / 3)}
    assert profile[1] == {'z': .5, 'mean': 50.}
    assert profile[2] == {'z': 1., 'mean': None}


def test_vertical_gradient_is_retained_when_longitudinal_means_are_identical():
    planes = [{'values': [[20, 20], [22, 22], [24, 24]]} for _ in range(3)]
    assert height_temperature_profile([0, .5, 1.], planes) == [
        {'z': 0., 'mean': 20.}, {'z': .5, 'mean': 22.}, {'z': 1., 'mean': 24.}]
