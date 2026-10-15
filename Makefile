.PHONY: test demo app evals
test:
	uv run python -m pytest -q
demo:
	uv run plotwright render examples/freefall.csv examples/freefall_recipe.json demo_out/
	uv run plotwright check demo_out/
	uv run python -c "import json; assert all(c['status'] == 'PASS' for c in json.load(open('demo_out/checks.json')))"
app:
	uv run streamlit run app.py
evals:
	uv run python -m evals.run --adapter fake
