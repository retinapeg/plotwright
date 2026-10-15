from typing import Literal
import numpy as np
import pandas as pd
from pydantic import BaseModel
from .units import conversion


class Check(BaseModel):
    name: str
    status: Literal['PASS', 'WARN', 'FAIL']
    detail: str


def run_checks(df, manifest, recipe, result):
    p, ax = result.plotted, result.fig.axes[0]
    checks = []
    def add(name, status, detail): checks.append(Check(name=name, status=status, detail=detail))
    def equal(a, b):
        return a is None and b is None or (a is not None and b is not None and np.shape(a) == np.shape(b) and np.allclose(a, b, rtol=1e-12, atol=0, equal_nan=False))
    columns = [c for c in (recipe.x, recipe.y, recipe.x_err, recipe.y_err) if c]
    numeric = df[columns].apply(pd.to_numeric, errors='coerce')
    valid = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    indices = np.flatnonzero(valid)
    expected = {}
    for axis in ('x', 'y'):
        scale, offset = 1., 0.
        for t in recipe.transforms:
            if t.column == getattr(recipe, axis): scale, offset = conversion(t.from_unit, t.to_unit)
        expected[axis] = numeric.loc[valid, getattr(recipe, axis)].to_numpy(dtype=float) * scale + offset
        err = getattr(recipe, axis + '_err')
        expected[axis + 'err'] = numeric.loc[valid, err].to_numpy(dtype=float) * abs(scale) if err else None
    locked = equal(p['x_lim'], ax.get_xlim()) and equal(p['y_lim'], ax.get_ylim()) and equal(p['indices'], indices) and all(equal(p[k], expected[k]) for k in expected)
    # Check the artist itself as well as the recorded arrays.
    line = ax.lines[0] if ax.lines else None
    locked = locked and line is not None and equal(line.get_xdata(), expected['x']) and equal(line.get_ydata(), expected['y'])
    actual_segments = [c.get_segments() for c in ax.collections if hasattr(c, 'get_segments')]
    expected_segments = []
    for axis in ('x', 'y'):
        if expected[axis + 'err'] is not None:
            x, y, e = expected['x'], expected['y'], expected[axis + 'err']
            expected_segments.append(np.array([[[a-b, c], [a+b, c]] if axis == 'x' else [[a, c-b], [a, c+b]] for a, c, b in zip(x, y, e)]))
    errors_ok = len(actual_segments) == len(expected_segments) and all(equal(a, b) for a, b in zip(actual_segments, expected_segments))
    add('data_lock', 'PASS' if locked and errors_ok else 'FAIL', 'Source values, row order and drawn artists compared at rtol=1e-12')
    invalid = set(np.flatnonzero(~valid).tolist())
    documented = {row for row, col, reason in manifest.invalid_cells if col in columns}
    accounted = len(df) == manifest.n_rows and equal(p['indices'], indices) and set(p['invalid_indices']) == invalid and invalid <= documented
    add('rows_accounted', 'PASS' if accounted else 'FAIL', f'Plotted {len(indices)} of {manifest.n_rows}; invalid source row indices: {sorted(invalid)}')
    hidden = indices[(expected['x'] < ax.get_xlim()[0]) | (expected['x'] > ax.get_xlim()[1]) | (expected['y'] < ax.get_ylim()[0]) | (expected['y'] > ax.get_ylim()[1])]
    add('hidden_points', 'WARN' if len(hidden) else 'PASS', f'{len(hidden)} points outside limits; source row indices: {hidden.tolist()}')
    scaled = errors_ok and all(equal(p[k], expected[k]) for k in ('xerr', 'yerr'))
    add('uncertainty_scaled', 'PASS' if scaled else 'FAIL', 'Uncertainties compared with paired value conversion scales and drawn error bars')
    labels = all(not getattr(recipe, a + '_unit') or f'[{getattr(recipe, a + "_unit")}]' in getattr(ax, 'get_' + a + 'label')() for a in ('x', 'y'))
    add('labels_units', 'PASS' if labels else 'FAIL', 'Declared units must appear in square brackets')
    visible = bool(result.artists) and ax.get_visible() and all(a.get_visible() and (a.get_alpha() is None or a.get_alpha() > 0) for a in result.artists)
    if line is not None:
        visible = visible and (line.get_marker() not in (None, 'None', '', ' ') or line.get_linestyle() not in (None, 'None', '', ' '))
    add('visibility', 'PASS' if visible else 'FAIL', 'Data artists must be visible with a marker or line')
    dropped = any(getattr(recipe, a + '_scale') == 'log' and np.any(p[a] <= 0) for a in ('x', 'y'))
    add('log_axis_valid', 'WARN' if dropped else 'PASS', 'Non-positive points on logarithmic axes' if dropped else 'No points dropped by log scaling')
    result.fig.canvas.draw()
    renderer = result.fig.canvas.get_renderer()
    bbox = result.fig.bbox
    clipped = []
    tick_labels = [tick.label1 for axis in (ax.xaxis, ax.yaxis) for tick in axis.get_major_ticks() if min(axis.get_view_interval()) <= tick.get_loc() <= max(axis.get_view_interval())]
    for artist in [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.texts, *result.fig.texts, *tick_labels, ax.get_legend()]:
        if artist is None or not artist.get_visible(): continue
        if hasattr(artist, 'get_text') and not artist.get_text(): continue
        b = artist.get_window_extent(renderer)
        if b.width and b.height and (b.x0 < bbox.x0 or b.y0 < bbox.y0 or b.x1 > bbox.x1 or b.y1 > bbox.y1): clipped.append(type(artist).__name__)
    add('readability', 'WARN' if clipped else 'PASS', f'Objects outside figure bbox: {clipped}')
    return checks
