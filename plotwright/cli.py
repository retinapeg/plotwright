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
    commands.add_parser('mcp', help='Run the local Plotwright MCP server over stdio')
    checking = commands.add_parser('check')
    checking.add_argument('out_dir')
    replaying = commands.add_parser('replay', help='Re-render a bundle and report the first differing value')
    replaying.add_argument('bundle_dir')
    args = parser.parse_args(argv)
    try:
        if args.command == 'replay':
            from .replay import replay, format_replay
            report = replay(args.bundle_dir)
            print(format_replay(report))
            return 0 if report['status'] == 'IDENTICAL' else 1
        if args.command == 'mcp':
            from .mcp_server import server
            server.run(transport='stdio')
            return 0
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
