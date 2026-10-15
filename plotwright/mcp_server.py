"""Local stdio MCP tools: all mutations use the same Session/export core as CLI."""
from threading import RLock
from typing import Any
from uuid import uuid4
import matplotlib.pyplot as plt
from mcp.server.fastmcp import FastMCP
from .data import load_table as read_table
from .session import Session, RejectedEdit
from .export import export, verify_bundle

server = FastMCP('plotwright', instructions='Only settings may change. Proposals do not commit. Approved exclusions stay visible. Show every WARN and FAIL to the user.')
_sessions: dict[str, Session] = {}
_lock = RLock()


def _session(session_id):
    if session_id not in _sessions: raise ValueError('Unknown session_id; call load_table first')
    return _sessions[session_id]


def _result(session_id, state, committed):
    return {'session_id': session_id, 'committed': committed,
        'valid': not any(c.status == 'FAIL' for c in state.checks),
        'recipe': state.recipe.model_dump(mode='json'),
        'checks': [c.model_dump() for c in state.checks]}


def _rejected(session_id, exc):
    checks = exc.checks or []
    return {'session_id': session_id, 'committed': False, 'valid': False,
        'checks': [c.model_dump() for c in checks] or [{'name': 'recipe_validation', 'status': 'FAIL', 'detail': str(exc)}],
        'reasons': exc.reasons}


@server.tool(structured_output=True)
def load_table(path: str, recipe: dict, sheet: str | int | None = None) -> dict[str, Any]:
    """Load a source and initial settings into an isolated session; return source evidence and checks."""
    with _lock:
        df, manifest = read_table(path, sheet)
        session = Session(df, manifest, recipe)
        session_id = uuid4().hex
        _sessions[session_id] = session
        return {**_result(session_id, session.current, True), 'manifest': manifest.model_dump(mode='json'), 'revision': 0}


@server.tool(structured_output=True)
def propose_recipe(session_id: str, recipe_patch: dict) -> dict[str, Any]:
    """Validate and check a candidate patch, returning all checks without committing it."""
    with _lock:
        session = _session(session_id)
        try:
            candidate = session.preview({**session.current.recipe.model_dump(), **recipe_patch})
            try:
                return {**_result(session_id, candidate, False), 'revision': len(session.history)}
            finally:
                plt.close(candidate.result.fig)
        except RejectedEdit as exc:
            return _rejected(session_id, exc)


@server.tool(structured_output=True)
def apply_recipe(session_id: str, recipe_patch: dict, expected_revision: int | None = None) -> dict[str, Any]:
    """Commit a settings patch only if every check avoids FAIL; optionally guard against a stale preview."""
    with _lock:
        session = _session(session_id)
        if expected_revision is not None and expected_revision != len(session.history):
            return _rejected(session_id, RejectedEdit(['Stale revision; propose again before applying']))
        try:
            state = session.apply({**session.current.recipe.model_dump(), **recipe_patch})
            return {**_result(session_id, state, True), 'revision': len(session.history)}
        except RejectedEdit as exc:
            return _rejected(session_id, exc)


@server.tool(structured_output=True)
def export_bundle(session_id: str, out_dir: str) -> dict[str, Any]:
    """Export current checked state transactionally, including source bytes and exact plotted arrays."""
    with _lock:
        session = _session(session_id)
        state = session.current
        out = export(state.result, state.recipe, session.manifest, state.checks, out_dir)
        return {'out_dir': str(out), 'checks': [c.model_dump() for c in state.checks]}


@server.tool(structured_output=True)
def check_bundle(bundle_dir: str) -> dict[str, Any]:
    """Re-render and compare a bundle with the identical code path used by plotwright check."""
    with _lock:
        return {'identical': True, 'checks': [c.model_dump() for c in verify_bundle(bundle_dir)]}
