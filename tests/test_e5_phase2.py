"""Phase-II safeguards; no synthetic fixture is empirical E5 evidence."""
from copy import deepcopy

import pytest

from research.e5.execution.core import GateError, validate_features

H = 'a' * 64


def packet():
    return {'case_id': 'synthetic-case', 'cik': '0000000001', 'accession': '0000009999-25-000001',
            'filing_timestamp': '2025-01-01T00:00:00Z', 'prediction_cutoff': '2025-01-01T00:00:00Z',
            'schema_hash': H, 'extraction_code_hash': H, 'preprocessing_hash': H,
            'reference_distribution_hash': H, 'features': {'current_ratio': 1.},
            'sources': [{'sha256': H, 'available_at': '2025-01-01T00:00:00Z',
                         'filing_timestamp': '2025-01-01T00:00:00Z', 'accession': '0000009999-25-000001',
                         'cik': '0000000001', 'role': 'INDEX_FILING'}]}


@pytest.mark.parametrize(('key', 'value'), [('accession', '0000009999-25-000002'),
                                           ('cik', '0000000002'), ('role', 'LATEST_COMPANYFACTS'),
                                           ('role', 'PRIOR_PERIOD_FILING')])
def test_source_identity_substitution_is_rejected(key, value):
    p = packet()
    p['sources'][0][key] = value
    with pytest.raises(GateError):
        validate_features(p, schema_hash=H, code_hash=H)


def test_filing_agent_accession_prefix_need_not_equal_issuer_cik():
    validate_features(packet(), schema_hash=H, code_hash=H)


def test_cross_case_accession_source_cannot_be_reused():
    a = packet()
    b = deepcopy(a)
    b['accession'] = '0000009999-25-000003'
    with pytest.raises(GateError):
        validate_features(b, schema_hash=H, code_hash=H)


def test_numeric_producer_is_before_verification_and_provider_calls(monkeypatch):
    from pathlib import Path

    from research.e5.phase2.producer import NumericProposalProducer, flatten
    root = Path(__file__).resolve().parents[1]
    producer = NumericProposalProducer(root)
    def forbidden(*args, **kwargs):
        raise AssertionError('downstream verification/provider entered the raw producer')
    monkeypatch.setattr('finrisk.assurance.engine.AssuranceEngine.evaluate', forbidden)
    monkeypatch.setattr('finrisk.agent.verification.verify_conclusions', forbidden)
    monkeypatch.setattr('finrisk.agent.review.three_role_review', forbidden)
    result = producer({'features': flatten({'cash': 1., 'revenue': 2.}, {}, 2024)})
    assert result['raw_structured_output']['evidence_verification_performed'] is False
    assert result['raw_structured_output']['assurance_performed'] is False
    assert producer.identity['generation_parameters']['provider_calls'] == 0


def test_numeric_producer_rejects_evaluation_label_input():
    from pathlib import Path

    from research.e5.phase2.producer import NumericProposalProducer, flatten
    producer = NumericProposalProducer(Path(__file__).resolve().parents[1])
    features = flatten({}, {}, 2024) | {'evaluation_label': 0}
    with pytest.raises(GateError):
        producer({'features': features})


@pytest.mark.parametrize('boundary', [-.05, .01, .3])
def test_constrained_null_is_likelihood_maximum(boundary):
    import numpy as np

    from research.e5.phase2.inference import constrained_probabilities
    values = np.array([-1]*8 + [0]*71 + [1]*21)
    p = constrained_probabilities(values, boundary)
    assert p @ np.array([-1, 0, 1]) == pytest.approx(boundary)
    counts = np.array([8, 71, 21])
    optimum = counts @ np.log(p)
    for s in np.linspace(abs(boundary)+1e-6, 1-1e-6, 1000):
        candidate = np.array([(s-boundary)/2, 1-s, (s+boundary)/2])
        assert counts @ np.log(candidate) <= optimum+1e-8


def test_canonical_analysis_rejects_legacy_identity_and_missing_qualification():
    from pathlib import Path

    from research.e5.phase2.inference import analyze, specification, validate_spec
    root = Path(__file__).resolve().parents[1]
    spec = specification(root)
    with pytest.raises(GateError):
        validate_spec(root, spec | {'engine_id': 'V1'})
    with pytest.raises(GateError):
        analyze(root, [], spec, {'analysis_identity': 'wrong', 'status': 'PASSED'})


def test_sec_acceptance_uses_eastern_and_rejects_ambiguous_time():
    from research.e5.phase2.sources import accepted_utc
    assert accepted_utc('2025-01-15 16:30:00') == '2025-01-15T21:30:00+00:00'
    assert accepted_utc('20250715163000') == '2025-07-15T20:30:00+00:00'
    with pytest.raises(GateError):
        accepted_utc('2025-11-02 01:30:00')


def test_nested_coverage_null_does_not_inherit_v2_false_rejection():
    import numpy as np

    from research.e5.phase2.inference import paired_null_pvalue
    # At N=100, two observed lost automated decisions are insufficient to reject
    # the null loss of five percent; V2's centered support lattice was too small.
    values = np.array([-1]*2 + [0]*98)
    assert paired_null_pvalue(values, -.05, draws=20000, seed=1) > .05


def test_study_bands_and_policy_preserve_production_vetoes():
    from dataclasses import asdict
    from pathlib import Path

    from finrisk.assurance.policy import AssurancePolicy

    from research.e5.phase2.calibration import apply
    from research.e5.phase2.study import CalibratedStudyProducer, band
    producer = CalibratedStudyProducer(Path(__file__).resolve().parents[1])
    before, after = asdict(AssurancePolicy()), asdict(producer.policy)
    for key in before.keys() - {'version', 'maturity'}:
        assert before[key] == after[key]
    for j in range(1001):
        points = j/10
        decision = ('FLAG' if points >= producer.fusion_policy['flag_score'] else
                    'REVIEW' if points >= producer.fusion_policy['review_score'] else 'PASS')
        assert decision == band(apply(producer.artifact, points/100))


def test_real_source_reextraction_fanout_and_certificate(tmp_path, monkeypatch):
    import csv
    import io
    import zipfile
    from pathlib import Path

    from finrisk.e4_core import E4_INSTANT_FIELDS, EXTENDED_ALIASES

    from research.e5.execution.core import (
        FrozenProposalProducer,
        digest,
        file_hash,
        freeze_json,
        verify_certificate_binding,
    )
    from research.e5.phase2.sources import accepted_utc, extract_packets
    from research.e5.phase2.study import REFERENCE, CalibratedStudyProducer, fanout
    root = Path(__file__).resolve().parents[1]
    cik, adsh = '0000000001', '0000000001-25-000001'
    sub = {'adsh': adsh, 'cik': '1', 'accepted': '2025-02-01 12:00:00',
           'period': '20241231', 'fy': '2024', 'form': '10-K', 'filed': '20250201'}
    nums = []
    values = {'cash': 10, 'revenue': 100, 'current_assets': 30, 'current_liabilities': 40,
              'total_assets': 200, 'total_liabilities': 100, 'net_income': -10,
              'operating_cash_flow': 20, 'capital_expenditure': 5, 'gross_profit': 30,
              'operating_income': 10, 'shareholder_equity': 100, 'interest_expense': 5,
              'inventory': 8, 'total_debt': 70}
    for period in ('20241231', '20231231'):
        for field, value in values.items():
            nums.append({'adsh': adsh, 'tag': EXTENDED_ALIASES[field][0], 'ddate': period,
                         'uom': 'USD', 'qtrs': '0' if field in E4_INSTANT_FIELDS else '4',
                         'value': str(value), 'coreg': '', 'segments': ''})
    def table(rows):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
        return stream.getvalue()
    archive = tmp_path/'2025q1.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('sub.txt', table([sub]))
        z.writestr('num.txt', table(nums))
    manifest = tmp_path/'2025q1.manifest.json'
    freeze_json(manifest, {'source_type': 'SEC_FSDS', 'dataset_quarter': '2025q1', 'file': archive.name,
                          'sha256': file_hash(archive), 'download_timestamp': '2026-10-19T00:00:00Z',
                          'source_url': 'https://www.sec.gov/files/dera/data/financial-statement-data-sets/2025q1.zip'})
    case = {'cik': cik, 'accession': adsh, 'accepted': accepted_utc(sub['accepted']),
            'source_hash': file_hash(archive), 'period': '20241231', 'fiscal_year': 2024, 'filed': '20250201'}
    bundle = extract_packets(root, [case], [manifest], reference_hash=file_hash(root/REFERENCE))[0]
    producer = CalibratedStudyProducer(root)
    proposal = FrozenProposalProducer(producer.identity, producer).run(bundle['packet'], tmp_path/'proposal.json')
    def forbidden(*args, **kwargs):
        raise AssertionError('proposal regenerated downstream')
    monkeypatch.setattr(producer, 'raw', forbidden)
    result = fanout(producer, proposal, bundle, case=case, manifests=[manifest])
    assert result['proposal_hash'] == proposal['proposal_hash']
    assert result['certificate']['policy_hash'] == producer.policy.policy_hash
    verify_certificate_binding(result['certificate'], proposal_hash=proposal['proposal_hash'], policy=producer.policy)
    broken = deepcopy(result['certificate'])
    broken['component_versions']['proposal_hash'] = digest('different')
    with pytest.raises(GateError):
        verify_certificate_binding(broken, proposal_hash=proposal['proposal_hash'], policy=producer.policy)
    mutated = deepcopy(bundle)
    mutated['packet']['features']['current__cash'] = 999
    with pytest.raises(GateError):
        fanout(producer, proposal, mutated, case=case, manifests=[manifest])


def test_c01_does_not_accept_an_approximate_list(tmp_path):
    from pathlib import Path

    from research.e5.phase2.cohort import prove_exclusions
    p = tmp_path/'previous.json'
    p.write_text('["0000000001"]')
    with pytest.raises(GateError):
        prove_exclusions(Path(__file__).resolve().parents[1], p)


def test_conflicting_facts_are_unavailable_and_segments_are_not_consolidated():
    from research.e5.phase2.sources import select_value
    base = {'tag': 'Assets', 'ddate': '20241231', 'uom': 'USD', 'qtrs': '0', 'value': '10'}
    value, _ = select_value([base | {'segments': 'one segment'}], 'total_assets', '20241231')
    assert value is None
    value, proof = select_value([base, base | {'value': '20'}], 'total_assets', '20241231')
    assert value is None and proof['status'] == 'CONFLICTING_SAME_ACCESSION_FACTS'


@pytest.mark.parametrize(('future_values', 'expected'), [
    ({'revenue': 70, 'net_income': -5, 'operating_cash_flow': 15, 'total_assets': 100, 'total_debt': 10}, 1),
    ({'revenue': 100, 'net_income': 5, 'operating_cash_flow': 15, 'total_assets': 100, 'total_debt': 10}, 0),
])
def test_endpoint_uses_bound_future_filing_without_score_input(tmp_path, future_values, expected):
    import csv
    import io
    import zipfile

    from finrisk.e4_core import E4_INSTANT_FIELDS, EXTENDED_ALIASES

    from research.e5.execution.core import file_hash, freeze_json
    from research.e5.phase2.endpoint import extract
    def table(rows):
        f = io.StringIO()
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
        return f.getvalue()
    adsh = '0000000001-25-000001'
    sub = {'adsh': adsh, 'cik': '1', 'form': '10-K', 'period': '20241231',
           'fy': '2024', 'fp': 'FY', 'accepted': '2025-02-01 12:00:00'}
    nums = [{'adsh': adsh, 'tag': EXTENDED_ALIASES[k][0], 'ddate': '20241231', 'uom': 'USD',
             'qtrs': '0' if k in E4_INSTANT_FIELDS else '4', 'value': str(v)} for k, v in future_values.items()]
    archive = tmp_path/'2025q1.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('sub.txt', table([sub]))
        z.writestr('num.txt', table(nums))
    manifest = tmp_path/'manifest.json'
    freeze_json(manifest, {'source_type': 'SEC_FSDS', 'dataset_quarter': '2025q1', 'file': archive.name,
                          'sha256': file_hash(archive), 'download_timestamp': '2026-10-19T00:00:00Z',
                          'source_url': 'https://www.sec.gov/files/dera/data/financial-statement-data-sets/2025q1.zip'})
    features = {'fiscal_year': 2023} | {'current__'+k: v for k, v in
               {'revenue': 100, 'net_income': 5, 'operating_cash_flow': 15, 'total_assets': 100, 'total_debt': 10}.items()}
    bundle = {'packet': {'case_id': 'synthetic', 'cik': '0000000001',
                         'prediction_cutoff': '2024-08-01T00:00:00Z', 'features': features}}
    result = extract([bundle], [manifest], as_of='2026-10-19T00:00:00Z')
    assert result['outcomes'][0]['status'] == 'VERIFIED'
    assert result['outcomes'][0]['label'] == expected
    assert result['annual_records'][0]['source_available_time'] == '2025-02-01T17:00:00+00:00'
