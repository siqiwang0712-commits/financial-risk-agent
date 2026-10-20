"""Accession-bound SEC FSDS feature extraction. No outcome table is accepted here."""
from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from finrisk.e4_core import E4_INSTANT_FIELDS, EXTENDED_ALIASES, _comparative_period
from finrisk.metrics import resolve_total_debt

from ..execution.core import (
    digest,
    file_hash,
    read_json,
    require,
    timestamp,
    validate_features,
)
from .producer import FIELDS, NumericProposalProducer, flatten


def accepted_utc(value: str) -> str:
    text = value.strip()
    require(bool(text), 'missing SEC acceptance timestamp')
    if re.fullmatch(r'\d{14}', text):
        result = datetime.strptime(text, '%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('America/New_York'))
    else:
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        # SEC EDGAR acceptance timestamps are Eastern; never reinterpret them as UTC.
        result = result.replace(tzinfo=ZoneInfo('America/New_York'))
        require(result.replace(fold=0).utcoffset() == result.replace(fold=1).utcoffset(),
                'ambiguous SEC acceptance time')
    require(result.replace(fold=0).utcoffset() == result.replace(fold=1).utcoffset(), 'ambiguous acceptance time')
    return result.astimezone(UTC).isoformat()


def tsv(path: Path, member: str):
    with zipfile.ZipFile(path) as archive, archive.open(member) as binary, io.TextIOWrapper(binary, encoding='utf-8-sig') as text:
        yield from csv.DictReader(text, delimiter='\t')


def source_manifest(path: Path) -> dict:
    manifest = read_json(path)
    require(manifest['source_type'] == 'SEC_FSDS', 'FSDS source required; master index alone is not numeric evidence')
    require(manifest['source_url'].startswith('https://www.sec.gov/files/dera/data/financial-statement-data-sets/'),
            'authoritative SEC dataset URL required')
    require(re.fullmatch(r'20\d{2}q[1-4]', manifest['dataset_quarter']) is not None, 'quarter identity required')
    require(manifest['source_url'].endswith('/' + manifest['dataset_quarter'] + '.zip'), 'quarter/source URL mismatch')
    archive = path.parent / manifest['file']
    require(archive.resolve().is_relative_to(path.parent.resolve()) and not archive.is_symlink(), 'source archive path escape')
    require(file_hash(archive) == manifest['sha256'], 'raw SEC source hash mismatch')
    timestamp(manifest['download_timestamp'])
    with zipfile.ZipFile(archive) as z:
        require({'sub.txt', 'num.txt'} <= set(z.namelist()), 'SEC source tables missing')
    return manifest | {'archive_path': str(archive.resolve())}


def eligible_universe(manifests: list[Path], *, start: str, end: str, as_of: str) -> dict:
    cutoff = timestamp(as_of)
    accepted = []
    exclusions = []
    sources = []
    for path in manifests:
        source = source_manifest(path)
        sources.append({k: v for k, v in source.items() if k != 'archive_path'})
        for row in tsv(Path(source['archive_path']), 'sub.txt'):
            if row.get('form') != '10-K':
                continue
            cik, accession = str(row['cik']).zfill(10), row['adsh']
            reason = None
            try:
                when = accepted_utc(row['accepted'])
                dt = timestamp(when)
                sic = int(row.get('sic') or 0)
                require(int(row['fy']) <= dt.year, 'future fiscal year')
                require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) is not None, 'invalid accession')
                require(re.fullmatch(r'\d{10}', cik) is not None, 'invalid CIK')
                require(re.fullmatch(r'\d{8}', row['period']) is not None, 'invalid reporting period')
                require(row['period'] <= dt.strftime('%Y%m%d'), 'post-cutoff reporting period')
                end_point = dt.replace(year=dt.year+1) if not (dt.month == 2 and dt.day == 29) else dt.replace(year=dt.year+1, day=28)
                if not start <= when[:10] <= end:
                    reason = 'OUTSIDE_FROZEN_WINDOW'
                elif 6000 <= sic <= 6999 or sic == 0:
                    reason = 'NONINDUSTRIAL_OR_UNKNOWN_SIC'
                elif end_point > cutoff:
                    reason = 'TWELVE_MONTH_HORIZON_NOT_ELAPSED'
                elif str(row.get('filed', '')) > dt.astimezone(ZoneInfo('America/New_York')).strftime('%Y%m%d'):
                    reason = 'PUBLIC_AVAILABILITY_AFTER_ACCEPTANCE_UNRESOLVED'
            except (ValueError, KeyError) as exc:
                reason = 'INVALID_SUBMISSION_METADATA:' + str(exc)
            if reason:
                exclusions.append({'cik': cik, 'accession': accession, 'reason': reason})
                continue
            accepted.append({'cik': cik, 'accession': accession, 'sic': sic,
                             'fiscal_year': int(row['fy']), 'period': row['period'], 'form': row['form'],
                             'filed': row['filed'], 'accepted': when,
                             'dataset_quarter': source['dataset_quarter'], 'source_hash': source['sha256'],
                             'source_manifest_hash': file_hash(path)})
    # Original first 10-K in the candidate window; no outcome information used.
    by_cik = {}
    for row in sorted(accepted, key=lambda x: (x['accepted'], x['accession'])):
        if row['cik'] in by_cik:
            exclusions.append({'cik': row['cik'], 'accession': row['accession'], 'reason': 'LATER_INDEX_CASE_SAME_COMPANY'})
        else:
            by_cik[row['cik']] = row
    return {'schema_version': 1, 'window': [start, end], 'as_of': as_of,
            'sources': sources, 'candidates': sorted(by_cik.values(), key=lambda x: x['cik']),
            'exclusions': exclusions, 'outcome_values_used': False,
            'outcome_observability': 'REQUIRES_SEPARATE_AUTHORITATIVE_AVAILABILITY_ATTESTATION_BEFORE_COHORT_FREEZE'}


def select_value(rows: list[dict], field: str, period: str | None):
    if period is None:
        return None, None
    aliases = EXTENDED_ALIASES[field]
    allowed_unit = 'shares' if field == 'shares_outstanding' else 'USD'
    candidates = []
    for row in rows:
        if (row.get('tag') not in aliases or row.get('ddate') != period or row.get('uom') != allowed_unit
                or row.get('coreg', '').strip() or row.get('segments', '').strip()):
            continue
        if row.get('qtrs') not in ({'0'} if field in E4_INSTANT_FIELDS else {'4'}):
            continue
        try:
            value = float(row['value'])
        except (ValueError, TypeError):
            continue
        if math.isfinite(value):
            candidates.append((aliases.index(row['tag']), value, row))
    if not candidates:
        return None, None
    rank = min(c[0] for c in candidates)
    best = [c for c in candidates if c[0] == rank]
    if len({c[1] for c in best}) != 1:
        return None, {'status': 'CONFLICTING_SAME_ACCESSION_FACTS'}
    _, value, row = min(best, key=lambda c: digest(c[2]))
    return value, {'status': 'SOURCE_ROW_BOUND', 'row': row, 'row_hash': digest(row)}


def extract_packets(root: Path, cohort: list[dict], manifests: list[Path], *, reference_hash: str) -> list[dict]:
    producer = NumericProposalProducer(root)
    by_source = {m['sha256']: m for m in map(source_manifest, manifests)}
    grouped = defaultdict(list)
    for case in cohort:
        grouped[case['source_hash']].append(case)
    output = []
    for source_hash, cases in grouped.items():
        require(source_hash in by_source, 'cohort source is missing')
        wanted = {c['accession'] for c in cases}
        source = by_source[source_hash]
        nums = defaultdict(list)
        for row in tsv(Path(source['archive_path']), 'num.txt'):
            if row.get('adsh') in wanted:
                nums[row['adsh']].append(row)
        sub = {r['adsh']: r for r in tsv(Path(source['archive_path']), 'sub.txt') if r['adsh'] in wanted}
        for case in cases:
            require(str(sub[case['accession']]['cik']).zfill(10) == case['cik'], 'cross-CIK accession substitution')
            require(accepted_utc(sub[case['accession']]['accepted']) == case['accepted'], 'acceptance metadata drift')
            rows = nums[case['accession']]
            prior_period = _comparative_period(rows, case['period'])
            current, previous, provenance = {}, {}, {}
            for prefix, period, values in [('current', case['period'], current), ('previous', prior_period, previous)]:
                for field in FIELDS:
                    value, origin = select_value(rows, field, period)
                    values[field] = value
                    provenance[f'{prefix}__{field}'] = origin
                if values.get('total_debt') is None:
                    values['total_debt'], parents = resolve_total_debt(values)
                    if values['total_debt'] is not None:
                        provenance[f'{prefix}__total_debt'] = {'status': 'DERIVED_FROM_BOUND_SOURCE_ROWS',
                                                             'parents': [f'{prefix}__{key}' for key in parents]}
            packet = {'case_id': digest({'cik': case['cik'], 'accession': case['accession']})[:24],
                      'cik': case['cik'], 'accession': case['accession'], 'filing_timestamp': case['accepted'],
                      'prediction_cutoff': case['accepted'], 'schema_hash': digest(producer.schema),
                      'extraction_code_hash': file_hash(Path(__file__)), 'preprocessing_hash': digest({'method': 'NO_RAW_IMPUTATION'}),
                      'reference_distribution_hash': reference_hash,
                      'sources': [{'sha256': source_hash, 'available_at': case['accepted'],
                                   'filing_timestamp': case['accepted'], 'accession': case['accession'],
                                   'cik': case['cik'], 'role': 'INDEX_FILING'}],
                      'features': flatten(current, previous, case['fiscal_year'])}
            validate_features(packet, schema_hash=digest(producer.schema), code_hash=file_hash(Path(__file__)))
            evidence = {'packet_hash': digest(packet), 'provenance': provenance,
                        'source_url': source['source_url'], 'source_sha256': source_hash,
                        'download_timestamp': source['download_timestamp'], 'dataset_quarter': source['dataset_quarter'],
                        'availability_semantics': 'INDEX_FILING_ACCEPTANCE_NOT_FSDS_DOWNLOAD_DATE',
                        'form': '10-K', 'period': case['period'], 'filed': case['filed'],
                        'index_accession': case['accession'], 'supporting_accessions': [],
                        'known_limitation': 'Accession reconstruction is retrospective; the downloaded FSDS archive itself was not available at the prediction cutoff.'}
            output.append({'packet': packet, 'evidence': evidence})
    return output
