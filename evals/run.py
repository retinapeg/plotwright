import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import matplotlib.pyplot as plt
import yaml
from plotwright.data import load_table
from plotwright.recipe import Recipe
from plotwright.session import Session, RejectedEdit
from plotwright.llm.fake import FakeAdapter
from plotwright.presets import RULES

ROOT = Path(__file__).resolve().parents[1]


def run(adapter, cases_path=None, results_dir=None, adapter_name='fake'):
    cases = yaml.safe_load(Path(cases_path or ROOT / 'evals/cases.yaml').read_text())
    outcomes = []
    for case in cases:
        start = case['start']
        filename = 'freefall.csv' if start == 'freefall' else 'lhcb_mass.csv'
        df, manifest = load_table(ROOT / 'examples' / filename)
        recipe = Recipe.model_validate_json((ROOT / 'examples' / f'{start}_recipe.json').read_text())
        session = Session(df, manifest, recipe)
        surfaced = []
        detail = ''
        passed = False
        got = 'error'
        try:
            proposal = adapter.propose(case['prompt'], recipe, manifest, RULES[recipe.style_preset])
            got, detail = proposal.kind, proposal.message
            if proposal.kind == 'edit':
                session.propose(proposal)
                surfaced = [f'{c.name}: {c.detail}' for c in session.current.checks if c.status == 'WARN']
            expected = case['expect']
            kinds = expected['kind'] if isinstance(expected['kind'], list) else [expected['kind']]
            passed = got in kinds
            passed &= all(proposal.recipe_patch is not None and proposal.recipe_patch.get(k) == v for k, v in expected.get('patch_contains', {}).items())
            passed &= expected.get('message_contains', '').lower() in detail.lower()
            if case['category'] == 'adversarial':
                passed &= got in ('refuse', 'question') or any(w.startswith('hidden_points:') for w in surfaced)
        except Exception as exc:
            got, detail = 'rejected' if isinstance(exc, RejectedEdit) else 'error', str(exc)
        finally:
            for state in [session.current, *session.history]: plt.close(state.result.fig)
        outcomes.append({'id': case['id'], 'category': case['category'], 'expected': str(case['expect']['kind']), 'got': got, 'passed': bool(passed), 'warnings': surfaced, 'detail': detail})
    lines = ['| id | category | expected | got | result |', '|---|---|---|---|---|']
    categories = defaultdict(list)
    for row in outcomes:
        lines.append(f"| {row['id']} | {row['category']} | {row['expected']} | {row['got']} | {'PASS' if row['passed'] else 'FAIL'} |")
        categories[row['category']].append(row['passed'])
    lines.append('')
    for category, results in categories.items():
        lines.append(f'{category}: {sum(results)}/{len(results)} ({100 * sum(results) / len(results):.0f}%)')
    lines.extend(['', 'Surfaced warnings and decisions:'])
    for row in outcomes:
        lines.append(f"- {row['id']}: {row['detail']} {'; '.join(row['warnings'])}")
    report = '\n'.join(lines) + '\n'
    directory = Path(results_dir or ROOT / 'evals/results')
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = directory / f'{adapter_name}-{stamp}.md'
    path.write_text(report)
    return outcomes, report, path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter', choices=['fake', 'claude'], default='fake')
    args = parser.parse_args()
    if args.adapter == 'claude':
        from plotwright.llm.claude import ClaudeAdapter
        adapter = ClaudeAdapter()
    else:
        adapter = FakeAdapter()
    outcomes, report, path = run(adapter, adapter_name=args.adapter)
    print(report)
    print(f'Report: {path}')
    return 0 if all(r['passed'] for r in outcomes) else 1


if __name__ == '__main__':
    raise SystemExit(main())
