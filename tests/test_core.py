import numpy as np
import pandas as pd
import pytest
from plotwright.data import load_table
from plotwright.recipe import Recipe, validate
from plotwright.render import render
from plotwright.checks import run_checks
from plotwright.units import factor


@pytest.fixture(autouse=True)
def close_figures():
    yield
    import matplotlib.pyplot as plt
    plt.close("all")


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


def test_export_regen_and_tampering(source, tmp_path):
    from plotwright.export import export, regenerate, verify_bundle
    from plotwright.session import Session, RejectedEdit
    from plotwright.checks import Check
    df, manifest, recipe = source
    session = Session(df, manifest, recipe)
    state = session.current
    out = tmp_path / 'out'
    export(state.result, recipe, manifest, state.checks, out)
    snapshot = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(RejectedEdit): session.apply({**recipe.model_dump(), 'x': 'missing'})
    assert session.current is state
    with pytest.raises(ValueError): export(state.result, recipe, manifest, [Check(name='bad', status='FAIL', detail='test')], out)
    assert snapshot == {p.name: p.read_bytes() for p in out.iterdir()}
    regenerate(out, tmp_path / 'regen')
    assert (out / 'plotted.csv').read_bytes() == (tmp_path / 'regen' / 'plotted.csv').read_bytes()
    verify_bundle(out)
    (out / 'plotted.csv').write_text((out / 'plotted.csv').read_text().replace('1,1,1', '1,99,1') + '\n')
    with pytest.raises(ValueError, match='Tampering'): verify_bundle(out)


def test_lhcb(source):
    from plotwright.presets import RULES
    df, manifest, recipe = source
    recipe = recipe.model_copy(update={'style_preset': 'lhcb', 'plot_type': 'hist_prebinned', 'title': 'Hidden by preset'})
    result = render(df, manifest, recipe)
    ax = result.fig.axes[0]
    assert not ax.get_title()
    assert any(t.get_text() == 'LHCb' for t in ax.texts)
    assert 'Candidates / (1 [s])' in ax.get_ylabel()
    assert all(r['source'] for r in RULES['lhcb'])


def test_fake_evals(tmp_path):
    from evals.run import run
    from plotwright.llm.fake import FakeAdapter
    outcomes, report, path = run(FakeAdapter(), results_dir=tmp_path)
    assert all(row['passed'] for row in outcomes), report
    for row in outcomes:
        if row['category'] == 'adversarial':
            assert row['got'] in ('refuse', 'question') or any('hidden_points:' in w for w in row['warnings'])
    assert path.exists()


def test_cli_tampering_and_standalone_regen(source, tmp_path):
    import subprocess
    import sys
    from plotwright.cli import main
    df, manifest, recipe = source
    recipe_path = tmp_path / 'recipe.json'
    recipe_path.write_text(recipe.model_dump_json())
    out = tmp_path / 'cli'
    assert main(['render', manifest.file, str(recipe_path), str(out)]) == 0
    assert main(['check', str(out)]) == 0
    subprocess.run([sys.executable, str(out / 'regen.py'), str(tmp_path / 'standalone')], check=True)
    assert (out / 'plotted.csv').read_bytes() == (tmp_path / 'standalone/plotted.csv').read_bytes()
    (out / 'plotted.csv').write_text('indices,x,y,yerr\n0,0,0,0\n')
    assert main(['check', str(out)]) == 1


def test_source_units_cannot_be_redeclared(source):
    from plotwright.session import Session, RejectedEdit
    df, manifest, recipe = source
    session = Session(df, manifest, recipe)
    before = session.current
    with pytest.raises(RejectedEdit, match='Source unit'):
        session.apply({**recipe.model_dump(), 'y_unit': 'cm'})
    with pytest.raises(RejectedEdit, match='Source unit'):
        session.apply({**recipe.model_dump(), 'y_unit': 'cm', 'transforms': [{'column': 'd', 'from_unit': 'mm', 'to_unit': 'cm'}]})
    assert session.current is before


def test_xlsx_affine_and_both_uncertainties(tmp_path):
    from plotwright.units import conversion
    path = tmp_path / 'source.xlsx'
    original = pd.DataFrame({'t': [1., 2.], 'temp': [10., 20.], 'dt': [.1, .2], 'dtemp': [.5, .6]})
    original.to_excel(path, sheet_name='Measured', index=False)
    contents = path.read_bytes()
    df, manifest = load_table(path, sheet='Measured')
    recipe = Recipe(x='t', y='temp', x_err='dt', y_err='dtemp', x_unit='ms', y_unit='K', transforms=[{'column':'t','from_unit':'s','to_unit':'ms'}, {'column':'temp','from_unit':'C','to_unit':'K'}])
    result = render(df, manifest, recipe)
    np.testing.assert_array_equal(result.plotted['xerr'], original.dt * 1000)
    np.testing.assert_allclose(result.plotted['y'], original.temp + 273.15)
    np.testing.assert_array_equal(result.plotted['yerr'], original.dtemp)
    assert all(c.status == 'PASS' for c in run_checks(df, manifest, recipe, result))
    assert path.read_bytes() == contents
    assert conversion('K', 'C') == (1., -273.15)
    with pytest.raises(ValueError): factor('K', 'C')


def test_faulty_fixture():
    from pathlib import Path
    df, manifest = load_table(Path(__file__).parents[1] / 'examples/faulty.csv')
    assert [reason for _, _, reason in manifest.invalid_cells].count('missing') == 2
    assert [reason for _, _, reason in manifest.invalid_cells].count('non-numeric') == 1
    recipe = Recipe(x='time_s', y='displacement_m', y_err='displacement_unc_m')
    result = render(df, manifest, recipe)
    row_check = next(c for c in run_checks(df, manifest, recipe, result) if c.name == 'rows_accounted')
    assert row_check.status == 'PASS' and '[1, 2, 3]' in row_check.detail


def test_tampered_operations_and_errorbars_rejected(source, tmp_path):
    from plotwright.export import export
    df, manifest, recipe = source
    result = render(df, manifest, recipe)
    checks = run_checks(df, manifest, recipe, result)
    out = tmp_path / 'existing'
    out.mkdir()
    (out / 'keep').write_text('unchanged')
    result.operations[0]['sha256'] = 'invented'
    with pytest.raises(ValueError, match='operations'): export(result, recipe, manifest, checks, out)
    assert list(out.iterdir()) == [out / 'keep']
    result = render(df, manifest, recipe)
    result.fig.axes[0].collections[0].set_segments([[[1, 0], [1, 9]]])
    checked = run_checks(df, manifest, recipe, result)
    assert next(c for c in checked if c.name == 'uncertainty_scaled').status == 'FAIL'
    with pytest.raises(ValueError): export(result, recipe, manifest, checks, out)
    assert (out / 'keep').read_text() == 'unchanged'


def test_export_after_ui_canvas_replacement(source, tmp_path):
    from matplotlib.backend_bases import FigureCanvasBase
    from plotwright.export import export, verify_bundle
    df, manifest, recipe = source
    result = render(df, manifest, recipe)
    FigureCanvasBase(result.fig)
    checks = run_checks(df, manifest, recipe, result)
    export(result, recipe, manifest, checks, tmp_path / 'serialized')
    assert all(c.status == 'PASS' for c in verify_bundle(tmp_path / 'serialized'))


def test_exclusion_visible_and_audited(source, tmp_path):
    import json
    from plotwright.export import export, verify_bundle
    df, manifest, recipe = source
    recipe = Recipe.model_validate({**recipe.model_dump(), 'exclusions': [{'row_index': 2, 'reason': 'sensor saturation', 'approved_by': 'Leo'}]})
    result = render(df, manifest, recipe)
    checks = run_checks(df, manifest, recipe, result)
    assert all(c.status == 'PASS' for c in checks)
    np.testing.assert_array_equal(result.plotted['y'], df.d)
    ax = result.fig.axes[0]
    line = ax.containers[1].lines[0]
    assert line.get_markerfacecolor() == 'none' and line.get_color() == 'grey'
    assert line.get_ydata().tolist() == [3.]
    assert 'excluded (1)' in [t.get_text() for t in ax.get_legend().get_texts()]
    out = export(result, recipe, manifest, checks, tmp_path / 'excluded')
    assert 'sensor saturation' in (out / 'run.log').read_text()
    check = next(c for c in json.loads((out / 'checks.json').read_text()) if c['name'] == 'exclusions')
    assert 'Leo' in check['detail'] and 'sensor saturation' in check['detail']
    assert all(c.status == 'PASS' for c in verify_bundle(out))


@pytest.mark.parametrize('exclusion', [{'row_index': 1}, {'row_index': 1, 'reason': 'bad'}, {'row_index': 1, 'reason': ' ', 'approved_by': 'Leo'}])
def test_unapproved_exclusion_fails_without_commit(source, exclusion):
    from plotwright.session import Session, RejectedEdit
    df, manifest, recipe = source
    session = Session(df, manifest, recipe)
    old = session.current
    candidate = Recipe.model_validate({**recipe.model_dump(), 'exclusions': [exclusion]})
    result = render(df, manifest, candidate)
    assert next(c for c in run_checks(df, manifest, candidate, result) if c.name == 'exclusions').status == 'FAIL'
    with pytest.raises(RejectedEdit, match='exclusions'): session.apply(candidate)
    assert session.current is old


def test_exclusion_cannot_disappear_or_be_hidden(source):
    from plotwright.session import Session, RejectedEdit
    df, manifest, recipe = source
    recipe = Recipe.model_validate({**recipe.model_dump(), 'exclusions': [{'row_index': 3, 'reason': 'reviewed', 'approved_by': 'Leo'}]})
    session = Session(df, manifest, recipe)
    with pytest.raises(RejectedEdit, match='outside axis limits'): session.apply({**recipe.model_dump(), 'y_lim': [0, 2]})
    result = session.current.result
    result.fig.axes[0].containers[1].lines[0].set_visible(False)
    assert next(c for c in run_checks(df, manifest, recipe, result) if c.name == 'exclusions').status == 'FAIL'
