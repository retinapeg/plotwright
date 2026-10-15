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


class Exclusion(Strict):
    row_index: int = Field(ge=0, strict=True)
    reason: str = ''
    approved_by: str = ''


class Series(Strict):
    y: str
    y_err: str | None = None
    label: str | None = None


class Residuals(Strict):
    against: str


class Recipe(Strict):
    x: str
    y: str | None = None
    y_err: str | None = None
    series: list[Series] = Field(default_factory=list)
    residuals: Residuals | None = None
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
    exclusions: list[Exclusion] = Field(default_factory=list)

    @model_validator(mode='after')
    def sensible_limits(self):
        if not self.series and not self.y:
            raise ValueError('Specify y or a nonempty series list')
        if self.series and (self.y is not None or self.y_err is not None):
            raise ValueError('Use either y/y_err or series, not both')
        for axis in ('x', 'y'):
            lim = getattr(self, axis + '_lim')
            if lim and lim[0] is not None and lim[1] is not None and lim[0] >= lim[1]:
                raise ValueError('Axis limits must increase')
            if lim and getattr(self, axis + '_scale') == 'log' and any(v is not None and v <= 0 for v in lim):
                raise ValueError('Log limits must be positive')
        return self


def validate(recipe, manifest):
    recipe = Recipe.model_validate(recipe.model_dump() if isinstance(recipe, Recipe) else recipe)
    rows = [e.row_index for e in recipe.exclusions]
    if len(set(rows)) != len(rows) or any(row >= manifest.n_rows for row in rows):
        raise ValueError('Exclusion rows must be unique and within the source table')
    specs = series_specs(recipe)
    values = [s.y for s in specs]
    if len(set(values)) != len(values):
        raise ValueError('Series value columns must be unique')
    if recipe.residuals:
        values = list(dict.fromkeys([*values, recipe.residuals.against]))
    errors = [c for c in [recipe.x_err, *[s.y_err for s in specs]] if c]
    if recipe.x in values or set([recipe.x, *values]) & set(errors):
        raise ValueError('Value and uncertainty columns must be distinct')
    for col in referenced_columns(recipe) + [t.column for t in recipe.transforms]:
        if col not in manifest.columns:
            raise ValueError(f'Unknown column: {col}')
    seen = set()
    for t in recipe.transforms:
        conversion(t.from_unit, t.to_unit)
        if t.column not in [recipe.x, *values] or t.column in seen:
            raise ValueError('One transform per value column; uncertainties scale automatically')
        seen.add(t.column)
        axis = 'x' if t.column == recipe.x else 'y'
        if getattr(recipe, axis + '_unit') != t.to_unit:
            raise ValueError('Declared axis unit must match transform target')
    if seen.intersection(values) and not set(values) <= seen:
        raise ValueError('Declare conversions for every series and residual reference on the shared y axis')
    for axis, cols in [('x', [recipe.x]), ('y', [s.y for s in specs])]:
        for col in cols:
            if getattr(recipe, axis + '_scale') == 'log' and col in manifest.nonpositive_columns:
                raise ValueError(f'Log scale requires positive data: {col}')
    return recipe


def series_specs(recipe):
    return recipe.series or [Series(y=recipe.y, y_err=recipe.y_err, label=recipe.legend_label)]


def referenced_columns(recipe):
    cols = [recipe.x, recipe.x_err]
    for s in series_specs(recipe): cols.extend([s.y, s.y_err])
    if recipe.residuals: cols.append(recipe.residuals.against)
    return list(dict.fromkeys(c for c in cols if c))


def label_with_unit(label, unit):
    return re.sub(r'\s*\[[^]]*\]', '', label).strip() + (f' [{unit}]' if unit else '')
