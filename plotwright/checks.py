from typing import Literal
import json
import numpy as np
import pandas as pd
from pydantic import BaseModel
from .units import conversion
from .recipe import series_specs
from .exclusions import equal, check_artists, exclusion_issues


class Check(BaseModel):
    name: str
    status: Literal['PASS', 'WARN', 'FAIL']
    detail: str


def run_checks(df, manifest, recipe, result):
    checks = []
    def add(name, status, detail): checks.append(Check(name=name, status=status, detail=detail))
    specs = series_specs(recipe)
    all_plotted = result.plotted.get('series', [])
    expected_groups = len(specs) * (2 if recipe.residuals else 1)
    structure_ok = len(all_plotted) == len(specs) and len(result.groups) == expected_groups and len(result.fig.axes) == (2 if recipe.residuals else 1)
    if not structure_ok:
        add('data_lock', 'FAIL', 'Series or panel count differs from the recipe')
        return checks
    # Catch modifications to the legacy single-series view too.
    if not all(equal(result.plotted[k], all_plotted[0][k]) for k in ('x', 'y', 'xerr', 'yerr', 'indices', 'invalid_indices', 'excluded', 'x_lim', 'y_lim')):
        add('data_lock', 'FAIL', 'Primary-series view differs from recorded series')
    def values(column, valid, uncertainty=False, paired=None):
        if column is None: return None
        scale, offset = 1., 0.
        for t in recipe.transforms:
            if t.column == (paired if uncertainty else column): scale, offset = conversion(t.from_unit, t.to_unit)
        return pd.to_numeric(df[column], errors='coerce').to_numpy(dtype=float)[valid] * (abs(scale) if uncertainty else scale) + (0 if uncertainty else offset)
    group_index = 0
    all_issues = []
    for si, spec in enumerate(specs):
        for panel in (['main', 'residual'] if recipe.residuals else ['main']):
            p = all_plotted[si] if panel == 'main' else all_plotted[si].get('residual', {})
            group = result.groups[group_index]
            group_index += 1
            ax = result.fig.axes[0 if panel == 'main' else 1]
            suffix = '' if len(specs) == 1 and panel == 'main' else f'[{spec.y}{":residual" if panel == "residual" else ""}]'
            cols = [c for c in (recipe.x, spec.y, recipe.x_err, spec.y_err) if c]
            if panel == 'residual': cols.append(recipe.residuals.against)
            numeric = df[list(dict.fromkeys(cols))].apply(pd.to_numeric, errors='coerce')
            valid = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
            indices = np.flatnonzero(valid)
            expected = {'x': values(recipe.x, valid), 'y': values(spec.y, valid), 'xerr': values(recipe.x_err, valid, True, recipe.x), 'yerr': values(spec.y_err, valid, True, spec.y)}
            if panel == 'residual': expected['y'] -= values(recipe.residuals.against, valid)
            excluded = np.isin(indices, [e.row_index for e in recipe.exclusions])
            locked = equal(p.get('x_lim'), ax.get_xlim()) and equal(p.get('y_lim'), ax.get_ylim()) and equal(p.get('indices'), indices) and equal(p.get('excluded'), excluded) and all(equal(p.get(k), expected[k]) for k in expected)
            locked &= group['series'] == spec.y and group['panel'] == panel and group['axes'] is ax
            artists_ok, errors_ok = check_artists(ax, group['containers'], expected, excluded)
            add('data_lock' + suffix, 'PASS' if locked and artists_ok and errors_ok else 'FAIL', 'Source values, row order and drawn artists compared at rtol=1e-12')
            invalid = set(np.flatnonzero(~valid).tolist())
            documented = {row for row, col, reason in manifest.invalid_cells if col in cols}
            accounted = len(df) == manifest.n_rows and equal(p.get('indices'), indices) and set(p.get('invalid_indices', [])) == invalid and invalid <= documented
            add('rows_accounted' + suffix, 'PASS' if accounted else 'FAIL', f'Plotted {len(indices)} of {manifest.n_rows}; invalid source row indices: {sorted(invalid)}')
            hidden = indices[(expected['x'] < ax.get_xlim()[0]) | (expected['x'] > ax.get_xlim()[1]) | (expected['y'] < ax.get_ylim()[0]) | (expected['y'] > ax.get_ylim()[1])]
            add('hidden_points' + suffix, 'WARN' if len(hidden) else 'PASS', f'{len(hidden)} points outside limits; source row indices: {hidden.tolist()}')
            scaled = errors_ok and all(equal(p.get(k), expected[k]) for k in ('xerr', 'yerr'))
            add('uncertainty_scaled' + suffix, 'PASS' if scaled else 'FAIL', 'Uncertainties compared with paired value conversion scales and drawn error bars')
            all_issues.extend(f'{spec.y}/{panel}: {issue}' for issue in exclusion_issues(recipe, p, ax, group['containers']))
    # Additional data artists cannot silently bypass the recorded-series checks.
    registered_lines = [c.lines[0] for g in result.groups for c in g['containers']]
    registered_collections = [a for g in result.groups for c in g['containers'] for a in c.lines[2]]
    if sum(len(ax.lines) for ax in result.fig.axes) != len(registered_lines) or sum(len(ax.collections) for ax in result.fig.axes) != len(registered_collections):
        add('data_lock', 'FAIL', 'Unrecorded data artist')
    add('exclusions', 'FAIL' if all_issues else 'PASS', json.dumps({'records': [e.model_dump() for e in recipe.exclusions], 'issues': all_issues}, sort_keys=True))
    xax = result.fig.axes[-1]
    labels = (not recipe.x_unit or f'[{recipe.x_unit}]' in xax.get_xlabel()) and all(not recipe.y_unit or f'[{recipe.y_unit}]' in ax.get_ylabel() for ax in result.fig.axes)
    add('labels_units', 'PASS' if labels else 'FAIL', 'Declared units must appear in square brackets')
    visible = bool(result.artists) and all(ax.get_visible() for ax in result.fig.axes) and all(a.get_visible() and (a.get_alpha() is None or a.get_alpha() > 0) for a in result.artists)
    visible &= all(line.get_marker() not in (None, 'None', '', ' ') or line.get_linestyle() not in (None, 'None', '', ' ') for line in registered_lines)
    add('visibility', 'PASS' if visible else 'FAIL', 'Data artists must be visible with a marker or line')
    dropped = any((g['axes'].get_xscale() == 'log' and np.any(g['plotted']['x'] <= 0)) or (g['axes'].get_yscale() == 'log' and np.any(g['plotted']['y'] <= 0)) for g in result.groups)
    add('log_axis_valid', 'WARN' if dropped else 'PASS', 'Non-positive points on logarithmic axes' if dropped else 'No points dropped by log scaling')
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    if not hasattr(result.fig.canvas, 'get_renderer'): FigureCanvasAgg(result.fig)
    result.fig.canvas.draw()
    renderer, bbox = result.fig.canvas.get_renderer(), result.fig.bbox
    clipped = []
    for ax in result.fig.axes:
        tick_labels = [tick.label1 for axis in (ax.xaxis, ax.yaxis) for tick in axis.get_major_ticks() if min(axis.get_view_interval()) <= tick.get_loc() <= max(axis.get_view_interval())]
        for artist in [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.texts, *result.fig.texts, *tick_labels, ax.get_legend()]:
            if artist is None or not artist.get_visible(): continue
            if hasattr(artist, 'get_text') and not artist.get_text(): continue
            b = artist.get_window_extent(renderer)
            if b.width and b.height and (b.x0 < bbox.x0 or b.y0 < bbox.y0 or b.x1 > bbox.x1 or b.y1 > bbox.y1): clipped.append(type(artist).__name__)
    add('readability', 'WARN' if clipped else 'PASS', f'Objects outside figure bbox: {clipped}')
    return checks
