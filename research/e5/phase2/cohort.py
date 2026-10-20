"""Outcome-blind historical exclusion and deterministic temporal enrollment."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from finrisk.sec_bulk import FROZEN_CIKS, add_twelve_months

from ..execution.core import (
    digest,
    exact_previous_270,
    file_hash,
    read_json,
    require,
    timestamp,
)
from .sources import accepted_utc

PIN = '96e60ae91c0ba73342c6e96e42eaa40145f082b1'


def temporal_boundary_assessment(root):
    """A commit date proves existence, not membership in a filing-year universe."""
    authored = subprocess.check_output(['git', 'show', '-s', '--format=%cI', PIN], cwd=root, text=True).strip()
    authored = datetime.fromisoformat(authored).astimezone(UTC).isoformat()
    source = subprocess.check_output(['git', 'show', PIN+':research/e4/protocol/experiment_config.json'], cwd=root)
    return {'historical_artifact_pin': PIN, 'pin_committed_at': authored,
            'pin_config_sha256': __import__('hashlib').sha256(source).hexdigest(),
            'historical_source_universe_proven': False,
            'reason': 'E4 config pins the previous artifact hash, but its own FY2024 filing universe does not establish the parent universe of previous_270.',
            'new_issuer_alternative': 'Requires authoritative proof of issuer/CIK creation and predecessor continuity after this historical pin; an IPO or later filing date alone is insufficient.',
            'earliest_possible_12m_maturity_for_that_alternative': add_twelve_months(timestamp(authored)).isoformat(),
            'exact_recovery_repeated': False, 'C01_closed': False}


def known_historical(root: Path):
    """Conservative union of frozen historical CIK-bearing artifacts, never labels."""
    registry = read_json(root/'research/e5/autonomy/historical_exclusions.json')
    ciks = set(FROZEN_CIKS.values())
    bindings = {}
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() == 'cik' and str(item).isdigit():
                    ciks.add(str(item).zfill(10))
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str) and re.fullmatch(r'\d{10}', value):
            ciks.add(value)
    # Registry artifacts are immutable. Scan only CIK metadata, without reading
    # historical outcomes or refitting any historical model.
    for record in list(registry['historical_sources'].values()) + [registry['strong_reference_2000']]:
        path = root/record['path']
        require(file_hash(path) == record['sha256'], 'historical source registry drift')
        bindings[record['path']] = record['sha256']
        if path.suffix == '.json':
            collect(read_json(path))
    # Exact original E4 input hashes establish this containing source universe;
    # this proof deliberately makes no claim about the unpublished previous_270.
    proof_path = root/'research/e5/phase2/qualification/known-E4-source-superset.json'
    proof = read_json(proof_path)
    parent = root/proof['parent_protocol']
    require(file_hash(parent) == proof['parent_protocol_sha256'], 'E4 parent protocol changed')
    config = read_json(parent)
    union = set()
    archives = set()
    for item in proof['source_archives']:
        m = item['manifest']
        filename = m['dataset_quarter']+'.zip'
        require(m['source_type'] == 'SEC_FSDS' and filename in config['feature_archives']
                and m['sha256'] == config['data_hashes'][filename], 'historical parent source mismatch')
        encoded = (json.dumps(item['original_10k_metadata'], sort_keys=True, separators=(',', ':'))+'\n').encode()
        require(__import__('hashlib').sha256(encoded).hexdigest() == m['submission_metadata_sha256'], 'historical metadata drift')
        archives.add(filename)
        union.update(str(r['cik']).zfill(10) for r in item['original_10k_metadata'])
    require(archives == set(config['feature_archives']) and sorted(union) == proof['ciks']
            and proof['previous_270_containment_proven'] is False, 'incomplete or overclaimed historical source universe')
    ciks |= union
    bindings[str(proof_path.relative_to(root))] = file_hash(proof_path)
    return ciks, bindings


def prove_exclusions(root, previous_path: Path):
    require(previous_path.is_file(), 'C01: exact previous_270 or independently verified parent-universe proof required')
    previous = exact_previous_270(previous_path)
    known, bindings = known_historical(root)
    return known | previous, {'kind': 'EXACT_HISTORICAL_ARTIFACT', 'previous_sha256': file_hash(previous_path),
                              'known_bindings': bindings, 'excluded_cik_hash': digest(sorted(known|previous))}


def from_metadata(root: Path, metadata: list[dict], provenance: dict, *, start: str, end: str, as_of: str):
    """Inspection only; an immutable candidate universe is not a frozen cohort."""
    source = provenance['manifest']
    require(source['source_type'] == 'SEC_FSDS', 'official FSDS metadata required')
    eligible, excluded = [], []
    known, bindings = known_historical(root)
    for row in metadata:
        accession, cik = row['adsh'], str(row['cik']).zfill(10)
        reason = None
        try:
            accepted = accepted_utc(row['accepted'])
            when = timestamp(accepted)
            require(row['form'] == '10-K', 'original 10-K required')
            require(re.fullmatch(r'\d{10}-\d{2}-\d{6}', accession) is not None, 'accession')
            require(re.fullmatch(r'\d{10}', cik) is not None, 'CIK')
            require(row['period'] <= when.strftime('%Y%m%d') and int(row['fy']) <= when.year, 'future period')
            if not start <= accepted[:10] <= end:
                reason = 'OUTSIDE_WINDOW'
            elif not row.get('sic') or 6000 <= int(row['sic']) <= 6999:
                reason = 'NONFINANCIAL_SCOPE'
            elif add_twelve_months(when) > timestamp(as_of):
                reason = '12_MONTH_WINDOW_NOT_ELAPSED'
            elif cik in known:
                reason = 'KNOWN_HISTORICAL_COMPANY'
        except (ValueError, TypeError, KeyError) as exc:
            reason = 'INVALID_SOURCE_METADATA: '+str(exc)
        if reason:
            excluded.append({'cik': cik, 'accession': accession, 'reason': reason})
        else:
            eligible.append({'cik': cik, 'accession': accession, 'accepted': accepted,
                             'period': row['period'], 'fiscal_year': int(row['fy']), 'filed': row['filed'],
                             'sic': int(row['sic']), 'source_hash': source['sha256'],
                             'dataset_quarter': source['dataset_quarter']})
    unique = {}
    for case in sorted(eligible, key=lambda x: (x['accepted'], x['accession'])):
        if case['cik'] in unique:
            excluded.append({'cik': case['cik'], 'accession': case['accession'], 'reason': 'LATER_CASE_SAME_COMPANY'})
        else:
            unique[case['cik']] = case
    return {'status': 'SOURCE_UNIVERSE_INSPECTION_NOT_COHORT_FREEZE', 'window': [start, end],
            'as_of': as_of, 'candidates': list(unique.values()), 'exclusions': excluded,
            'historical_bindings': bindings, 'source_hash': source['sha256'],
            'unresolved': ['C01_HISTORICAL_NONOVERLAP', 'AUTHORITATIVE_OUTCOME_OBSERVABILITY'],
            'outcome_values_used': False}


def select(universe, exclusions: set[str], *, n: int | None, salt: str, availability: dict):
    require(availability['outcome_values_included'] is False, 'availability catalog must contain metadata only')
    available = {r['cik'] for r in availability['companies'] if r['window_fully_observable'] is True}
    rows, rejected = [], []
    for row in universe['candidates']:
        reason = ('HISTORICAL_COMPANY' if row['cik'] in exclusions else
                  'OUTCOME_EVIDENCE_NOT_OBSERVABLE' if row['cik'] not in available else None)
        if reason:
            rejected.append({'cik': row['cik'], 'reason': reason})
        else:
            rows.append(row)
    rows.sort(key=lambda r: digest([salt, r['cik'], r['accession']]))
    require(n is None or type(n) is int and n > 0, 'positive N or largest valid cohort required')
    chosen = rows if n is None else rows[:n]
    require(len(chosen) >= 3 and len({r['cik'] for r in chosen}) == len(chosen), 'insufficient unique eligible companies')
    return {'cases': chosen, 'exclusions': universe['exclusions']+rejected,
            'selection_salt': salt, 'universe_hash': digest(universe),
            'availability_hash': digest(availability), 'historical_exclusion_hash': digest(sorted(exclusions)),
            'underpowered': n is not None and len(chosen)<n}
