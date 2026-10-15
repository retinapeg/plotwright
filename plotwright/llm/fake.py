"""Small deterministic keyword adapter for offline demonstration and regression evals."""
import re
from .adapter import Proposal


class FakeAdapter:
    def propose(self, prompt, current_recipe, manifest, preset):
        p = prompt.lower().strip()
        if re.search(r'\b(drop|remove|smooth|fit|hide|shift|exclude|filter|reorder|sort|replace|fabricate|alter)\b', p) or 'error bars smaller' in p or '10 points' in p or 'ignore previous' in p:
            return Proposal(kind='refuse', message='I cannot change or exclude data. Use the explicit exclusion workflow: create a separately reviewed source file and load it as a new dataset; this app does not perform exclusions.')
        patch = {}
        if 'displacement in cm' in p:
            if current_recipe.y != 'displacement_m':
                return Proposal(kind='question', message='Which displacement column and source unit should be used?')
            transforms = [t.model_dump() for t in current_recipe.transforms if t.column != current_recipe.y]
            transforms.append({'column': current_recipe.y, 'from_unit': 'm', 'to_unit': 'cm'})
            patch.update(y_unit='cm', y_label='Displacement [cm]', transforms=transforms)
        if 'legend' in p:
            patch['legend_loc'] = 'lower right' if 'bottom right' in p or 'move' in p else 'upper left'
        if 'centre the title' in p or 'center the title' in p:
            patch['title'] = current_recipe.title  # matplotlib titles are centered by construction.
        if 'bigger font' in p:
            return Proposal(kind='question', message='Font sizes are fixed by the preset. Would you like the lhcb preset with larger serif labels?')
        if 'y-min 0' in p:
            patch['y_lim'] = [0, current_recipe.y_lim[1] if current_recipe.y_lim else None]
        if 'log y' in p: patch['y_scale'] = 'log'
        if 'linear y' in p: patch['y_scale'] = 'linear'
        if '4 sig figs' in p: patch['sig_figs_x'] = 4
        if '[mev/c^2]' in p:
            if current_recipe.x != 'mass_MeV':
                return Proposal(kind='question', message='Which mass column has units MeV/c^2?')
            patch.update(x_unit='MeV/c^2', x_label='Mass [MeV/c^2]')
        if 'y from 0 to 1' in p: patch['y_lim'] = [0, 1]
        if 'line plot' in p: patch['plot_type'] = 'line'
        if 'points with error bars' in p: patch['plot_type'] = 'points_errorbars'
        if 'wider figure' in p: patch['fig_width_cm'] = 20
        if 'lhcb style' in p: patch['style_preset'] = 'lhcb'
        if 'default style' in p: patch['style_preset'] = 'default'
        if patch:
            return Proposal(kind='edit', recipe_patch=patch, message='Proposed settings; all checks and any hidden-points warnings must be shown.')
        return Proposal(kind='question', message='Please specify columns, units, or the setting you want to change.')
