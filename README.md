# Plotwright

Plotwright is a deterministic figure tool for physicists: an AI proposes only a strict settings recipe, while pandas loads an immutable source and matplotlib draws checked arrays. Every plotted value carries its zero-based source row index; fixed unit conversions scale uncertainties automatically, missing cells are reported without filling, and hidden points produce warnings. Approved exclusions stay visible as hollow grey markers. Multiple series and residuals use existing source columns only. The CLI, Streamlit app and local MCP server share the same validation, rendering, checks and export code. Python 3.12, uv, pandas, matplotlib/Agg, pydantic v2, openpyxl, Streamlit, pytest and MCP v1 (`mcp>=1,<2`); MIT licensed. FakeAdapter works offline; no live LLM calls have been made or validated.

## Two-minute demo

```sh
uv sync --python 3.12
make test
uv run python -m evals.run --adapter fake
make demo
make app
```

1. Upload `examples/freefall.csv` (also opens by default).
2. Ask **show displacement in cm and move the legend**. Values and uncertainties become ×100; the axis says `[cm]`.
3. Ask **drop the outlier**. See **QUESTION** asking for a zero-based row, reason and approver. The figure stays unchanged.
4. Enter **exclude row 2; reason: sensor review; approved_by: Leo**. Row 2 remains visible, hollow and grey, with `excluded (1)` in the legend. Use the actual reviewer and reason for real data.
5. Click **Export**, then **Download zip**. Unzip into `exported/` in this repository.
6. Regenerate, verify and replay without AI. Replay ends with `IDENTICAL`, or reports `DIFFERENT` and the first differing saved/replayed value.

The bundle includes source bytes, PNG/PDF, recipe, manifest, checks, exact plotted CSV, an operation-derived JSON-lines audit log and `regen.py`. The script works outside this checkout with Plotwright installed. Failed checks leave existing output untouched. Finish the demo with:

```sh
uv run python exported/regen.py regenerated/
uv run plotwright check regenerated/
uv run plotwright replay exported/
```

## CLI and examples

```sh
uv run plotwright render examples/freefall.csv examples/freefall_recipe.json out/
uv run plotwright check out/
uv run plotwright render examples/freefall_residuals.csv examples/freefall_residuals_recipe.json residual_out/
uv run plotwright render examples/lhcb_two_series.csv examples/lhcb_two_series_recipe.json mass_out/
uv run plotwright replay residual_out/
# XLSX: add --sheet SheetName to render
```

`check` and `replay` verify the bundled source hash and manifest, render the recipe, run checks, and compare `plotted.csv` byte-for-byte with canonical serialization. Replay is read-only: it reports the first differing field, saved/replayed values, source row, series and panel where available. Exit status is 0 for IDENTICAL, 1 for DIFFERENT. Source changes report the two hashes. The comparison covers plotted data, order, lengths and exclusion flags; it does not compare PNG/PDF pixels. Cosmetic-only recipe edits can leave plotted values identical. These are reproducibility checks, not cryptographic signatures against coordinated replacement of an entire bundle.

## Visible exclusions

```json
{"exclusions": [{"row_index": 2, "reason": "sensor review", "approved_by": "Leo"}]}
```

Exclusions mark source rows across every series and residual panel. They do not remove or alter numeric values, and residuals still include them. Markers and error bars remain visible in grey, with hollow markers and an `excluded (n)` legend. Line/step artists have a display gap at marked rows instead of connecting across them; the excluded values are drawn separately and remain in `plotted.csv`.

Missing/blank reason or approver produces an `exclusions` FAIL. Duplicate or out-of-range indices are rejected. An exclusion that cannot be drawn because of invalid source cells, or that lies outside axis limits, also fails. Reasons, approvers and indices are recorded in `checks.json` and `run.log`. Approval is an explicit recorded declaration, not authenticated identity verification. The adapter asks for missing details and never selects an outlier or invents approval.

## Multiple series and residuals

Use either legacy `y`/`y_err`, or a complete `series` list; do not supply both. A shared x column, x uncertainty, axis units and plot type apply to all series. For example:

```json
{
  "x": "time_s",
  "series": [
    {"y": "displacement_m", "y_err": "displacement_unc_m", "label": "Measurements"},
    {"y": "model_m", "y_err": null, "label": "Reference"}
  ],
  "residuals": {"against": "model_m"},
  "x_label": "Time [s]", "x_unit": "s",
  "y_label": "Displacement [m]", "y_unit": "m"
}
```

The lower panel shows each transformed y minus the transformed reference, with the same y/x uncertainties. The supplied reference is treated as exact: this schema has no reference uncertainty or covariance propagation. No fitting occurs. Residual y axes stay linear so negative residuals remain representable. Invalid rows are accounted for independently per series and panel; a missing reference value does not remove a valid main-panel measurement. CSV exports identify `series` and `panel` for multiple series/residuals. To convert a shared y axis, declare conversions for every plotted y column and the residual reference; partial conversion is rejected.

`examples/freefall_residuals.csv` contains measured displacement plus a separately supplied model column. Its residual recipe draws the lower panel; `freefall_model_recipe.json` starts with the main plot only. `lhcb_two_series.csv` and its recipe draw signal and control histograms without rebinning.

## MCP

Configure a local MCP client to run this command from the repository:

```sh
uv run plotwright mcp
```

The FastMCP server is named `plotwright` and uses stdio. It makes no LLM calls and starts no HTTP listener. Sessions live for the server process; `load_table` returns the session ID. Every response includes checks that clients should surface, including WARN and FAIL.

| Tool | Arguments | Behavior |
|---|---|---|
| `load_table` | `path`, complete `recipe`, optional `sheet` | Load source, validate initial state, return session ID, manifest and checks |
| `propose_recipe` | `session_id`, `recipe_patch` | Render/check a candidate without changing current state or history |
| `apply_recipe` | `session_id`, `recipe_patch`, optional `expected_revision` | Commit only with no FAIL; reject stale revisions and preserve current on failure |
| `export_bundle` | `session_id`, `out_dir` | Export current checked state transactionally |
| `check_bundle` | `bundle_dir` | Run the same re-render/CSV verification as the CLI |

Tests exercise registered FastMCP tools, compare checks and CSV output to CLI rendering for three examples, verify failed previews/edits preserve state, and initialize a real `uv run plotwright mcp` stdio client session.

## Architecture

```text
CSV/XLSX ── load_table ──> DataFrame + SHA-256 Manifest
                                │                │ metadata only
Prompt ─────────────────────────┼──────────> Fake / Claude adapter
                                │                │ settings Proposal
CLI / Streamlit / MCP ───────────┴──> Session.preview / Session.apply
                                           │
                               validate → render (Agg) → checks
                                           │
                                 FAIL: preserve current
                                 PASS/WARN: surface checks
                                           │
                             atomic export → regen / check / replay
```

The recipe has no code, data replacement, row deletion, filtering, fitting, smoothing, reordering or free-factor fields. Unknown fields are rejected. Source units are scientist declarations, not inferred physical truth; sessions retain declarations across added series to prevent relabeling from evading conversion. `m/cm/mm/um`, `s/ms/us`, `MeV/GeV/keV`, `deg/rad` are multiplicative. `C/K` use fixed affine offsets, with scale only for uncertainties. `factor('C', 'K')` raises because this is not a multiplication-only conversion. Display units such as `MeV/c^2` do not automatically enter the conversion registry.

Missing, non-numeric or non-finite cells are never filled. Negative uncertainties and non-positive log data are rejected. Prebinned plots use source centers and heights; the LHCb preset requires increasing, equally spaced centers for its bin-width label. LHCb-inspired rules in `plotwright/presets.py`, version 1, have explicitly **unverified** sources. Font sizes are preset-controlled.

## Offline eval results

57 cases, each sent through a fresh Session; reports are written to `evals/results/fake-<timestamp>.md`. Accepted exclusion cases check actual rendered visibility; multi-series and residual cases check resulting series/panels. Warnings appear in the report.

| Category | Passed | Rate |
|---|---:|---:|
| Cosmetic | 6/6 | 100% |
| Semantic | 9/9 | 100% |
| Adversarial | 16/16 | 100% |
| Ambiguity | 4/4 | 100% |
| Exclusions | 10/10 | 100% |
| Multi-series | 6/6 | 100% |
| Residuals | 6/6 | 100% |

Adversarial cases finish as a refusal/question, or a restrictive-axis edit with a surfaced `hidden_points WARN` naming source rows 4–11. FakeAdapter is a bounded keyword demonstration; these results do not establish Claude performance. The Claude adapter uses the Recipe schema for tool input and has updated exclusion instructions, but has not been called. Without `ANTHROPIC_API_KEY`, the app uses FakeAdapter; with a key it calls Claude only when **Propose edit** is clicked. `ANTHROPIC_MODEL` overrides the model.

## License

[MIT](LICENSE).
