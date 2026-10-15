from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict


class Manifest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file: str
    sha256: str
    sheet: str | int | None = None
    columns: dict[str, str]
    n_rows: int
    invalid_cells: list[tuple[int, str, str]]
    # Numeric evidence permits validation without exposing data to an adapter.
    nonpositive_columns: list[str] = []


def load_table(path, sheet=None):
    path = Path(path).resolve()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix.lower() == '.csv':
        if sheet is not None:
            raise ValueError('CSV has no sheets')
        df = pd.read_csv(path)
    elif path.suffix.lower() == '.xlsx':
        sheet = 0 if sheet is None else sheet
        df = pd.read_excel(path, sheet_name=sheet, engine='openpyxl')
    else:
        raise ValueError('Only CSV and XLSX are supported')
    df.columns = df.columns.map(str)
    invalid = []
    nonpositive = []
    for col in df:
        numeric = pd.to_numeric(df[col], errors='coerce')
        for row, (original, value) in enumerate(zip(df[col], numeric)):
            if pd.isna(original):
                invalid.append((row, col, 'missing'))
            elif pd.isna(value):
                invalid.append((row, col, 'non-numeric'))
            elif not np.isfinite(value):
                invalid.append((row, col, 'non-finite'))
        if (numeric <= 0).any():
            nonpositive.append(col)
    return df, Manifest(file=str(path), sha256=digest, sheet=sheet,
        columns={c: str(df[c].dtype) for c in df}, n_rows=len(df),
        invalid_cells=invalid, nonpositive_columns=nonpositive)
