"""Explicit local style rules, not a claim of official LHCb approval."""
import numpy as np

VERSION = '1'
RULES = {
    'default': [],
    'lhcb': [
        {'rule': 'font', 'value': {'font.family': 'serif', 'font.size': 12, 'axes.labelsize': 14, 'xtick.labelsize': 12, 'ytick.labelsize': 12, 'legend.fontsize': 12}, 'source': 'unverified: local LHCb-inspired typography'},
        {'rule': 'experiment_label', 'value': 'LHCb at top-left', 'source': 'unverified: local LHCb-inspired label placement'},
        {'rule': 'title', 'value': 'none', 'source': 'unverified: local LHCb-inspired title convention'},
        {'rule': 'units', 'value': 'square brackets', 'source': 'unverified: local physics axis convention'},
        {'rule': 'prebinned_y_label', 'value': 'Candidates / (bin width unit)', 'source': 'unverified: local prebinned histogram convention'},
    ],
}


def preset_rc(name):
    return RULES['lhcb'][0]['value'].copy() if name == 'lhcb' else {}


def apply_preset(ax, recipe):
    if recipe.style_preset != 'lhcb': return
    ax.set_title('')
    ax.text(.04, .96, 'LHCb', transform=ax.transAxes, ha='left', va='top', fontsize=16)
    if recipe.plot_type == 'hist_prebinned':
        centers = np.asarray(ax.lines[0].get_xdata())
        widths = np.diff(centers)
        if len(widths) == 0 or np.any(widths <= 0) or not np.allclose(widths, widths[0], rtol=1e-12, atol=1e-12):
            raise ValueError('LHCb prebinned label needs increasing, equally spaced bin centers')
        unit = f' [{recipe.x_unit}]' if recipe.x_unit else ''
        ylabel = f'Candidates / ({widths[0]:g}{unit})'
        if recipe.y_unit: ylabel += f' [{recipe.y_unit}]'
        ax.set_ylabel(ylabel)
