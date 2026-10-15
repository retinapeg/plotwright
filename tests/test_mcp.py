import asyncio
import json
from pathlib import Path
import sys
import pytest
import matplotlib.pyplot as plt
from plotwright.cli import main
from plotwright.mcp_server import server, _sessions

ROOT = Path(__file__).parents[1]


def call(name, **arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    # FastMCP v1 returns (content, structured_content) for dictionary outputs.
    if isinstance(result, tuple): return result[1]
    if isinstance(result, dict): return result
    return json.loads(result[0].text)


@pytest.fixture(autouse=True)
def close_sessions():
    yield
    _sessions.clear()
    plt.close('all')


@pytest.mark.parametrize('name', ['freefall', 'freefall_residuals', 'lhcb_two_series'])
def test_mcp_matches_cli_and_preview_does_not_commit(name, tmp_path):
    source = ROOT / 'examples' / f'{name}.csv'
    recipe_path = ROOT / 'examples' / f'{name}_recipe.json'
    recipe = json.loads(recipe_path.read_text())
    loaded = call('load_table', path=str(source), recipe=recipe)
    sid = loaded['session_id']
    assert main(['render', str(source), str(recipe_path), str(tmp_path / 'cli')]) == 0
    cli_checks = json.loads((tmp_path / 'cli/checks.json').read_text())
    assert loaded['checks'] == cli_checks
    before = _sessions[sid].current
    preview = call('propose_recipe', session_id=sid, recipe_patch={'legend_loc': 'lower right'})
    assert preview['valid'] and not preview['committed']
    assert _sessions[sid].current is before and not _sessions[sid].history
    proposed_path = tmp_path / 'proposed.json'
    proposed_path.write_text(json.dumps(preview['recipe']))
    assert main(['render', str(source), str(proposed_path), str(tmp_path / 'cli_proposed')]) == 0
    assert preview['checks'] == json.loads((tmp_path / 'cli_proposed/checks.json').read_text())
    applied = call('apply_recipe', session_id=sid, recipe_patch={'legend_loc': 'lower right'}, expected_revision=0)
    assert applied['committed'] and applied['checks'] == preview['checks']
    call('export_bundle', session_id=sid, out_dir=str(tmp_path / 'mcp'))
    assert (tmp_path / 'cli_proposed/plotted.csv').read_bytes() == (tmp_path / 'mcp/plotted.csv').read_bytes()
    assert call('check_bundle', bundle_dir=str(tmp_path / 'mcp'))['checks'] == applied['checks']
    assert main(['check', str(tmp_path / 'mcp')]) == 0
    failed = call('apply_recipe', session_id=sid, recipe_patch={'title': 'stale'}, expected_revision=0)
    assert not failed['committed'] and _sessions[sid].current.recipe.title != 'stale'


def test_failed_mcp_preview_and_apply_are_transactional(tmp_path):
    recipe = json.loads((ROOT / 'examples/freefall_recipe.json').read_text())
    loaded = call('load_table', path=str(ROOT / 'examples/freefall.csv'), recipe=recipe)
    sid = loaded['session_id']
    before = _sessions[sid].current
    for patch in ({'exclusions': [{'row_index': 2}]}, {'exclude_rows': [1]}, {'y': 'missing'}):
        proposed = call('propose_recipe', session_id=sid, recipe_patch=patch)
        applied = call('apply_recipe', session_id=sid, recipe_patch=patch)
        assert not proposed['valid'] and not applied['committed']
        assert any(c['status'] == 'FAIL' for c in proposed['checks'])
        assert _sessions[sid].current is before and not _sessions[sid].history
    call('export_bundle', session_id=sid, out_dir=str(tmp_path / 'out'))
    (tmp_path / 'out/plotted.csv').write_text('tampered')
    with pytest.raises(Exception, match='Tampering'): call('check_bundle', bundle_dir=str(tmp_path / 'out'))


def test_cli_mcp_stdio_handshake():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def exercise():
        async with stdio_client(StdioServerParameters(command=sys.executable, args=['-m', 'plotwright.cli', 'mcp'], cwd=str(ROOT))) as (read, write):
            async with ClientSession(read, write) as client:
                info = await client.initialize()
                assert info.serverInfo.name == 'plotwright'
                tools = await client.list_tools()
                assert {t.name for t in tools.tools} == {'load_table', 'propose_recipe', 'apply_recipe', 'export_bundle', 'check_bundle'}
                result = await client.call_tool('load_table', {'path': str(ROOT / 'examples/freefall.csv'), 'recipe': json.loads((ROOT / 'examples/freefall_recipe.json').read_text())})
                assert not result.isError
                assert all(c['status'] == 'PASS' for c in result.structuredContent['checks'])
    asyncio.run(exercise())
