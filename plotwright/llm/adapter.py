from typing import Literal, Protocol
from pydantic import model_validator
from ..recipe import Strict, Recipe
from ..data import Manifest


class Proposal(Strict):
    kind: Literal['edit', 'question', 'refuse']
    recipe_patch: dict | None = None
    message: str

    @model_validator(mode='after')
    def patch_is_settings(self):
        if self.kind == 'edit' and self.recipe_patch is None:
            raise ValueError('An edit requires a settings patch')
        if self.kind != 'edit' and self.recipe_patch is not None:
            raise ValueError('Only edits can contain a settings patch')
        if self.recipe_patch and set(self.recipe_patch) - Recipe.model_fields.keys():
            raise ValueError('Patch contains forbidden fields')
        return self


class Adapter(Protocol):
    def propose(self, prompt: str, current_recipe: Recipe, manifest: Manifest, preset: dict) -> Proposal: ...
