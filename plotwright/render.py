from dataclasses import dataclass, field
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from .recipe import validate, label_with_unit, series_specs, referenced_columns
from .units import conversion
from .exclusions import draw_data


@dataclass
class RenderResult:
    fig: object
    plotted: dict
    operations: list[dict] = field(default_factory=list)
    artists: list = field(default_factory=list)
    groups: list = field(default_factory=list)


def render(df, manifest, recipe):
    recipe = validate(recipe, manifest)
    specs = series_specs(recipe)
    columns = referenced_columns(recipe)
    numeric = df[columns].apply(pd.to_numeric, errors='coerce')
    transformed = {c: numeric[c].to_numpy(dtype=float).copy() for c in columns}
    operations = [{'operation': 'load', 'sha256': manifest.sha256, 'columns': columns}]
    scaled_errors = {}
    for t in recipe.transforms:
        scale, offset = conversion(t.from_unit, t.to_unit)
        transformed[t.column] = transformed[t.column] * scale + offset
        operations.append({'operation': 'transform', 'column': t.column, 'from_unit': t.from_unit, 'to_unit': t.to_unit, 'factor': scale, 'offset': offset})
        pairs = [(recipe.x, recipe.x_err), *[(s.y, s.y_err) for s in specs]]
        for value, err in pairs:
            if t.column == value and err:
                # The same uncertainty column may be shared; never multiply twice.
                if err in scaled_errors and scaled_errors[err] != abs(scale):
                    raise ValueError('Shared uncertainty columns require the same conversion scale')
                scaled_errors[err] = abs(scale)
                transformed[err] = numeric[err].to_numpy(dtype=float) * abs(scale)
                operations.append({'operation': 'uncertainty_transform', 'column': err, 'factor': abs(scale), 'paired_column': value})
    plotted_series, artists, groups = [], [], []
    from .presets import apply_preset, preset_rc, VERSION
    with matplotlib.rc_context(matplotlib.rcParamsDefault):
        matplotlib.rcParams.update(preset_rc(recipe.style_preset))
        if recipe.residuals:
            fig, axes = plt.subplots(2, 1, sharex=True, gridspec_kw={'height_ratios': [3, 1]}, figsize=(recipe.fig_width_cm / 2.54, recipe.fig_height_cm / 2.54), dpi=100, layout='constrained')
            ax, residual_ax = axes
        else:
            fig, ax = plt.subplots(figsize=(recipe.fig_width_cm / 2.54, recipe.fig_height_cm / 2.54), dpi=100, layout='constrained')
            residual_ax = None
        try:
            for spec in specs:
                cols = [c for c in (recipe.x, spec.y, recipe.x_err, spec.y_err) if c]
                valid = np.isfinite(numeric[cols].to_numpy(dtype=float)).all(axis=1)
                p = {'column': spec.y, 'label': spec.label, 'indices': np.flatnonzero(valid), 'invalid_indices': np.flatnonzero(~valid)}
                for key, col in [('x', recipe.x), ('y', spec.y), ('xerr', recipe.x_err), ('yerr', spec.y_err)]:
                    p[key] = transformed[col][valid].copy() if col else None
                for axis in ('x', 'y'):
                    if getattr(recipe, axis + '_scale') == 'log' and np.any(p[axis] <= 0): raise ValueError(f'Log scale requires positive transformed {axis}')
                    if p[axis + 'err'] is not None and np.any(p[axis + 'err'] < 0): raise ValueError('Uncertainties must be nonnegative')
                containers = draw_data(ax, p, recipe, spec.label)
                groups.append({'series': spec.y, 'panel': 'main', 'axes': ax, 'containers': containers, 'plotted': p})
                if recipe.residuals:
                    reference = recipe.residuals.against
                    residual_valid = valid & np.isfinite(numeric[reference].to_numpy(dtype=float))
                    r = {'column': spec.y, 'against': reference, 'indices': np.flatnonzero(residual_valid), 'invalid_indices': np.flatnonzero(~residual_valid)}
                    for key, col in [('x', recipe.x), ('y', spec.y), ('xerr', recipe.x_err), ('yerr', spec.y_err)]:
                        r[key] = transformed[col][residual_valid].copy() if col else None
                    r['y'] -= transformed[reference][residual_valid]
                    residual_containers = draw_data(residual_ax, r, recipe, spec.label)
                    p['residual'] = r
                    groups.append({'series': spec.y, 'panel': 'residual', 'axes': residual_ax, 'containers': residual_containers, 'plotted': r})
                    operations.append({'operation': 'residual', 'column': spec.y, 'against': reference, 'indices': r['indices'].tolist(), 'uncertainty': spec.y_err, 'reference_treated_as_exact': True})
                operations.append({'operation': 'draw', 'column': spec.y, 'indices': p['indices'].tolist(), 'invalid_indices': p['invalid_indices'].tolist()})
                plotted_series.append(p)
            ax.set(xlabel='' if residual_ax else label_with_unit(recipe.x_label, recipe.x_unit), ylabel=label_with_unit(recipe.y_label, recipe.y_unit), title=recipe.title or '', xscale=recipe.x_scale, yscale=recipe.y_scale)
            if recipe.x_lim: ax.set_xlim(*recipe.x_lim)
            if recipe.y_lim: ax.set_ylim(*recipe.y_lim)
            if residual_ax:
                residual_ax.set(xlabel=label_with_unit(recipe.x_label, recipe.x_unit), ylabel=label_with_unit('Residual', recipe.y_unit), xscale=recipe.x_scale)
            for axis_obj in fig.axes:
                for axis in ('x', 'y'):
                    digits = getattr(recipe, 'sig_figs_' + axis)
                    getattr(axis_obj, axis + 'axis').set_major_formatter(FuncFormatter(lambda v, pos, d=digits: format(v, f'.{d}g')))
                if any(s.label for s in specs) or recipe.exclusions:
                    handles, labels = axis_obj.get_legend_handles_labels()
                    unique = dict(zip(labels, handles))
                    axis_obj.legend(unique.values(), unique.keys(), loc=recipe.legend_loc)
            for a in recipe.annotations: ax.text(a.x, a.y, a.text)
            apply_preset(ax, recipe)
            operations.append({'operation': 'preset', 'name': recipe.style_preset, 'version': VERSION})
            fig.canvas.draw()
            for group in groups:
                group['plotted'].update(x_lim=tuple(group['axes'].get_xlim()), y_lim=tuple(group['axes'].get_ylim()))
                artists.extend(a for c in group['containers'] for a in (c.lines[0], *c.lines[1], *c.lines[2]))
        except Exception:
            plt.close(fig)
            raise
    operations.extend({'operation': 'exclusion', **e.model_dump()} for e in recipe.exclusions)
    # Preserve the original single-series API while exposing every series/panel.
    plotted = {**plotted_series[0], 'series': plotted_series}
    return RenderResult(fig, plotted, operations, artists, groups)
