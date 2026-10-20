"""Accession-bound adapter for the existing forward deterioration endpoint.

Called only after the execution journal unlock. General CIK identifiers replace
historical ticker registries; source acceptance uses SEC Eastern time. Financial
conditions and the missing-label rule are the released deterministic algorithm.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from finrisk.sec_bulk import add_twelve_months, build_deterioration_labels

from ..execution.core import digest, require, timestamp, verified_label
from .sources import accepted_utc, select_value, source_manifest, tsv


def duration(rows, field, period, qtrs):
    from finrisk.e4_core import EXTENDED_ALIASES
    candidates = [r for r in rows if r.get('ddate') == period and r.get('tag') in EXTENDED_ALIASES[field]
                  and r.get('uom') == 'USD' and r.get('qtrs') == str(qtrs)
                  and not r.get('coreg', '').strip() and not r.get('segments', '').strip()]
    # Reuse the conflict-aware annual selector on a local normalized copy only.
    # Original duration is retained in returned provenance and never in features.
    normalized = [r | {'qtrs': '4'} for r in candidates]
    value, provenance = select_value(normalized, field, period)
    return value, {'duration_quarters': qtrs, 'source_rows_hash': digest(candidates), 'selection': provenance}


def extract(frozen_bundles: list[dict], manifests: list[Path], *, as_of: str):
    cases = {b['packet']['cik']: b for b in frozen_bundles}
    require(len(cases) == len(frozen_bundles), 'one company per endpoint')
    source_records = [source_manifest(p) for p in manifests]
    submissions, numbers = {}, defaultdict(list)
    for source in source_records:
        wanted = set()
        for row in tsv(Path(source['archive_path']), 'sub.txt'):
            cik = str(row.get('cik', '')).zfill(10)
            if cik not in cases or row.get('form') not in {'10-K', '10-Q'}:
                continue
            packet = cases[cik]['packet']
            cutoff = timestamp(packet['prediction_cutoff'])
            horizon = add_twelve_months(cutoff)
            require(horizon <= timestamp(as_of), 'endpoint window not mature')
            accepted = accepted_utc(row['accepted'])
            if not cutoff < timestamp(accepted) <= horizon:
                continue
            record = row | {'cik': cik, 'available_at': accepted, 'source_hash': source['sha256']}
            adsh = row['adsh']
            require(adsh not in submissions or submissions[adsh] == record, 'conflicting outcome accession')
            submissions[adsh] = record
            wanted.add(adsh)
        for row in tsv(Path(source['archive_path']), 'num.txt'):
            if row.get('adsh') in wanted:
                numbers[row['adsh']].append(row)
    observations, annual, reports = [], [], []
    for cik, bundle in cases.items():
        packet = bundle['packet']
        cutoff = timestamp(packet['prediction_cutoff'])
        observations.append({'ticker': cik, 'observation_id': packet['case_id'],
                             'fiscal_year': packet['features']['fiscal_year'],
                             'information_cutoff': cutoff.isoformat(),
                             'outcome_window_end': add_twelve_months(cutoff).isoformat(),
                             'facts': {k.removeprefix('current__'): v for k, v in packet['features'].items()
                                       if k.startswith('current__')}})
        previous_ytd = {}
        for filing in sorted((r for r in submissions.values() if r['cik'] == cik), key=lambda r: (r['available_at'], r['adsh'])):
            rows, period = numbers[filing['adsh']], filing['period']
            year = int(filing['fy'])
            if filing['form'] == '10-K':
                facts = {field: select_value(rows, field, period)[0] for field in
                         ('revenue', 'net_income', 'operating_cash_flow', 'total_assets', 'total_debt',
                          'short_term_debt', 'long_term_debt')}
                if facts['total_debt'] is None and facts['short_term_debt'] is not None and facts['long_term_debt'] is not None:
                    facts['total_debt'] = facts['short_term_debt']+facts['long_term_debt']
                annual.append({'ticker': cik, 'observation_id': filing['adsh'], 'fiscal_year': year, 'source_available_time': filing['available_at'],
                               'facts': facts, 'accession': filing['adsh'], 'source_hash': filing['source_hash']})
            quarter = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'FY': 4}.get(filing.get('fp'))
            values, proof = {}, {}
            for field in ('operating_cash_flow', 'capital_expenditure'):
                value, origin = duration(rows, field, period, quarter) if quarter else (None, None)
                standalone = value
                key = (year, field)
                if quarter in {2, 3}:
                    prior = previous_ytd.get(key)
                    standalone = None if value is None or not prior or prior[0] != quarter-1 else value-prior[1]
                if value is not None:
                    previous_ytd[key] = (quarter, value)
                values[field], proof[field] = standalone, origin
            ocf, capex = values['operating_cash_flow'], values['capital_expenditure']
            reports.append({'ticker': cik, 'accession': filing['adsh'], 'source_available_time': filing['available_at'],
                            'period': period, 'form': filing['form'], 'source_hash': filing['source_hash'],
                            'free_cash_flow': None if ocf is None or capex is None else ocf-abs(capex),
                            'standalone_duration_provenance': proof})
    raw = build_deterioration_labels(observations, reports, annual, as_of)
    by_id = {r['observation_id']: r for r in raw}
    result = []
    for observation in observations:
        value = by_id[observation['observation_id']]
        outcome = {'status': {'REQUIRES_HUMAN_REVIEW': 'REQUIRES_REVIEW'}.get(value['label_status'], value['label_status']),
                   'label': value['financial_deterioration_12m'], 'raw_endpoint': value,
                   'case_id': observation['observation_id'], 'cik': observation['ticker']}
        verified_label(outcome)
        result.append(outcome)
    return {'outcomes': result, 'source_manifests': [{k: v for k, v in s.items() if k != 'archive_path'} for s in source_records],
            'annual_records': annual, 'reported_fcf_periods': reports,
            'endpoint': 'deterministic_forward_outcome_rule_v1_WITH_ACCESSION_TIMING_AND_STANDALONE_FCF_ADAPTER',
            'unadjudicated_review_cases_remain_nonverified': True}
