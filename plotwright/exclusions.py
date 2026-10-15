"""Visible row exclusions; values remain in the data and audit arrays."""
import numpy as np
from matplotlib.colors import to_rgba


def draw_data(ax, plotted, recipe, label=None):
    excluded = np.isin(plotted['indices'], [e.row_index for e in recipe.exclusions])
    plotted['excluded'] = excluded
    fmt = 'o' if recipe.plot_type in ('points', 'points_errorbars') else '-'
    kwargs = {'drawstyle': 'steps-mid'} if recipe.plot_type in ('step', 'hist_prebinned') else {}
    # NaN display gaps prevent connecting a line across an excluded row.
    # These are artist masks only; recorded source-derived arrays remain intact.
    y = np.where(excluded, np.nan, plotted['y'])
    normal = ax.errorbar(plotted['x'], y, xerr=plotted['xerr'], yerr=plotted['yerr'], fmt=fmt, label=label, **kwargs)
    containers = [normal]
    if excluded.any():
        containers.append(ax.errorbar(plotted['x'][excluded], plotted['y'][excluded],
            xerr=plotted['xerr'][excluded] if plotted['xerr'] is not None else None,
            yerr=plotted['yerr'][excluded] if plotted['yerr'] is not None else None,
            fmt='o', linestyle='None', color='grey', markerfacecolor='none',
            markeredgecolor='grey', label=f'excluded ({excluded.sum()})', zorder=4))
    return containers


def equal(a, b, *, masked=False):
    return a is None and b is None or (a is not None and b is not None and np.shape(a) == np.shape(b) and np.allclose(a, b, rtol=1e-12, atol=0, equal_nan=masked))


def check_artists(ax, containers, expected, excluded):
    """Independently compare both normal and excluded data/errorbar artists."""
    expected_count = 2 if excluded.any() else 1
    locked = len(containers) == expected_count
    errors_ok = locked
    for i, container in enumerate(containers):
        if i >= expected_count: return False, False
        x = expected['x'][excluded] if i else expected['x']
        y = expected['y'][excluded] if i else np.where(excluded, np.nan, expected['y'])
        line = container.lines[0]
        locked &= line in ax.lines and equal(line.get_xdata(), x) and equal(line.get_ydata(), y, masked=True)
        expected_segments = []
        for axis in ('x', 'y'):
            err = expected[axis + 'err']
            if err is None: continue
            if i: err = err[excluded]
            expected_segments.append([np.array([[a-b, c], [a+b, c]] if axis == 'x' else [[a, c-b], [a, c+b]]) if np.isfinite(c) else np.empty((0,)) for a, c, b in zip(x, y, err)])
        collections = container.lines[2]
        errors_ok &= len(collections) == len(expected_segments)
        for artist, expected_segs in zip(collections, expected_segments):
            actual = artist.get_segments()
            errors_ok &= artist in ax.collections and len(actual) == len(expected_segs) and all(equal(a, b) for a, b in zip(actual, expected_segs))
    return bool(locked), bool(errors_ok)


def exclusion_issues(recipe, plotted, ax, containers):
    issues = []
    for e in recipe.exclusions:
        if not e.reason.strip() or not e.approved_by.strip(): issues.append(f'row {e.row_index}: reason and approved_by are required')
        if e.row_index not in plotted['indices']:
            issues.append(f'row {e.row_index}: excluded point cannot be drawn because it is invalid')
        else:
            i = list(plotted['indices']).index(e.row_index)
            if not (ax.get_xlim()[0] <= plotted['x'][i] <= ax.get_xlim()[1] and ax.get_ylim()[0] <= plotted['y'][i] <= ax.get_ylim()[1]):
                issues.append(f'row {e.row_index}: excluded point is outside axis limits')
    if recipe.exclusions and len(containers) > 1:
        line = containers[1].lines[0]
        if not line.get_visible() or line.get_markerfacecolor() != 'none' or to_rgba(line.get_markeredgecolor()) != to_rgba('grey'):
            issues.append('Excluded markers must be visible, hollow and grey')
        legend = ax.get_legend()
        label = f'excluded ({int(plotted["excluded"].sum())})'
        if legend is None or label not in [t.get_text() for t in legend.get_texts()]: issues.append('Missing exclusion legend')
    elif recipe.exclusions:
        issues.append('Missing excluded-point artist')
    return issues
