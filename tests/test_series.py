from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import matplotlib.pyplot as plt
from plotwright.data import load_table
from plotwright.recipe import Recipe
from plotwright.render import render
from plotwright.checks import run_checks
from plotwright.export import export, regenerate, verify_bundle
from plotwright.session import Session, RejectedEdit


@pytest.fixture
def multiple(tmp_path):
    path = tmp_path / 'series.csv'
    pd.DataFrame({'x': [1., 2., 3., 4.], 'a': [2., 4., 6., 8.], 'ae': [.1]*4, 'b': [3., None, 7., 9.], 'be': [.2]*4, 'model': [1.5, 3.5, None, 7.5]}).to_csv(path, index=False)
    df, manifest = load_table(path)
    recipe = Recipe(x='x', series=[{'y': 'a', 'y_err': 'ae', 'label': 'A'}, {'y': 'b', 'y_err': 'be', 'label': 'B'}], residuals={'against': 'model'}, x_unit='s', y_unit='m')
    yield df, manifest, recipe
    plt.close('all')


def test_series_and_residuals_keep_independent_rows(multiple):
    df, manifest, recipe = multiple
    result = render(df, manifest, recipe)
    assert len(result.fig.axes) == 2
    a, b = result.plotted['series']
    np.testing.assert_array_equal(a['indices'], [0, 1, 2, 3])
    np.testing.assert_array_equal(b['indices'], [0, 2, 3])
    np.testing.assert_array_equal(a['residual']['indices'], [0, 1, 3])
    np.testing.assert_array_equal(b['residual']['indices'], [0, 3])
    np.testing.assert_allclose(a['residual']['y'], [.5, .5, .5])
    np.testing.assert_allclose(b['residual']['y'], [1.5, 1.5])
    np.testing.assert_allclose(b['residual']['yerr'], [.2, .2])
    checks = run_checks(df, manifest, recipe, result)
    assert all(c.status == 'PASS' for c in checks), checks
    rows = [c for c in checks if c.name.startswith('rows_accounted')]
    assert len(rows) == 4
    assert '[1, 2]' in next(c.detail for c in rows if 'b:residual' in c.name)


def test_series_scaling_and_residual_subtraction(multiple):
    df, manifest, recipe = multiple
    session = Session(df, manifest, recipe)
    transforms = [{'column': col, 'from_unit': 'm', 'to_unit': 'cm'} for col in ('a', 'b', 'model')]
    state = session.apply({**recipe.model_dump(), 'y_unit': 'cm', 'transforms': transforms})
    a, b = state.result.plotted['series']
    np.testing.assert_array_equal(a['y'], df.a * 100)
    np.testing.assert_array_equal(a['yerr'], df.ae * 100)
    np.testing.assert_allclose(b['residual']['y'], [150, 150])
    np.testing.assert_allclose(b['residual']['yerr'], [20, 20])
    with pytest.raises(RejectedEdit, match='every series'): session.apply({**recipe.model_dump(), 'y_unit': 'cm', 'transforms': transforms[:1]})


def test_series_and_residual_artist_tampering(multiple):
    df, manifest, recipe = multiple
    result = render(df, manifest, recipe)
    result.fig.axes[1].containers[1].lines[0].set_ydata([0., 0.])
    checks = run_checks(df, manifest, recipe, result)
    assert next(c for c in checks if c.name == 'data_lock[b:residual]').status == 'FAIL'
    assert next(c for c in checks if c.name == 'data_lock[a]').status == 'PASS'
    result.plotted['series'][1]['indices'] = np.array([3, 2, 0])
    assert next(c for c in run_checks(df, manifest, recipe, result) if c.name == 'rows_accounted[b]').status == 'FAIL'


def test_multiseries_export_and_regen(multiple, tmp_path):
    df, manifest, recipe = multiple
    recipe = Recipe.model_validate({**recipe.model_dump(), 'exclusions': [{'row_index': 3, 'reason': 'sensor check', 'approved_by': 'Leo'}]})
    state = Session(df, manifest, recipe).current
    out = export(state.result, recipe, manifest, state.checks, tmp_path / 'out')
    regenerate(out, tmp_path / 'regen')
    assert (out / 'plotted.csv').read_bytes() == (tmp_path / 'regen/plotted.csv').read_bytes()
    csv = pd.read_csv(out / 'plotted.csv')
    assert set(csv.series) == {'a', 'b'} and set(csv.panel) == {'main', 'residual'}
    assert csv.excluded.sum() == 4
    assert all(c.status == 'PASS' for c in verify_bundle(out))


def test_new_examples_render():
    root = Path(__file__).parents[1] / 'examples'
    for name in ('freefall_residuals', 'lhcb_two_series'):
        df, manifest = load_table(root / f'{name}.csv')
        recipe = Recipe.model_validate_json((root / f'{name}_recipe.json').read_text())
        state = Session(df, manifest, recipe).current
        assert all(c.status == 'PASS' for c in state.checks), state.checks
        if name == 'lhcb_two_series':
            assert len(state.result.plotted['series']) == 2
            assert 'Candidates / (10 [MeV/c^2])' in state.result.fig.axes[0].get_ylabel()
        plt.close(state.result.fig)
