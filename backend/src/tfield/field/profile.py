"""Height-wise temperature summaries from the same visible volume grid."""
import math


def height_temperature_profile(z, planes):
    """Average all finite in-roof predictions at each z across x/y.

    Missing heights remain null. Cells are pooled before averaging so sections
    with fewer available cells do not receive the same weight as full sections.
    """
    profile = []
    for iz, height in enumerate(z):
        values = [value for plane in planes for value in plane['values'][iz]
                  if value is not None and math.isfinite(value)]
        profile.append({'z': float(height), 'mean': math.fsum(values) / len(values) if values else None})
    return profile
