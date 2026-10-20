"""Preserve accession-bound archive values; resolve clocks from original EDGAR.

FSDS stores minute-resolution acceptance values. Original index pages provide
seconds in Eastern time. API acceptanceDateTime is not a clock authority here.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..execution.core import digest, file_hash, require, utcnow, validate_features
from .acquire_sec import USER_AGENT
from .sec_access import SpacedSecClient as SecClient
from .sources import accepted_utc
from .sources import extract_packets as archive_packets


def index_clock(cik, accession, cache: Path):
    client = SecClient(USER_AGENT, cache_dir=cache, pause_seconds=.3, max_retries=1)
    cik = client._normalize_cik(cik)
    require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) is not None, 'invalid index accession')
    url = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{accession}-index.html'
    raw = client.get_bytes(url, 'index-'+accession)
    found = re.search(r'Accepted\s*</div>\s*<div[^>]*>\s*([^<]+)', raw.decode(), re.IGNORECASE)
    require(found is not None, 'original EDGAR index acceptance missing')
    return {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'cik': cik, 'accession': accession,
            'accepted_eastern': found.group(1).strip(), 'accepted': accepted_utc(found.group(1).strip()),
            'precision': 'SECOND', 'authority': 'ORIGINAL_EDGAR_INDEX_NOT_API_ACCEPTANCE_FIELD'}


def resolve_universe(universe: dict, cache: Path):
    output = dict(universe)
    cases, excluded = [], list(universe['exclusions'])
    start, end = universe['window']
    for case in universe['candidates']:
        clock = index_clock(case['cik'], case['accession'], cache)
        accepted = clock['accepted']
        if not start <= accepted[:10] <= end:
            excluded.append({'cik': case['cik'], 'accession': case['accession'], 'reason': 'EXACT_INDEX_TIME_OUTSIDE_WINDOW'})
            continue
        cases.append(case | {'archive_accepted': case.get('archive_accepted', case['accepted']),
                             'accepted': accepted, 'clock_source': clock, 'clock_observed_at': utcnow()})
    output.update(candidates=cases, exclusions=excluded, parent_universe_hash=digest(universe),
                  acceptance_clock='ORIGINAL_EDGAR_INDEX_SECOND_RESOLUTION', outcome_values_used=False)
    return output


def extract_packets(root: Path, cohort: list[dict], manifests: list[Path], *, reference_hash: str):
    originals = [c | {'accepted': c['archive_accepted']} for c in cohort]
    bundles = archive_packets(root, originals, manifests, reference_hash=reference_hash)
    by_cik = {c['cik']: c for c in cohort}
    for bundle in bundles:
        packet, evidence = bundle['packet'], bundle['evidence']
        case = by_cik[packet['cik']]
        actual = index_clock(case['cik'], case['accession'], root/'.runtime/e5-index-clock')
        require(actual == case['clock_source'] and actual['accepted'] == case['accepted'], 'index clock source changed')
        packet['filing_timestamp'] = packet['prediction_cutoff'] = case['accepted']
        packet['extraction_code_hash'] = file_hash(Path(__file__))
        packet['preprocessing_hash'] = digest({'mode': 'UNCHANGED_FSDS_VALUES_WITH_PRIMARY_INDEX_CLOCK',
                                             'archive_extractor_sha256': file_hash(root/'research/e5/phase2/sources.py'),
                                             'clock_adapter_sha256': file_hash(Path(__file__))})
        for source in packet['sources']:
            source['available_at'] = source['filing_timestamp'] = case['accepted']
        evidence['archive_accepted'] = case['archive_accepted']
        evidence['index_clock_source'] = case['clock_source']
        evidence['source_mode'] = 'SEC_FSDS_WITH_PRIMARY_INDEX_CLOCK'
        evidence['packet_hash'] = digest(packet)
        validate_features(packet, schema_hash=packet['schema_hash'], code_hash=file_hash(Path(__file__)))
    return bundles
