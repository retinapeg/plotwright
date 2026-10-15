# Plotwright status

Completed and committed locally:

- Explicit exclusions retain every numeric value and draw marked rows hollow/grey with `excluded (n)` legends. Missing reasons/approvers fail checks; invalid, out-of-range, duplicate or hidden excluded rows cannot be accepted. Audit records include row, reason and approver.
- Multiple source series share x; residual panels subtract a supplied reference column and retain error bars. Data-lock and row accounting run independently per series/panel. New freefall model/residual and two-series LHCb examples are included.
- FastMCP server `plotwright`, with `mcp>=1,<2` (lock: 1.30.0), runs through `uv run plotwright mcp`. Its five tools use the CLI's Session/export/check core. Preview does not commit; apply rejects FAIL and stale revisions.
- `plotwright replay bundle/` verifies source hash, re-renders and reports IDENTICAL/DIFFERENT, with the first differing field, saved/replayed values and source row/series/panel where available. It is the README demo's last command.

Verification passed:

- `make test`: 35 tests passed under Python 3.12.
- `uv run python -m evals.run --adapter fake`: 57/57 cases. Adversarial 16/16, exclusions 10/10, multi-series 6/6, residuals 6/6; every category is 100%.
- Latest eval report: `evals/results/fake-20261015T222412472622Z.md`. A full passing report is also committed at `evals/results/fake-20261015T222131373462Z.md`.
- Registered MCP tool checks and exported arrays equal CLI results for freefall, freefall residuals and two-series histograms. Real `uv run plotwright mcp` stdio initialization/tool calls passed, with structured responses.
- Rejected edits and previews preserve current state; approved exclusions remain visible and audited. Residual artist/row tampering, changed CSV values, missing CSV rows and changed source hashes are detected. New series retain source-unit declarations across later edits.
- `make demo`: all nine freefall checks PASS and exported CSV verification PASS. Both new examples render with green checks and were visually inspected.
- Offline Streamlit smoke: missing exclusion details produce QUESTION with unchanged state; an approved exclusion renders visibly, exports a ZIP and replays IDENTICAL.

Stubbed or limited:

- None of the four requested additions is stubbed. FakeAdapter remains a bounded keyword demonstration.
- Claude's schema/prompt were updated but no LLM calls were made; live behavior remains unvalidated.
- `approved_by` records an explicit declaration, not authenticated identity. Reference columns are treated as exact; reference uncertainty/covariance propagation is not implemented in this schema.
- Source units are scientist declarations. LHCb styling sources remain explicitly unverified.
- Replay compares source evidence and exact plotted CSV, not image pixels or cryptographic authenticity. MCP sessions are local and live only for the server process.

First thing tomorrow: connect a local MCP client using `uv run plotwright mcp` from this repository and exercise load → propose → apply → export → check on the freefall residual example.

Nothing pushed. No LLM calls. Existing dependency work was already committed before this task; all additions are committed on the existing main branch.
