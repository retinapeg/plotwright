"""Transactional artifact export. Audit text is derived only from recorded operations."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import pandas as pd
from .data import load_table, Manifest
from .recipe import Recipe
from .checks import run_checks
from .render import render


def plotted_csv(result):
    p = result.plotted
    return pd.DataFrame({k: p[k] for k in ('indices', 'x', 'y', 'yerr', 'xerr') if p[k] is not None}).to_csv(index=False, float_format='%.17g', lineterminator='\n')


_REGEN = '''from pathlib import Path
import argparse
from plotwright.export import regenerate

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenerate a Plotwright export without AI")
    parser.add_argument("out_dir", nargs="?", default=str(Path(__file__).parent / "regenerated"))
    args = parser.parse_args()
    regenerate(Path(__file__).parent, args.out_dir)
'''


def export(result, recipe, manifest, checks, out_dir):
    if any(c.status == 'FAIL' for c in checks):
        raise ValueError('Export refused: checks contain FAIL')
    source = Path(manifest.file)
    if hashlib.sha256(source.read_bytes()).hexdigest() != manifest.sha256:
        raise ValueError('Source file hash changed')
    df, fresh_manifest = load_table(source, manifest.sheet)
    if fresh_manifest.model_dump() != manifest.model_dump():
        raise ValueError('Manifest does not match source')
    fresh = run_checks(df, manifest, recipe, result)
    if any(c.status == 'FAIL' for c in fresh):
        raise ValueError('Export refused: live integrity check failed')
    out = Path(out_dir).resolve()
    if out == source or out in source.parents:
        raise ValueError('Output directory cannot contain the original source')
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.plotwright-', dir=out.parent))
    backup = None
    try:
        result.fig.savefig(stage / 'figure.png', dpi=100)
        result.fig.savefig(stage / 'figure.pdf', metadata={'CreationDate': None, 'ModDate': None})
        (stage / 'recipe.json').write_text(recipe.model_dump_json(indent=2))
        (stage / 'manifest.json').write_text(manifest.model_dump_json(indent=2))
        (stage / 'checks.json').write_text(json.dumps([c.model_dump() for c in fresh], indent=2))
        (stage / 'plotted.csv').write_text(plotted_csv(result))
        shutil.copyfile(source, stage / ('source' + source.suffix.lower()))
        records = result.operations + [{'operation': 'check', **c.model_dump()} for c in fresh]
        (stage / 'run.log').write_text('\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n')
        (stage / 'regen.py').write_text(_REGEN)
        if out.exists():
            backup = stage.with_name(stage.name + '-previous')
            out.rename(backup)
        try:
            stage.rename(out)
        except Exception:
            if backup: backup.rename(out)
            raise
        if backup: shutil.rmtree(backup)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return out


def load_bundle(directory):
    directory = Path(directory)
    manifest = Manifest.model_validate_json((directory / 'manifest.json').read_text())
    source = directory / ('source' + Path(manifest.file).suffix.lower())
    df, loaded = load_table(source, manifest.sheet)
    # The file location may move, but all source evidence must still match.
    if loaded.model_dump(exclude={'file'}) != manifest.model_dump(exclude={'file'}):
        raise ValueError('Bundled source or manifest was changed')
    recipe = Recipe.model_validate_json((directory / 'recipe.json').read_text())
    result = render(df, loaded, recipe)
    checks = run_checks(df, loaded, recipe, result)
    if any(c.status == 'FAIL' for c in checks): raise ValueError('Bundle checks failed')
    return recipe, loaded, result, checks


def verify_bundle(directory):
    recipe, manifest, result, checks = load_bundle(directory)
    if (Path(directory) / 'plotted.csv').read_bytes() != plotted_csv(result).encode():
        raise ValueError('Tampering detected: plotted.csv differs from source and recipe')
    return checks


def regenerate(directory, out_dir):
    recipe, manifest, result, checks = load_bundle(directory)
    return export(result, recipe, manifest, checks, out_dir)
