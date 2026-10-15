import numpy as np
import pandas as pd
import pytest
from plotwright.data import load_table
from plotwright.recipe import Recipe, validate
from plotwright.render import render
from plotwright.checks import run_checks
from plotwright.units import factor


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'data.csv'
    pd.DataFrame({'t': [1., 2., 3., 4.], 'd': [1., 2., 3., 4.], 'err': [.1] * 4}).to_csv(path, index=False)
    df, manifest = load_table(path)
    return df, manifest, Recipe(x='t', y='d', y_err='err', x_label='Time', y_label='Displacement', x_unit='s', y_unit='m')


def test_conversion(source):
    df, manifest, recipe = source
    recipe = Recipe.model_validate({**recipe.model_dump(), 'y_unit': 'cm', 'transforms': [{'column': 'd', 'from_unit': 'm', 'to_unit': 'cm'}]})
    result = render(df, manifest, recipe)
    np.testing.assert_array_equal(result.plotted['y'], df.d * 100)
    np.testing.assert_array_equal(result.plotted['yerr'], df.err * 100)
    assert '[cm]' in result.fig.axes[0].get_ylabel()
    assert all(c.status == 'PASS' for c in run_checks(df, manifest, recipe, result))


def test_reject_columns_and_fields(source):
    _, manifest, recipe = source
    with pytest.raises(ValueError): validate(recipe.model_copy(update={'x': 'unknown'}), manifest)
    with pytest.raises(ValueError): Recipe(x='t', y='d', exclude_rows=[1])
    with pytest.raises(ValueError): factor('m', 'banana')
    with pytest.raises(ValueError): factor('m', 's')


def test_hidden_points(source):
    df, manifest, recipe = source
    recipe = recipe.model_copy(update={'y_lim': (0, 2.5)})
    result = render(df, manifest, recipe)
    check = next(c for c in run_checks(df, manifest, recipe, result) if c.name == 'hidden_points')
    assert check.status == 'WARN' and '[2, 3]' in check.detail


def test_tampered_artist(source):
    df, manifest, recipe = source
    result = render(df, manifest, recipe)
    result.fig.axes[0].lines[0].set_ydata([1, 2, 3, 99])
    assert next(c for c in run_checks(df, manifest, recipe, result) if c.name == 'data_lock').status == 'FAIL'


def test_invalid_and_log(tmp_path):
    path = tmp_path / 'faulty.csv'
    path.write_text('x,y\n1,2\n2,\n3,text\n,4\n')
    df, manifest = load_table(path)
    assert len(manifest.invalid_cells) == 3
    recipe = Recipe(x='x', y='y')
    result = render(df, manifest, recipe)
    row_check = next(c for c in run_checks(df, manifest, recipe, result) if c.name == 'rows_accounted')
    assert row_check.status == 'PASS' and '[1, 2, 3]' in row_check.detail
    df.loc[0, 'y'] = '0'
    df.to_csv(path, index=False)
    df, manifest = load_table(path)
    with pytest.raises(ValueError): render(df, manifest, Recipe(x='x', y='y', y_scale='log'))


def test_session_rejection_and_undo(source):
    from plotwright.session import Session, RejectedEdit
    df, manifest, recipe = source
    session = Session(df, manifest, recipe)
    original = session.current
    with pytest.raises(RejectedEdit): session.apply({**recipe.model_dump(), 'exclude_rows': [0]})
    assert session.current is original and not session.history
    session.apply({**recipe.model_dump(), 'title': 'New title'})
    assert session.current.result.fig.axes[0].get_title() == 'New title'
    assert session.undo() is original
