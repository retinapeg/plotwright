"""Closed conversion registry; callers cannot supply numeric factors."""
import numpy as np

_UNITS = {
    'm': ('length', 1., 0.), 'cm': ('length', .01, 0.),
    'mm': ('length', .001, 0.), 'um': ('length', 1e-6, 0.),
    's': ('time', 1., 0.), 'ms': ('time', .001, 0.), 'us': ('time', 1e-6, 0.),
    'GeV': ('energy', 1000., 0.), 'MeV': ('energy', 1., 0.), 'keV': ('energy', .001, 0.),
    'rad': ('angle', 1., 0.), 'deg': ('angle', np.pi / 180, 0.),
    'K': ('temperature', 1., 0.), 'C': ('temperature', 1., 273.15),
}


def conversion(from_unit, to_unit):
    try:
        a, b = _UNITS[from_unit], _UNITS[to_unit]
    except KeyError as exc:
        raise ValueError('Unknown unit pair') from exc
    if a[0] != b[0]:
        raise ValueError('Incompatible unit pair')
    return a[1] / b[1], (a[2] - b[2]) / b[1]


def factor(from_unit, to_unit):
    scale, offset = conversion(from_unit, to_unit)
    if offset:
        raise ValueError('Affine temperature conversion requires a fixed offset')
    return scale
