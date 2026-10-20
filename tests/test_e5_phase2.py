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
