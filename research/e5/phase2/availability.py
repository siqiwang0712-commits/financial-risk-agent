"""Outcome-value-blind SEC filing-metadata availability catalog.

SEC submissions JSON contains filing metadata, not financial outcomes. Only
filing/accession/form/period/date fields are retained. Dates near either window
boundary are excluded conservatively, avoiding ambiguous acceptance timezone
semantics in current submissions JSON. Numeric future facts are never fetched.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from .acquire_sec import USER_AGENT


def fetch(name):
    assert re.fullmatch(r'CIK\d{10}(?:-submissions-\d+)?\.json', name)
    url = 'https://data.sec.gov/submissions/'+name
    time.sleep(.3)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    return json.loads(raw), {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def rows(table):
    keys = ('accessionNumber', 'form', 'filingDate', 'reportDate')
    if not table:
        return []
    assert len({len(table[k]) for k in keys}) == 1
    return [{k: table[k][i] for k in keys} for i in range(len(table['form']))]


def build(universe, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    companies, exports = [], {}
    for case in universe['candidates']:
        cik = case['cik']
        cutoff = datetime.fromisoformat(case['accepted'])
        try:
            end = cutoff.replace(year=cutoff.year+1)
        except ValueError:
            end = cutoff.replace(year=cutoff.year+1, day=28)
        lo, hi = (cutoff+timedelta(days=2)).date().isoformat(), (end-timedelta(days=2)).date().isoformat()
        source_refs, failures, filings = [], [], []
        try:
            data, source = fetch('CIK'+cik+'.json')
            assert str(data['cik']).zfill(10) == cik
            source_refs.append(source)
            filings.extend(rows(data['filings']['recent']))
            recent_start = min((r['filingDate'] for r in filings), default='9999-12-31')
            if recent_start > lo:
                for shard in data['filings'].get('files', []):
                    if shard['filingTo'] >= lo and shard['filingFrom'] <= hi:
                        old, origin = fetch(shard['name'])
                        source_refs.append(origin)
                        filings.extend(rows(old))
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            failures.append({'error_type': type(exc).__name__, 'error': str(exc)})
        selected = [r for r in filings if r['form'] in {'10-K', '10-Q'} and lo <= r['filingDate'] <= hi
                    and r['reportDate'].replace('-', '') > case['period']]
        selected = list({r['accessionNumber']: r for r in selected}.values())
        index_period = date.fromisoformat(case['period'])
        annual = [r for r in selected if r['form'] == '10-K' and r['reportDate']
                  and 351 <= (date.fromisoformat(r['reportDate'])-index_period).days <= 380]
        periods = {r['reportDate'] for r in selected}
        observable = not failures and bool(annual) and len(periods) >= 2
        evidence = {'cik': cik, 'index_accession': case['accession'], 'cutoff': case['accepted'],
                    'window_end': end.isoformat(), 'conservative_interior_filed_dates': [lo, hi],
                    'official_submission_sources': source_refs, 'filing_metadata': selected,
                    'acquisition_failures': failures, 'financial_values_included': False,
                    'interpretation': 'Filing evidence is observable; financial-condition completeness is determined only after unlock.'}
        raw = (json.dumps(evidence, sort_keys=True, separators=(',', ':'))+'\n').encode()
        filename = cik+'.json'
        (output/filename).write_bytes(raw)
        exports[filename] = evidence
        companies.append({'cik': cik, 'window_fully_observable': observable,
                          'authoritative_evidence_url': 'https://www.sec.gov/edgar/browse/?CIK='+cik,
                          'source_catalog_sha256': hashlib.sha256(raw).hexdigest(),
                          'reason': 'OBSERVABLE_FILINGS' if observable else 'METADATA_ACQUISITION_FAILED' if failures else 'REQUIRED_FILING_EVIDENCE_NOT_OBSERVABLE'})
        print('metadata-only availability', cik, companies[-1]['reason'], flush=True)
    return {'scope': 'OFFICIAL_FILING_METADATA_ONLY_NO_FINANCIAL_OUTCOME_VALUES',
            'outcome_values_included': False, 'companies': companies,
            'evidence_exports': exports, 'universe_sha256': hashlib.sha256(
                (json.dumps(universe, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)+'\n').encode()).hexdigest()}
