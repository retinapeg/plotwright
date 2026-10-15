"""Read-only bundle replay with the first exact plotted-value difference."""
import csv
import hashlib
import io
import json
from pathlib import Path
import matplotlib.pyplot as plt
from .export import load_bundle, plotted_csv


def replay(bundle_dir):
    directory = Path(bundle_dir)
    result = None
    try:
        saved_manifest = json.loads((directory / 'manifest.json').read_text())
        source = directory / ('source' + Path(saved_manifest['file']).suffix.lower())
        actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual_hash != saved_manifest['sha256']:
            return {'status': 'DIFFERENT', 'detail': 'Source hash differs', 'first_difference': {'field': 'sha256', 'saved': saved_manifest['sha256'], 'replayed': actual_hash}}
        _, _, result, checks = load_bundle(directory)
        expected_bytes = plotted_csv(result).encode()
        saved_bytes = (directory / 'plotted.csv').read_bytes()
        check_records = [c.model_dump() for c in checks]
        if saved_bytes == expected_bytes:
            return {'status': 'IDENTICAL', 'detail': 'Source hash verified; all plotted values, source indices, series, panels and exclusion flags are identical', 'first_difference': None, 'checks': check_records}
        saved_rows = list(csv.reader(io.StringIO(saved_bytes.decode())))
        expected_rows = list(csv.reader(io.StringIO(expected_bytes.decode())))
        difference = None
        for row_index in range(max(len(saved_rows), len(expected_rows))):
            saved = saved_rows[row_index] if row_index < len(saved_rows) else []
            expected = expected_rows[row_index] if row_index < len(expected_rows) else []
            if saved == expected: continue
            for col_index in range(max(len(saved), len(expected))):
                a = saved[col_index] if col_index < len(saved) else '<missing>'
                b = expected[col_index] if col_index < len(expected) else '<missing>'
                if a != b:
                    headers = expected_rows[0] if expected_rows else []
                    context = dict(zip(headers, expected)) if row_index else {}
                    difference = {'csv_row': row_index, 'field': headers[col_index] if col_index < len(headers) else f'column_{col_index}', 'saved': a, 'replayed': b,
                        **{k: context[k] for k in ('indices', 'series', 'panel') if k in context}}
                    break
            break
        if difference is None:
            index = next((i for i, (a, b) in enumerate(zip(saved_bytes, expected_bytes)) if a != b), min(len(saved_bytes), len(expected_bytes)))
            difference = {'field': 'CSV serialization', 'byte_offset': index, 'saved': repr(saved_bytes[index:index+24]), 'replayed': repr(expected_bytes[index:index+24])}
        return {'status': 'DIFFERENT', 'detail': 'plotted.csv differs from the replayed source and recipe', 'first_difference': difference, 'checks': check_records}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'status': 'DIFFERENT', 'detail': f'Bundle cannot be reproduced: {exc}', 'first_difference': {'field': 'bundle_validation', 'saved': 'bundle on disk', 'replayed': str(exc)}}
    finally:
        if result is not None: plt.close(result.fig)


def format_replay(report):
    text = f'{report["status"]}: {report["detail"]}'
    if report['first_difference']:
        text += '\nFirst difference: ' + json.dumps(report['first_difference'], sort_keys=True)
    warnings = [f'{c["status"]} {c["name"]}: {c["detail"]}' for c in report.get('checks', []) if c['status'] != 'PASS']
    return '\n'.join([text, *warnings])
