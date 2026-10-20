"""Live original-filing XBRL input; never current/latest CompanyFacts values.

Only the index accession's extracted instance is admitted. Entity, period, unit,
consolidation and annual duration are checked before deterministic alias choice.
Acceptance comes from the original EDGAR index in seconds, not API timestamps.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from finrisk.e4_core import E4_INSTANT_FIELDS, EXTENDED_ALIASES, _comparative_period
from finrisk.metrics import resolve_total_debt

from ..execution.core import (
    GateError,
    digest,
    file_hash,
    freeze_json,
    read_json,
    require,
    timestamp,
    utcnow,
    validate_features,
)
from .acquire_sec import USER_AGENT
from .precise_source import index_clock
from .producer import FIELDS, NumericProposalProducer, flatten
from .sec_access import SpacedSecClient as SecClient
from .sources import select_value
from .study import REFERENCE

NS = {'x': 'http://www.xbrl.org/2003/instance'}


def resolve_precision(rows):
    """Keep the unique most precise duplicate only when every declared interval contains it.

    Context identity, concept, unit and period must all agree. Inconsistent,
    equally precise discordant or undeclared precision facts remain conflicting.
    This handles rounded narrative repetitions without averaging any values.
    """
    groups = {}
    for row in rows:
        key = tuple(row[k] for k in ('context_id', 'tag', 'uom', 'ddate', 'qtrs'))
        groups.setdefault(key, []).append(row)
    retained, resolutions = [], []
    for group in groups.values():
        try:
            values = [Decimal(r['value']) for r in group]
            require(all(v.is_finite() for v in values), 'nonfinite XBRL fact')
            if len(set(values)) <= 1:
                retained.extend(group)
                continue
            bounds = []
            for row, value in zip(group, values, strict=True):
                precision = row.get('decimals')
                if precision == 'INF':
                    radius = Decimal(0)
                else:
                    require(isinstance(precision, str) and re.fullmatch(r'-?\d{1,2}', precision) is not None,
                            'ambiguous declared precision')
                    radius = Decimal(10)**(-int(precision))/2
                bounds.append((value-radius, value+radius, radius))
            minimum = min(b[2] for b in bounds)
            best = [i for i, b in enumerate(bounds) if b[2] == minimum]
            require(len({values[i] for i in best}) == 1, 'equally precise contradictory facts')
            selected = min(best, key=lambda i: digest(group[i]))
            lo, hi, _ = bounds[selected]
            require(all(b[0] <= lo and hi <= b[1] for b in bounds), 'inconsistent rounding intervals')
            retained.append(group[selected])
            resolutions.append({'method': 'UNIQUE_MOST_PRECISE_INTERVAL_CONTAINED_IN_ALL_DUPLICATES',
                                'selected_row_hash': digest(group[selected]), 'all_rows': group})
        except (GateError, ValueError, TypeError, InvalidOperation):
            retained.extend(group)
    return retained, resolutions


def extract(root: Path, cik: str, accession: str, cache: Path):
    cik = SecClient._normalize_cik(cik)
    require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) is not None, 'invalid accession')
    client = SecClient(USER_AGENT, cache_dir=cache, pause_seconds=.3, max_retries=1)
    submissions = client.submissions(cik)
    require(str(submissions['cik']).zfill(10) == cik, 'submissions cross-CIK substitution')
    recent = submissions['filings']['recent']
    matches = [i for i, a in enumerate(recent['accessionNumber']) if a == accession]
    require(len(matches) == 1 and recent['form'][matches[0]] == '10-K', 'one original index 10-K required')
    i = matches[0]
    clock = index_clock(cik, accession, root/'.runtime/e5-index-clock')
    accepted = clock['accepted']
    base = f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
    listing = client.get_json(base+'index.json', 'directory-'+accession)
    names = [r['name'] for r in listing['directory']['item'] if r['name'].endswith('_htm.xml')]
    require(len(names) == 1 and re.fullmatch(r'[A-Za-z0-9._-]+', names[0]) is not None,
            'one accession-bound extracted XBRL instance required')
    url = base+names[0]
    raw = client.get_bytes(url, 'instance-'+accession)
    require(b'<!DOCTYPE' not in raw.upper(), 'document type declarations forbidden')
    source_hash = hashlib.sha256(raw).hexdigest()
    tree = ET.fromstring(raw)
    require(tree.tag == '{http://www.xbrl.org/2003/instance}xbrl', 'XBRL instance root required')
    meta = {}
    for node in tree:
        local = node.tag.rsplit('}', 1)[-1]
        if local in {'DocumentFiscalYearFocus', 'DocumentPeriodEndDate', 'DocumentType', 'EntityCentralIndexKey'}:
            meta.setdefault(local, set()).add((node.text or '').strip())
    require(all(len(meta.get(k, set())) == 1 for k in ('DocumentFiscalYearFocus', 'DocumentPeriodEndDate', 'DocumentType')),
            'unambiguous original document metadata required')
    require(next(iter(meta['DocumentType'])) == '10-K', 'amendment or nonannual instance rejected')
    year = int(next(iter(meta['DocumentFiscalYearFocus'])))
    period = next(iter(meta['DocumentPeriodEndDate'])).replace('-', '')
    require(period == recent['reportDate'][i].replace('-', '') and year <= timestamp(accepted).year,
            'index reporting period/year mismatch')
    if meta.get('EntityCentralIndexKey'):
        require({str(int(v)).zfill(10) for v in meta['EntityCentralIndexKey']} == {cik}, 'instance cross-CIK substitution')
    contexts = {}
    for context in tree.findall('x:context', NS):
        identifier = context.find('x:entity/x:identifier', NS)
        if identifier is None or not (identifier.text or '').isdigit() or str(int(identifier.text)).zfill(10) != cik:
            continue
        if context.find('.//x:segment', NS) is not None or context.find('x:scenario', NS) is not None:
            continue
        instant = context.findtext('x:period/x:instant', namespaces=NS)
        start = context.findtext('x:period/x:startDate', namespaces=NS)
        end = context.findtext('x:period/x:endDate', namespaces=NS)
        if instant:
            contexts[context.attrib['id']] = (instant.replace('-', ''), '0')
        elif start and end and 330 <= (date.fromisoformat(end)-date.fromisoformat(start)).days <= 400:
            contexts[context.attrib['id']] = (end.replace('-', ''), '4')
    units = {}
    for unit in tree.findall('x:unit', NS):
        measures = unit.findall('x:measure', NS)
        if len(measures) == 1:
            name = (measures[0].text or '').split(':')[-1]
            if name in {'USD', 'shares'}:
                units[unit.attrib['id']] = name
    aliases = {v for group in EXTENDED_ALIASES.values() for v in group}
    rows = []
    for node in tree:
        tag = node.tag.rsplit('}', 1)[-1]
        context = contexts.get(node.attrib.get('contextRef'))
        unit = units.get(node.attrib.get('unitRef'))
        if '/us-gaap/' not in node.tag or tag not in aliases or not context or not unit or context[0] > period:
            continue
        if context[1] != ('0' if any(tag in EXTENDED_ALIASES[f] for f in E4_INSTANT_FIELDS if f in EXTENDED_ALIASES) else '4'):
            continue
        rows.append({'adsh': accession, 'tag': tag, 'ddate': context[0], 'qtrs': context[1], 'uom': unit,
                     'value': (node.text or '').strip(), 'coreg': '', 'segments': '',
                     'context_id': node.attrib.get('contextRef'), 'decimals': node.attrib.get('decimals')})
    require(bool(rows), 'qualified consolidated financial schema unavailable')
    rows, precision_resolutions = resolve_precision(rows)
    previous_period = _comparative_period(rows, period)
    current, previous, provenance = {}, {}, {}
    for prefix, end, values in [('current', period, current), ('previous', previous_period, previous)]:
        for field in FIELDS:
            values[field], provenance[prefix+'__'+field] = select_value(rows, field, end)
            if provenance[prefix+'__'+field] == {'status': 'CONFLICTING_SAME_ACCESSION_FACTS'}:
                provenance[prefix+'__'+field]['conflicting_rows'] = [
                    row for row in rows if row['tag'] in EXTENDED_ALIASES[field] and row['ddate'] == end]
        if values['total_debt'] is None:
            values['total_debt'], parents = resolve_total_debt(values)
            if values['total_debt'] is not None:
                provenance[prefix+'__total_debt'] = {'status': 'DERIVED_FROM_BOUND_SOURCE_ROWS',
                                                    'parents': [prefix+'__'+p for p in parents]}
    capture_path = cache/('capture-'+source_hash+'.json')
    if not capture_path.exists():
        freeze_json(capture_path, {'download_timestamp': utcnow()})
    captured = read_json(capture_path)['download_timestamp']
    producer = NumericProposalProducer(root)
    packet = {'case_id': digest({'cik': cik, 'accession': accession})[:24], 'cik': cik, 'accession': accession,
              'filing_timestamp': accepted, 'prediction_cutoff': accepted, 'schema_hash': digest(producer.schema),
              'extraction_code_hash': file_hash(Path(__file__)), 'preprocessing_hash': digest({'mode': 'ORIGINAL_INSTANCE_US_GAAP_CONSOLIDATED_ANNUAL_NO_BACKFILL'}),
              'reference_distribution_hash': file_hash(root/REFERENCE), 'features': flatten(current, previous, year),
              'sources': [{'sha256': source_hash, 'available_at': accepted, 'filing_timestamp': accepted,
                           'accession': accession, 'cik': cik, 'role': 'INDEX_FILING'}]}
    validate_features(packet, schema_hash=digest(producer.schema), code_hash=file_hash(Path(__file__)))
    return {'packet': packet, 'evidence': {'packet_hash': digest(packet), 'provenance': provenance,
            'source_url': url, 'source_sha256': source_hash, 'download_timestamp': captured,
            'source_mode': 'LIVE_SEC_EXACT_INDEX_ACCESSION', 'index_acceptance_source': clock,
            'precision_resolutions': precision_resolutions,
            'sic': int(submissions.get('sic') or 0), 'retained_accessions': [accession],
            'future_or_other_accession_backfill': False, 'financial_api_latest_values_used': False}}
