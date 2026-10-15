"""Run with: uv run streamlit run app.py"""
from pathlib import Path
import hashlib
import io
import os
import uuid
import zipfile
import pandas as pd
import streamlit as st
from plotwright.data import load_table
from plotwright.recipe import Recipe
from plotwright.session import Session, RejectedEdit
from plotwright.llm.fake import FakeAdapter
from plotwright.presets import RULES
from plotwright.export import export

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='Plotwright', layout='wide')
st.title('Plotwright')
st.caption('AI chooses settings. Your source values stay locked. All row indices are zero-based.')
upload = st.file_uploader('Upload CSV or XLSX', type=['csv', 'xlsx'])
path = ROOT / 'examples/freefall.csv'
sheet = None
if upload:
    payload = upload.getvalue()
    directory = ROOT / '.plotwright_uploads'
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(payload).hexdigest() + Path(upload.name).suffix.lower())
    if not path.exists(): path.write_bytes(payload)
    if path.suffix == '.xlsx':
        with pd.ExcelFile(path, engine='openpyxl') as workbook:
            sheet = st.selectbox('Worksheet', workbook.sheet_names)
identity = (str(path), sheet)
if st.session_state.get('source_identity') != identity:
    try:
        df, manifest = load_table(path, sheet)
        if upload and hashlib.sha256(path.read_bytes()).hexdigest() != hashlib.sha256((ROOT / 'examples/freefall.csv').read_bytes()).hexdigest():
            numeric = [c for c in df if pd.to_numeric(df[c], errors='coerce').notna().any()]
            if len(numeric) < 2: raise ValueError('Choose a table with at least two numeric columns')
            recipe = Recipe(x=numeric[0], y=numeric[1], x_label=numeric[0], y_label=numeric[1])
        else:
            recipe = Recipe.model_validate_json((ROOT / 'examples/freefall_recipe.json').read_text())
        session = Session(df, manifest, recipe)
    except Exception as exc:
        st.error(f'Cannot load table: {exc}')
        st.stop()
    st.session_state.session = session
    st.session_state.source_identity = identity
    st.session_state.revision = st.session_state.get('revision', 0) + 1
    st.session_state.pop('zip_bytes', None)
    st.session_state.pop('decision', None)
session = st.session_state.session
manifest = session.manifest
with st.expander('Source manifest', expanded=True):
    st.write({'file': Path(manifest.file).name, 'sha256': manifest.sha256, 'sheet': manifest.sheet, 'rows': manifest.n_rows})
    st.dataframe(pd.DataFrame([{'column': c, 'dtype': d} for c, d in manifest.columns.items()]), hide_index=True)
    st.dataframe(pd.DataFrame(manifest.invalid_cells, columns=['row', 'column', 'reason']), hide_index=True)
left, right = st.columns([1, 1.5])

def accepted(message):
    st.session_state.revision += 1
    st.session_state.decision = message
    st.session_state.pop('zip_bytes', None)
    st.rerun()

with left:
    editor = st.text_area('Recipe JSON', value=session.current.recipe.model_dump_json(indent=2), height=350, key=f'recipe-{st.session_state.revision}')
    if st.button('Apply recipe'):
        try:
            session.apply(Recipe.model_validate_json(editor))
            accepted('Recipe accepted. Review checks below.')
        except (RejectedEdit, ValueError) as exc:
            st.error(f'Rejected edit: {exc}. Current figure unchanged.')
    if st.button('Undo', disabled=not session.history):
        session.undo()
        accepted('Previous recipe restored.')
    use_claude = bool(os.environ.get('ANTHROPIC_API_KEY'))
    st.caption('Adapter: Claude (key configured)' if use_claude else 'Adapter: FakeAdapter (offline keyword demo)')
    prompt = st.text_input('Ask for a setting', placeholder='show displacement in cm and move the legend')
    if st.button('Propose edit', disabled=not prompt.strip()):
        try:
            if use_claude:
                from plotwright.llm.claude import ClaudeAdapter
                adapter = ClaudeAdapter()
            else:
                adapter = FakeAdapter()
            proposal = adapter.propose(prompt, session.current.recipe, manifest, RULES[session.current.recipe.style_preset])
            if proposal.kind == 'edit':
                session.propose(proposal)
                accepted(proposal.message)
            else:
                st.session_state.decision = f'{proposal.kind.upper()}: {proposal.message}'
        except Exception as exc:
            st.error(f'Rejected edit: {exc}. Current figure unchanged.')
    if st.session_state.get('decision'): st.info(st.session_state.decision)
with right:
    state = session.current
    st.pyplot(state.result.fig, clear_figure=False)
    colors = {'PASS': '#d5f5dc', 'WARN': '#ffe5a0', 'FAIL': '#ffc4c4'}
    checks_table = pd.DataFrame([c.model_dump() for c in state.checks])
    st.dataframe(checks_table.style.map(lambda value: f'background-color: {colors[value]}; color: #111', subset=['status']), hide_index=True)
    for c in state.checks:
        if c.status == 'WARN': st.warning(f'{c.name}: {c.detail}')
    if st.button('Export'):
        try:
            token = st.session_state.setdefault('export_id', uuid.uuid4().hex)
            out = export(state.result, state.recipe, manifest, state.checks, ROOT / '.plotwright_exports' / token)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(out.iterdir()): archive.write(file, arcname=file.name)
            st.session_state.zip_bytes = buffer.getvalue()
            st.success('Export ready. Includes source, figures, audit records and regen.py.')
        except Exception as exc:
            st.error(f'Export refused: {exc}')
    if st.session_state.get('zip_bytes'):
        st.download_button('Download zip', st.session_state.zip_bytes, file_name='plotwright.zip', mime='application/zip')
