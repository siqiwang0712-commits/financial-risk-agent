"""Live official SEC input, strictly bound to one original accession.

This never selects the latest CompanyFacts value. Every retained raw fact must
name exactly the index accession, original form and filed date. Future or other
filing entries cannot backfill comparatives. Snapshot hashes are immutable;
availability refers to the index filing, not the subsequently fetched snapshot.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

from finrisk.e4_core import E4_INSTANT_FIELDS, EXTENDED_ALIASES, _comparative_period
from finrisk.metrics import resolve_total_debt
from finrisk.xbrl import SecClient

from ..execution.core import (
    digest,
    file_hash,
    require,
    timestamp,
    utcnow,
    validate_features,
)
from .acquire_sec import USER_AGENT
from .producer import FIELDS, NumericProposalProducer, flatten
from .sources import select_value
from .study import REFERENCE


def extract(root: Path, cik: str, accession: str, cache: Path):
    client = SecClient(USER_AGENT, cache_dir=cache, pause_seconds=.3, max_retries=1)
    cik = client._normalize_cik(cik)
    # Both APIs are official SEC sources; no ticker or financial third party.
    submissions = client.submissions(cik)
    require(str(submissions['cik']).zfill(10) == cik, 'submissions cross-CIK substitution')
    table = submissions['filings']['recent']
    matches = [i for i, a in enumerate(table['accessionNumber']) if a == accession]
    require(len(matches) == 1, 'live index accession absent or ambiguous')
    i = matches[0]
    require(table['form'][i] == '10-K', 'original 10-K required')
    accepted = table['acceptanceDateTime'][i]
    accepted = __import__('datetime').datetime.fromisoformat(accepted.replace('Z', '+00:00')).isoformat()
    timestamp(accepted)
    period = table['reportDate'][i].replace('-', '')
    filed = table['filingDate'][i]
    payload = client.companyfacts(cik)
    require(str(payload['cik']).zfill(10) == cik, 'CompanyFacts cross-CIK substitution')
    source_bytes = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    rows, fiscal_years = [], set()
    aliases = {alias for values in EXTENDED_ALIASES.values() for alias in values}
    instant_tags = {tag for field in E4_INSTANT_FIELDS if field in EXTENDED_ALIASES for tag in EXTENDED_ALIASES[field]}
    for tag, concept in payload.get('facts', {}).get('us-gaap', {}).items():
        if tag not in aliases:
            continue
        for unit, entries in concept.get('units', {}).items():
            if unit not in {'USD', 'shares'}:
                continue
            for item in entries:
                if (item.get('accn') != accession or item.get('form') != '10-K'
                        or item.get('filed') != filed or item.get('fp') != 'FY'):
                    continue
                end = item.get('end')
                if not end or end.replace('-', '') > period:
                    continue
                if tag in instant_tags:
                    if item.get('start'):
                        continue
                    quarters = '0'
                else:
                    if not item.get('start') or not 330 <= (date.fromisoformat(end)-date.fromisoformat(item['start'])).days <= 400:
                        continue
                    quarters = '4'
                value = item.get('val')
                if type(value) not in (int, float) or not math.isfinite(value):
                    continue
                if type(item.get('fy')) is int:
                    fiscal_years.add(item['fy'])
                rows.append({'adsh': accession, 'tag': tag, 'ddate': end.replace('-', ''), 'qtrs': quarters,
                             'uom': unit, 'value': str(value), 'coreg': '', 'segments': '',
                             'origin': item, 'origin_hash': digest(item)})
    require(len(fiscal_years) == 1, 'index fiscal-year provenance is missing or ambiguous')
    year = next(iter(fiscal_years))
    require(year <= timestamp(accepted).year and period <= accepted[:10].replace('-', ''), 'post-cutoff period/year')
    previous_period = _comparative_period(rows, period)
    current, previous, provenance = {}, {}, {}
    for prefix, end, values in [('current', period, current), ('previous', previous_period, previous)]:
        for field in FIELDS:
            values[field], provenance[prefix+'__'+field] = select_value(rows, field, end)
        if values['total_debt'] is None:
            values['total_debt'], parents = resolve_total_debt(values)
            if values['total_debt'] is not None:
                provenance[prefix+'__total_debt'] = {'status': 'DERIVED_FROM_BOUND_SOURCE_ROWS',
                                                    'parents': [prefix+'__'+p for p in parents]}
    producer = NumericProposalProducer(root)
    packet = {'case_id': digest({'cik': cik, 'accession': accession})[:24], 'cik': cik, 'accession': accession,
              'filing_timestamp': accepted, 'prediction_cutoff': accepted,
              'schema_hash': digest(producer.schema), 'extraction_code_hash': file_hash(Path(__file__)),
              'preprocessing_hash': digest({'mode': 'SEC_ACCESSION_EXACT_NO_LATEST_NO_BACKFILL', 'source': file_hash(Path(__file__))}),
              'reference_distribution_hash': file_hash(root/REFERENCE), 'features': flatten(current, previous, year),
              'sources': [{'sha256': source_hash, 'available_at': accepted, 'filing_timestamp': accepted,
                           'accession': accession, 'cik': cik, 'role': 'INDEX_FILING'}]}
    validate_features(packet, schema_hash=digest(producer.schema), code_hash=file_hash(Path(__file__)))
    return {'packet': packet, 'evidence': {'packet_hash': digest(packet), 'provenance': provenance,
            'source_url': f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json', 'source_sha256': source_hash,
            'snapshot_acquired_at': utcnow(), 'availability_semantics': 'EXACT_INDEX_ACCESSION_FACTS_NOT_LATEST_VALUES',
            'index_metadata': {k: table[k][i] for k in ('accessionNumber', 'form', 'filingDate', 'reportDate', 'acceptanceDateTime')},
            'retained_accessions': sorted({r['adsh'] for r in rows}), 'future_or_other_accession_backfill': False,
            'known_limitation': 'Current SEC API snapshot; historical equivalence requires explicit qualification, and live use requires acquisition within the frozen prediction deadline.'}}
