import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .units import conversion


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Transform(Strict):
    column: str
    from_unit: str
    to_unit: str


class Annotation(Strict):
    text: str
    x: float
    y: float


class Recipe(Strict):
    x: str
    y: str
    y_err: str | None = None
    x_err: str | None = None
    plot_type: Literal['points', 'points_errorbars', 'line', 'step', 'hist_prebinned'] = 'points'
    title: str | None = None
    x_label: str = ''
    y_label: str = ''
    x_unit: str = ''
    y_unit: str = ''
    x_lim: tuple[float | None, float | None] | None = None
    y_lim: tuple[float | None, float | None] | None = None
    x_scale: Literal['linear', 'log'] = 'linear'
    y_scale: Literal['linear', 'log'] = 'linear'
    legend_loc: Literal['best', 'upper right', 'upper left', 'lower left', 'lower right', 'center', 'center left', 'center right', 'lower center', 'upper center'] = 'best'
    legend_label: str | None = None
    sig_figs_x: int = Field(default=3, ge=1, le=12)
    sig_figs_y: int = Field(default=3, ge=1, le=12)
    fig_width_cm: float = Field(default=16, ge=4, le=60)
    fig_height_cm: float = Field(default=12, ge=4, le=60)
    style_preset: Literal['default', 'lhcb'] = 'default'
    transforms: list[Transform] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)

    @model_validator(mode='after')
    def sensible_limits(self):
        for axis in ('x', 'y'):
            lim = getattr(self, axis + '_lim')
            if lim and lim[0] is not None and lim[1] is not None and lim[0] >= lim[1]:
                raise ValueError('Axis limits must increase')
            if lim and getattr(self, axis + '_scale') == 'log' and any(v is not None and v <= 0 for v in lim):
                raise ValueError('Log limits must be positive')
        return self


def validate(recipe, manifest):
    recipe = Recipe.model_validate(recipe.model_dump() if isinstance(recipe, Recipe) else recipe)
    columns = [recipe.x, recipe.y, recipe.x_err, recipe.y_err]
    for col in columns + [t.column for t in recipe.transforms]:
        if col is not None and col not in manifest.columns:
            raise ValueError(f'Unknown column: {col}')
    if len(set(c for c in columns if c)) != len([c for c in columns if c]):
        raise ValueError('Value and uncertainty columns must be distinct')
    seen = set()
    for t in recipe.transforms:
        conversion(t.from_unit, t.to_unit)
        if t.column not in (recipe.x, recipe.y) or t.column in seen:
            raise ValueError('One transform per value column; uncertainties scale automatically')
        seen.add(t.column)
        axis = 'x' if t.column == recipe.x else 'y'
        if getattr(recipe, axis + '_unit') != t.to_unit:
            raise ValueError('Declared axis unit must match transform target')
    for axis in ('x', 'y'):
        col = getattr(recipe, axis)
        if getattr(recipe, axis + '_scale') == 'log' and col in manifest.nonpositive_columns:
            raise ValueError(f'Log scale requires positive data: {col}')
    return recipe


def label_with_unit(label, unit):
    return re.sub(r'\s*\[[^]]*\]', '', label).strip() + (f' [{unit}]' if unit else '')
