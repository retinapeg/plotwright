import csv
import io
from pathlib import Path
import matplotlib.pyplot as plt
import pytest
from plotwright.cli import main
from plotwright.replay import replay

ROOT = Path(__file__).parents[1]


@pytest.fixture
def bundle(tmp_path):
    out = tmp_path / 'bundle'
    assert main(['render', str(ROOT / 'examples/freefall_residuals.csv'), str(ROOT / 'examples/freefall_residuals_recipe.json'), str(out)]) == 0
    yield out
    plt.close('all')


def test_replay_is_identical_and_read_only(bundle, capsys):
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    assert main(['replay', str(bundle)]) == 0
    assert 'IDENTICAL:' in capsys.readouterr().out
    assert replay(bundle)['first_difference'] is None
    assert before == {p.name: p.read_bytes() for p in bundle.iterdir()}


def test_replay_reports_first_differing_residual_value(bundle, capsys):
    path = bundle / 'plotted.csv'
    rows = list(csv.DictReader(io.StringIO(path.read_text())))
    target = next(row for row in rows if row['panel'] == 'residual')
    original = target['y']
    target['y'] = '999'
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
    path.write_text(out.getvalue())
    report = replay(bundle)
    assert report['status'] == 'DIFFERENT'
    assert report['first_difference']['field'] == 'y'
    assert report['first_difference']['saved'] == '999'
    assert report['first_difference']['replayed'] == original
    assert report['first_difference']['panel'] == 'residual'
    assert report['first_difference']['indices'] == '0'
    assert main(['replay', str(bundle)]) == 1
    assert 'First difference:' in capsys.readouterr().out


def test_replay_rejects_source_hash_change(bundle):
    path = bundle / 'source.csv'
    path.write_bytes(path.read_bytes() + b'\n')
    report = replay(bundle)
    assert report['status'] == 'DIFFERENT'
    assert report['first_difference']['field'] == 'sha256'
    assert report['first_difference']['saved'] != report['first_difference']['replayed']


def test_replay_reports_missing_row(bundle):
    path = bundle / 'plotted.csv'
    path.write_text('\n'.join(path.read_text().splitlines()[:-1]) + '\n')
    report = replay(bundle)
    assert report['status'] == 'DIFFERENT'
    assert report['first_difference']['saved'] == '<missing>'
