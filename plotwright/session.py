from dataclasses import dataclass
import matplotlib.pyplot as plt
from .recipe import Recipe, validate, series_specs
from .render import render
from .checks import run_checks


class RejectedEdit(ValueError):
    def __init__(self, reasons, checks=None):
        self.reasons = reasons
        self.checks = checks
        super().__init__('; '.join(reasons))


@dataclass(frozen=True)
class State:
    recipe: Recipe
    result: object
    checks: list


class Session:
    def __init__(self, df, manifest, recipe):
        self.df = df.copy(deep=True)
        self.manifest = manifest.model_copy(deep=True)
        initial = Recipe.model_validate(recipe.model_dump() if isinstance(recipe, Recipe) else recipe)
        self.source_units = {initial.x: initial.x_unit, **{s.y: initial.y_unit for s in series_specs(initial)}}
        if initial.residuals: self.source_units[initial.residuals.against] = initial.y_unit
        for transform in initial.transforms:
            self.source_units[transform.column] = transform.from_unit
        self.current = None
        self.history = []
        self.apply(recipe)

    def preview(self, new_recipe):
        """Validate, render and check without changing current or history."""
        candidate = None
        try:
            recipe = validate(Recipe.model_validate(new_recipe.model_dump() if isinstance(new_recipe, Recipe) else new_recipe), self.manifest)
            value_axes = [(recipe.x, 'x'), *[(s.y, 'y') for s in series_specs(recipe)]]
            if recipe.residuals: value_axes.append((recipe.residuals.against, 'y'))
            for column, axis in value_axes:
                source_unit = self.source_units.get(column)
                transform = next((t for t in recipe.transforms if t.column == column), None)
                claimed_source = transform.from_unit if transform else getattr(recipe, axis + '_unit')
                if source_unit and claimed_source != source_unit:
                    raise ValueError(f'Source unit for {column} is {source_unit}; relabeling cannot replace conversion')
            candidate = render(self.df, self.manifest, recipe)
            checks = run_checks(self.df, self.manifest, recipe, candidate)
        except (ValueError, TypeError, KeyError) as exc:
            if candidate is not None: plt.close(candidate.fig)
            if isinstance(exc, RejectedEdit): raise
            raise RejectedEdit([str(exc)]) from exc
        return State(recipe, candidate, checks)

    def apply(self, new_recipe):
        state = self.preview(new_recipe)
        failures = [f'{c.name}: {c.detail}' for c in state.checks if c.status == 'FAIL']
        if failures:
            plt.close(state.result.fig)
            raise RejectedEdit(failures, state.checks)
        if self.current is not None: self.history.append(self.current)
        self.current = state
        units = [(state.recipe.x, state.recipe.x_unit), *[(s.y, state.recipe.y_unit) for s in series_specs(state.recipe)]]
        if state.recipe.residuals: units.append((state.recipe.residuals.against, state.recipe.y_unit))
        for column, unit in units:
            transform = next((t for t in state.recipe.transforms if t.column == column), None)
            if not self.source_units.get(column):
                self.source_units[column] = transform.from_unit if transform else unit
        return self.current

    def undo(self):
        if self.history:
            plt.close(self.current.result.fig)
            self.current = self.history.pop()
        return self.current

    def propose(self, proposal):
        if proposal.kind != 'edit': return proposal.message
        recipe = self.current.recipe.model_dump()
        recipe.update(proposal.recipe_patch or {})
        return self.apply(recipe)
