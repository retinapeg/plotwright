import argparse
from pathlib import Path
import sys
from .data import load_table
from .recipe import Recipe
from .session import Session
from .export import export, verify_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(prog='plotwright')
    commands = parser.add_subparsers(dest='command', required=True)
    rendering = commands.add_parser('render')
    rendering.add_argument('data')
    rendering.add_argument('recipe')
    rendering.add_argument('out_dir')
    rendering.add_argument('--sheet', default=None)
    checking = commands.add_parser('check')
    checking.add_argument('out_dir')
    args = parser.parse_args(argv)
    try:
        if args.command == 'render':
            df, manifest = load_table(args.data, args.sheet)
            recipe = Recipe.model_validate_json(Path(args.recipe).read_text())
            state = Session(df, manifest, recipe).current
            export(state.result, state.recipe, manifest, state.checks, args.out_dir)
            checks = state.checks
        else:
            checks = verify_bundle(args.out_dir)
        for c in checks: print(f'{c.status:4} {c.name}: {c.detail}')
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
