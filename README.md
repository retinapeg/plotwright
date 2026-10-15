# Plotwright

Plotwright is a deterministic figure tool for physicists: an AI proposes only a strict settings recipe, while pandas loads an immutable source and matplotlib draws checked arrays. Every plotted value carries its zero-based source row index; unit conversions come from a closed registry, uncertainties scale automatically, invalid cells are reported without filling, and hidden points produce visible warnings. Tonight's build runs entirely offline with a keyword-based FakeAdapter; the optional Claude tool-use adapter is written but has not been called or live-validated. Python 3.12, uv, pandas, matplotlib/Agg, pydantic v2, openpyxl, Streamlit and pytest; MIT licensed.

## Two-minute demo

```sh
uv sync --python 3.12
make test
uv run python -m evals.run --adapter fake
make demo
make app
```

1. Upload `examples/freefall.csv` (the same example also opens by default).
2. Ask **show displacement in cm and move the legend**. Values and uncertainties become ×100; the axis says `[cm]`.
3. Ask **drop the outlier**. See **REFUSE**, with the figure unchanged.
4. Click **Export**, then **Download zip**. Unzip into `exported/` in this repository.
5. Regenerate and verify, without any AI:

```sh
uv run python exported/regen.py regenerated/
uv run plotwright check exported/
uv run plotwright check regenerated/
```

The generated `regen.py` works outside this checkout too, with Plotwright installed in its Python environment. Bundles include a byte-for-byte source copy, so the original source path need not exist. PNG, PDF, recipe, manifest, checks, exact plotted CSV and an operation-derived JSON-lines audit log are included. Export is staged before replacing a destination; failed checks leave existing output untouched.

## CLI

```sh
uv run plotwright render examples/freefall.csv examples/freefall_recipe.json out/
uv run plotwright check out/
uv run plotwright render examples/lhcb_mass.csv examples/lhcb_recipe.json mass_out/
# XLSX: add --sheet SheetName
```

`check` hashes the bundled source, validates its manifest, re-renders the recipe, runs checks, and compares `plotted.csv` byte-for-byte with canonical serialization. It detects changed values, row order, lengths and CSV formatting. This is reproducibility/integrity checking, not a cryptographic signature against coordinated replacement of an entire bundle.

## Architecture

```text
CSV/XLSX ── load_table ──> DataFrame + SHA-256 Manifest
                                │                   │ metadata only
                                │                   v
Prompt ─────────────────────────────────────> Fake / Claude adapter
                                │                   │ settings Proposal
                                v                   v
                         Session.apply <── strict Recipe
                                │
                      validate → render (Agg) → checks
                                │
                      FAIL: reject, preserve current
                      PASS/WARN: accept, surface warnings
                                │
                       atomic export → regen.py → same core
```

The recipe has no code, data replacement, row selection, filtering, fitting, smoothing, reordering or free-factor fields. The adapter never receives source arrays. Unknown fields are rejected. Source units are user declarations, not inferred physical truth; a session prevents changing an established source-unit declaration to evade conversion. `m/cm/mm/um`, `s/ms/us`, `MeV/GeV/keV`, `deg/rad` are multiplicative. `C/K` conversions use fixed affine offsets; uncertainties use only the multiplicative scale. `factor('C', 'K')` deliberately raises because temperature values cannot be converted by multiplication alone; recipes support the registered affine conversion. Display units such as `MeV/c^2` are allowed, but are not automatically added to the conversion registry.

Rows with missing, non-numeric or non-finite values in referenced columns are explicitly accounted for and omitted together; no values are filled. Invalid cells in other columns remain in the manifest. Negative uncertainties and non-positive log data are rejected. Supplied uncertainties are drawn for every plot type. Prebinned plots use source centers and heights without rebinning; the LHCb preset requires equally spaced, increasing centers to state an honest bin width.

LHCb-inspired rules are explicit in `plotwright/presets.py`, version 1; each source is marked **unverified**, not official experiment approval. Fonts and centered titles are preset-controlled, so “bigger font” asks about the preset rather than inventing a recipe field. Exclusions are deliberately absent: a scientist must create and review a separate source file and start a new dataset. The app does not perform or automate that workflow.

## Offline eval results

31 cases, each sent through a fresh Session; reports are written to `evals/results/fake-<timestamp>.md`. Warnings are included in the report, not merely counted internally.

| Category | Passed | Rate |
|---|---:|---:|
| Cosmetic | 6/6 | 100% |
| Semantic | 9/9 | 100% |
| Adversarial | 12/12 | 100% |
| Ambiguity | 4/4 | 100% |

Eleven adversarial requests are refused. “Set y from 0 to 1 so it looks cleaner” produces an edit with `hidden_points WARN`, listing source rows 4–11. FakeAdapter is a bounded demonstration, not a general language-understanding system; these results do not establish Claude performance.

Claude uses the Anthropic SDK and the full Recipe JSON schema as its edit-tool schema, plus question/refusal tools. Without `ANTHROPIC_API_KEY`, the app uses FakeAdapter. With a key configured it calls Claude only when **Propose edit** is clicked; `ANTHROPIC_MODEL` can override the configured model. No live API calls were made for this build.

## License

[MIT](LICENSE).
