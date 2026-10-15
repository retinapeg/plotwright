# Tonight's status

Passed:

- `make test`: 15 tests passed under Python 3.12.
- `uv run python -m evals.run --adapter fake`: 31/31 cases; adversarial 12/12 (100%). The accepted restrictive-axis case surfaces a warning listing all eight hidden rows.
- `make demo`: freefall PNG/PDF exported; all eight checks PASS; bundle re-render and exact plotted CSV comparison PASS.
- Streamlit AppTest smoke: cm conversion, refused outlier removal with state unchanged, export and ZIP generation passed. Freefall figure visually inspected.
- Coverage includes source/uncertainty conversion, XLSX, affine temperatures, invalid-cell accounting, unknown fields/columns, hidden rows, transactional rejection/undo, untouched output on export failure, LHCb labels, standalone regeneration, changed CSV/artists/error bars and forged audit records.
- Required features and MIT license are committed locally. Nothing pushed. No API calls made.

Stubbed or deliberately limited:

- FakeAdapter is a keyword-based offline demonstration, not a general semantic model.
- Claude adapter is implemented with Recipe-schema tool use and key gating, but has not been live-tested.
- LHCb styling sources are explicitly unverified; this is an inspired preset, not an official style certification.
- Exclusion workflow is manual outside this app: review a separate source file and load it as a new dataset. There is no exclusion operation in a recipe.
- Source unit declarations are scientist-supplied; they cannot be independently established from CSV values. Celsius/Kelvin use fixed offsets, and `factor()` refuses those non-multiplicative pairs.
- Check verifies reproducibility, not authenticity against coordinated rewriting of every artifact.
- Existing user dependency edits in `pyproject.toml` and `uv.lock` were preserved and remain uncommitted. This working tree includes the required libraries; retain those dependency edits when transferring the project.

First thing tomorrow: configure an Anthropic key and model, then run the same eval suite against Claude and inspect refusals, ambiguity questions and surfaced warnings before using it on research figures.
