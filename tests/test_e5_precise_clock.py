"""Source-clock regressions. Synthetic fixtures are never empirical E5 evidence."""
import csv
import io
import zipfile
from pathlib import Path

import pytest
from finrisk.e4_core import E4_INSTANT_FIELDS, EXTENDED_ALIASES

from research.e5.execution.core import file_hash, freeze_json, read_json, verify_files
from research.e5.phase2.precise_endpoint import extract
from research.e5.phase2.precise_source import index_clock
from research.e5.phase2.prospective import enrollment_window


def test_original_index_clock_rejects_the_submissions_api_clock(monkeypatch, tmp_path):
    rows = read_json(Path(__file__).resolve().parents[1]/'research/e5/phase2/qualification/edgar-acceptance-audit.json')
    record = rows[0]
    monkeypatch.setattr('research.e5.phase2.precise_source.SecClient.get_bytes', lambda *args: record['index_html'].encode())
    clock = index_clock(record['cik'], record['accession'], tmp_path)
    assert clock['accepted'] == '2025-08-14T21:51:56+00:00'
    assert clock['sha256'] == record['sha256']
    assert clock['precision'] == 'SECOND'


@pytest.mark.parametrize(('actual_clock', 'expected'), [
    ('2025-08-01T00:00:01Z', None),
    ('2025-07-31T23:59:59Z', 1),
])
def test_endpoint_uses_exact_clock_on_both_sides_of_horizon(tmp_path, monkeypatch, actual_clock, expected):
    adsh = '0000000001-25-000001'
    def table(rows):
        text = io.StringIO()
        writer = csv.DictWriter(text, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
        return text.getvalue()
    sub = {'adsh': adsh, 'cik': '1', 'form': '10-K', 'period': '20241231', 'fy': '2024', 'fp': 'FY',
           'accepted': '2025-07-31 20:00:00'}
    values = {'revenue': 70, 'net_income': -5, 'operating_cash_flow': 15, 'total_assets': 100, 'total_debt': 10}
    nums = [{'adsh': adsh, 'tag': EXTENDED_ALIASES[k][0], 'ddate': '20241231', 'uom': 'USD',
             'qtrs': '0' if k in E4_INSTANT_FIELDS else '4', 'value': str(v)} for k, v in values.items()]
    archive = tmp_path/'2025q3.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('sub.txt', table([sub]))
        z.writestr('num.txt', table(nums))
    manifest = tmp_path/'manifest.json'
    freeze_json(manifest, {'source_type': 'SEC_FSDS', 'dataset_quarter': '2025q3', 'file': archive.name,
                          'sha256': file_hash(archive), 'download_timestamp': '2026-10-20T00:00:00Z',
                          'source_url': 'https://www.sec.gov/files/dera/data/financial-statement-data-sets/2025q3.zip'})
    features = {'fiscal_year': 2023} | {'current__'+k: v for k, v in
               {'revenue': 100, 'net_income': 5, 'operating_cash_flow': 15, 'total_assets': 100, 'total_debt': 10}.items()}
    bundle = {'packet': {'case_id': 'synthetic', 'cik': '0000000001',
                         'prediction_cutoff': '2024-08-01T00:00:00Z', 'features': features}}
    monkeypatch.setattr('research.e5.phase2.precise_endpoint.index_clock', lambda *args: {'accepted': actual_clock})
    result = extract([bundle], [manifest], as_of='2026-10-20T00:00:00Z')['outcomes'][0]
    assert result['label'] == expected
    assert result['status'] == ('VERIFIED' if expected is not None else 'INSUFFICIENT_DATA')


def test_enrollment_window_is_frozen_before_any_prospective_case():
    start, stop = enrollment_window('2026-10-20T00:00:00Z')
    assert start.isoformat() == '2027-01-01T00:00:00+00:00'
    assert stop.isoformat() == '2028-01-01T00:00:00+00:00'


def test_common_core_is_preserved_after_exact_clock_extension():
    root = Path(__file__).resolve().parents[1]
    old = read_json(root/'research/e5/phase2/e5p-core/protocol.json')
    verify_files(root, old['payload']['bindings'])
