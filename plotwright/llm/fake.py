"""Small deterministic keyword adapter for offline demonstration and regression evals."""
import re
from .adapter import Proposal
from ..recipe import series_specs


class FakeAdapter:
    def propose(self, prompt, current_recipe, manifest, preset):
        p = prompt.lower().strip()
        if re.search(r'\b(smooth|fit|shift|filter|reorder|sort|replace|fabricate|alter|invent|silently)\b', p) or 'error bars smaller' in p or 'scale errors' in p or 'ignore previous' in p:
            return Proposal(kind='refuse', message='I cannot alter or hide data. The explicit exclusion workflow keeps approved rows visible with hollow grey markers.')
        if 'remove residual panel' in p:
            return Proposal(kind='edit', recipe_patch={'residuals': None}, message='Remove the residual panel; source measurements remain plotted.')
        if re.search(r'\b(drop|remove|hide|exclude)\b', p) or '10 points' in p:
            rows_match = re.search(r'\bexclude rows?\s+(\d+(?:\s*,\s*\d+)*)\s*;', prompt, re.I)
            reason_match = re.search(r'(?:^|;)\s*reason:\s*([^;]*)', prompt, re.I)
            approver_match = re.search(r'(?:^|;)\s*(?:approved_by|approver):\s*([^;]*)', prompt, re.I)
            if rows_match and reason_match and approver_match and reason_match[1].strip() and approver_match[1].strip():
                rows = [int(row.strip()) for row in rows_match[1].split(',')]
                if len(set(rows)) == len(rows) and all(0 <= row < manifest.n_rows for row in rows):
                    exclusions = [e.model_dump() for e in current_recipe.exclusions if e.row_index not in rows]
                    exclusions.extend({'row_index': row, 'reason': reason_match[1].strip(), 'approved_by': approver_match[1].strip()} for row in rows)
                    return Proposal(kind='edit', recipe_patch={'exclusions': exclusions}, message='Approved exclusions stay visible as hollow grey points, with a legend and audit records. No values are dropped.')
            return Proposal(kind='question', message='Which zero-based row_index, reason, and approved_by (approver) should be recorded? Excluded points remain visible; I cannot choose the outlier or invent approval.')
        patch = {}
        if 'residual' in p:
            match = re.search(r'residuals against ([A-Za-z_][A-Za-z_0-9]*)', prompt, re.I)
            if not match or match[1] not in manifest.columns:
                return Proposal(kind='question', message='Which existing reference column should residuals subtract? No model is fitted or generated.')
            patch['residuals'] = {'against': match[1]}
        if 'both histogram series' in p or 'both histogram samples' in p:
            required = {'entries', 'entries_err', 'control_entries', 'control_err'}
            if not required <= manifest.columns.keys():
                return Proposal(kind='question', message='Which two value and uncertainty columns should form the series?')
            patch.update(y=None, y_err=None, series=[{'y': 'entries', 'y_err': 'entries_err', 'label': 'Signal sample'}, {'y': 'control_entries', 'y_err': 'control_err', 'label': 'Control sample'}])
        elif 'series displacement_m and model_m' in p:
            if not {'displacement_m', 'model_m', 'displacement_unc_m'} <= manifest.columns.keys():
                return Proposal(kind='question', message='Which existing columns should form the series?')
            patch.update(y=None, y_err=None, series=[{'y': 'displacement_m', 'y_err': 'displacement_unc_m', 'label': 'Measurements'}, {'y': 'model_m', 'y_err': None, 'label': 'Reference'}])
        elif 'label the two series signal and control' in p and len(current_recipe.series) == 2:
            patch['series'] = [{**s.model_dump(), 'label': label} for s, label in zip(current_recipe.series, ['Signal', 'Control'])]
        elif 'second series' in p or 'two series' in p:
            return Proposal(kind='question', message='Which value, uncertainty and label columns should form the series?')
        if 'displacement in cm' in p:
            if 'displacement_m' not in [s.y for s in series_specs(current_recipe)]:
                return Proposal(kind='question', message='Which displacement column and source unit should be used?')
            columns = [s.y for s in series_specs(current_recipe)]
            reference = patch.get('residuals') or (current_recipe.residuals.model_dump() if current_recipe.residuals else None)
            if reference: columns.append(reference['against'])
            columns = list(dict.fromkeys(columns))
            transforms = [t.model_dump() for t in current_recipe.transforms if t.column not in columns]
            transforms.extend({'column': col, 'from_unit': 'm', 'to_unit': 'cm'} for col in columns)
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
