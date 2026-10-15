from dataclasses import dataclass
import matplotlib.pyplot as plt
from .recipe import Recipe, validate
from .render import render
from .checks import run_checks


class RejectedEdit(ValueError):
    def __init__(self, reasons):
        self.reasons = reasons
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
        self.source_units = {getattr(initial, axis): getattr(initial, axis + '_unit') for axis in ('x', 'y')}
        for transform in initial.transforms:
            self.source_units[transform.column] = transform.from_unit
        self.current = None
        self.history = []
        self.apply(recipe)

    def apply(self, new_recipe):
        candidate = None
        try:
            recipe = validate(Recipe.model_validate(new_recipe.model_dump() if isinstance(new_recipe, Recipe) else new_recipe), self.manifest)
            for axis in ('x', 'y'):
                column = getattr(recipe, axis)
                source_unit = self.source_units.get(column)
                transform = next((t for t in recipe.transforms if t.column == column), None)
                claimed_source = transform.from_unit if transform else getattr(recipe, axis + '_unit')
                if source_unit and claimed_source != source_unit:
                    raise ValueError(f'Source unit for {column} is {source_unit}; relabeling cannot replace conversion')
            candidate = render(self.df, self.manifest, recipe)
            checks = run_checks(self.df, self.manifest, recipe, candidate)
            failures = [f'{c.name}: {c.detail}' for c in checks if c.status == 'FAIL']
            if failures: raise RejectedEdit(failures)
        except (ValueError, TypeError, KeyError) as exc:
            if candidate is not None: plt.close(candidate.fig)
            if isinstance(exc, RejectedEdit): raise
            raise RejectedEdit([str(exc)]) from exc
        if self.current is not None: self.history.append(self.current)
        self.current = State(recipe, candidate, checks)
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
