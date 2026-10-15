from dataclasses import dataclass, field
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from .recipe import validate, label_with_unit
from .units import conversion
from .exclusions import draw_data


@dataclass
class RenderResult:
    fig: object
    plotted: dict
    operations: list[dict] = field(default_factory=list)
    artists: list = field(default_factory=list)


def render(df, manifest, recipe):
    recipe = validate(recipe, manifest)
    columns = [c for c in (recipe.x, recipe.y, recipe.x_err, recipe.y_err) if c]
    numeric = df[columns].apply(pd.to_numeric, errors='coerce')
    valid = np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1)
    plotted = {'indices': np.flatnonzero(valid), 'invalid_indices': np.flatnonzero(~valid)}
    operations = [{'operation': 'load', 'sha256': manifest.sha256, 'columns': columns}]
    for key, col in [('x', recipe.x), ('y', recipe.y), ('xerr', recipe.x_err), ('yerr', recipe.y_err)]:
        plotted[key] = numeric.loc[valid, col].to_numpy(dtype=float).copy() if col else None
    for t in recipe.transforms:
        axis = 'x' if t.column == recipe.x else 'y'
        scale, offset = conversion(t.from_unit, t.to_unit)
        plotted[axis] = plotted[axis] * scale + offset
        operations.append({'operation': 'transform', 'column': t.column, 'from_unit': t.from_unit, 'to_unit': t.to_unit, 'factor': scale, 'offset': offset})
        if plotted[axis + 'err'] is not None:
            plotted[axis + 'err'] *= abs(scale)
            operations.append({'operation': 'uncertainty_transform', 'column': getattr(recipe, axis + '_err'), 'factor': abs(scale), 'paired_column': t.column})
    for axis in ('x', 'y'):
        if getattr(recipe, axis + '_scale') == 'log' and np.any(plotted[axis] <= 0):
            raise ValueError(f'Log scale requires positive transformed {axis}')
        if plotted[axis + 'err'] is not None and np.any(plotted[axis + 'err'] < 0):
            raise ValueError('Uncertainties must be nonnegative')
    with matplotlib.rc_context(matplotlib.rcParamsDefault):
        from .presets import apply_preset, preset_rc, VERSION
        matplotlib.rcParams.update(preset_rc(recipe.style_preset))
        fig, ax = plt.subplots(figsize=(recipe.fig_width_cm / 2.54, recipe.fig_height_cm / 2.54), dpi=100, layout='constrained')
        containers = draw_data(ax, plotted, recipe, recipe.legend_label)
        artists = [a for c in containers for a in (c.lines[0], *c.lines[1], *c.lines[2])]
        ax.set(xlabel=label_with_unit(recipe.x_label, recipe.x_unit), ylabel=label_with_unit(recipe.y_label, recipe.y_unit), title=recipe.title or '', xscale=recipe.x_scale, yscale=recipe.y_scale)
        if recipe.x_lim: ax.set_xlim(*recipe.x_lim)
        if recipe.y_lim: ax.set_ylim(*recipe.y_lim)
        for axis in ('x', 'y'):
            digits = getattr(recipe, 'sig_figs_' + axis)
            getattr(ax, axis + 'axis').set_major_formatter(FuncFormatter(lambda v, pos, d=digits: format(v, f'.{d}g')))
        if recipe.legend_label or recipe.exclusions: ax.legend(loc=recipe.legend_loc)
        for a in recipe.annotations: ax.text(a.x, a.y, a.text)
        apply_preset(ax, recipe)
        operations.append({'operation': 'preset', 'name': recipe.style_preset, 'version': VERSION})
        fig.canvas.draw()
        plotted.update(x_lim=tuple(ax.get_xlim()), y_lim=tuple(ax.get_ylim()))
    operations.extend({'operation': 'exclusion', **e.model_dump()} for e in recipe.exclusions)
    return RenderResult(fig, plotted, operations, artists)
