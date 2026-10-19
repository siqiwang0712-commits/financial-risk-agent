"""Adversarial execution-boundary tests use synthetic fixtures, never E5 cases."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import bootstrap

from research.e5.execution.core import (
    FrozenProposalProducer,
    GateError,
    digest,
    disjoint,
    exact_previous_270,
    file_hash,
    freeze_json,
    outcome_barrier,
    shared_proposals,
    validate_features,
    validate_proposal,
    verified_label,
    verify_files,
)
from research.e5.execution.development import utility
from research.e5.execution.inference import (
    analyze,
    company_matrix,
    component,
    holm,
    iut,
    paired_statistics,
)
from research.e5.execution.qualification import null_distribution

ROOT = Path(__file__).resolve().parents[1]
H = 'a' * 64


def feature():
    return {'case_id': 'engineering-only', 'cik': '0000000001',
            'accession': '0000000001-25-000001', 'filing_timestamp': '2025-01-01T00:00:00Z',
            'prediction_cutoff': '2025-01-01T00:00:00Z', 'schema_hash': H,
            'extraction_code_hash': H, 'preprocessing_hash': H, 'reference_distribution_hash': H,
            'features': {'current_ratio': 1.},
            'sources': [{'sha256': H, 'available_at': '2025-01-01T00:00:00Z',
                         'filing_timestamp': '2025-01-01T00:00:00Z', 'accession': '0000000001-25-000001'}]}


def producer_identity():
    return {'version': 'ENGINEERING_ONLY', 'code_hash': H, 'model': 'synthetic-test-callable',
            'prompt_hash': None, 'tool_definition_hash': None, 'generation_parameters': {},
            'score_semantics': 'SYNTHETIC_TEST_SCORE'}


def proposal(tmp_path):
    producer = FrozenProposalProducer(producer_identity(), lambda _: {
        'raw_structured_output': {'fixture': True}, 'normalized_risk_score': .8, 'proposed_decision': 'FLAG'})
    return producer.run(feature(), tmp_path / 'proposal.json')


@pytest.mark.parametrize('field', ['available_at', 'filing_timestamp'])
def test_source_one_second_leakage(tmp_path, field):
    packet = feature()
    packet['sources'][0][field] = '2025-01-01T00:00:01Z'
    with pytest.raises(GateError):
        validate_features(packet, schema_hash=H, code_hash=H)


def test_future_index_filing():
    packet = feature()
    packet['filing_timestamp'] = '2025-01-01T00:00:01Z'
    with pytest.raises(GateError):
        validate_features(packet, schema_hash=H, code_hash=H)


@pytest.mark.parametrize('key', ['schema_hash', 'extraction_code_hash'])
def test_feature_identity_drift(key):
    packet = feature()
    packet[key] = 'b' * 64
    with pytest.raises(GateError):
        validate_features(packet, schema_hash=H, code_hash=H)


def test_valid_feature_and_no_outcome_fields():
    packet = feature()
    assert validate_features(packet, schema_hash=H, code_hash=H) == digest(packet)
    packet['outcome'] = 0
    with pytest.raises(GateError):
        validate_features(packet, schema_hash=H, code_hash=H)


def test_outcome_before_prediction_freeze(tmp_path):
    with pytest.raises(GateError):
        outcome_barrier(tmp_path, {}, outcome_paths=[], prediction_stage=False)


def test_outcome_mount_too_early(tmp_path):
    (tmp_path / 'outcomes').mkdir()
    with pytest.raises(GateError):
        outcome_barrier(tmp_path, {}, outcome_paths=[tmp_path / 'outcomes'], prediction_stage=True)


def test_mutated_proposal(tmp_path):
    packet = proposal(tmp_path)
    packet['normalized_risk_score'] = .2
    with pytest.raises(GateError):
        validate_proposal(packet, producer_hash=digest(producer_identity()))


@pytest.mark.parametrize('arm', ['S3', 'S4'])
def test_regenerated_proposal_fails(tmp_path, arm):
    packet = proposal(tmp_path)
    proposals = {name: deepcopy(packet) for name in ['S2', 'S3', 'S4']}
    proposals[arm]['generation_timestamp'] = '2026-10-01T00:00:00Z'
    proposals[arm]['proposal_hash'] = digest({k: v for k, v in proposals[arm].items() if k != 'proposal_hash'})
    with pytest.raises(GateError):
        shared_proposals(proposals, digest(producer_identity()))


def test_model_identity_change(tmp_path):
    packet = proposal(tmp_path)
    packet['producer_identity']['model'] = 'different-model'
    packet['proposal_hash'] = digest({k: v for k, v in packet.items() if k != 'proposal_hash'})
    with pytest.raises(GateError):
        validate_proposal(packet, producer_hash=digest(producer_identity()))


def test_producer_once_and_read_only_resume(tmp_path):
    calls = []
    def produce(_):
        calls.append(1)
        return {'raw_structured_output': {}, 'normalized_risk_score': .8, 'proposed_decision': 'FLAG'}
    p = FrozenProposalProducer(producer_identity(), produce)
    first = p.run(feature(), tmp_path / 'p.json')
    stat = (tmp_path / 'p.json').stat()
    assert p.run(feature(), tmp_path / 'p.json') == first
    assert calls == [1]
    assert (tmp_path / 'p.json').stat().st_mtime_ns == stat.st_mtime_ns


def test_historical_overlap():
    with pytest.raises(GateError):
        disjoint(['0000000001'], {'0000000001'})


def test_duplicate_company():
    with pytest.raises(GateError):
        disjoint(['0000000001', '0000000001'], set())


def test_invalid_c01_cannot_close(tmp_path):
    p = tmp_path / 'previous.json'
    freeze_json(p, [str(i).zfill(10) for i in range(270)])
    with pytest.raises(GateError):
        exact_previous_270(p)


def test_evaluation_cannot_be_supplied_to_utility():
    with pytest.raises(TypeError):
        utility(ROOT, evaluation_labels=[0, 1])


@pytest.mark.parametrize('name', ['policy', 'threshold', 'code', 'model'])
def test_frozen_identity_mutations(tmp_path, name):
    p = tmp_path / f'{name}.json'
    freeze_json(p, {name: 'original'})
    manifest = {p.name: file_hash(p)}
    p.write_text('{}')
    with pytest.raises(GateError):
        verify_files(tmp_path, manifest)


def test_immutable_rerun_and_overwrite(tmp_path):
    p = tmp_path / 'freeze.json'
    freeze_json(p, {'a': 1})
    before = p.stat().st_mtime_ns
    freeze_json(p, {'a': 1})
    assert p.stat().st_mtime_ns == before
    with pytest.raises(GateError):
        freeze_json(p, {'a': 2})


@pytest.mark.parametrize('label', [None, False, 2])
def test_verified_needs_binary_label(label):
    with pytest.raises(GateError):
        verified_label({'status': 'VERIFIED', 'label': label})


@pytest.mark.parametrize('status', ['MISSING', 'INSUFFICIENT_DATA', 'REQUIRES_REVIEW'])
def test_nonverified_cannot_be_negative(status):
    assert verified_label({'status': status, 'label': None}) is None
    with pytest.raises(GateError):
        verified_label({'status': status, 'label': 0})


def test_holm_trusted_fixtures():
    assert holm([.01, .04]) == [{'adjusted_p': .02, 'reject': True}, {'adjusted_p': .04, 'reject': True}]
    assert holm([.03, .04]) == [{'adjusted_p': .06, 'reject': False}, {'adjusted_p': .06, 'reject': False}]
    assert holm([.04, .01]) == [{'adjusted_p': .04, 'reject': True}, {'adjusted_p': .02, 'reject': True}]


def test_iut_maximum_and_undefined():
    assert iut([.01, .03, .02]) == .03
    assert iut([.01, None, .02]) is None


def test_fixed_seed_and_pair_preservation():
    matrix = np.array([[1, a, -a, a] for a in [0, 1, 0, 1, 0]], dtype=float)
    a = paired_statistics(matrix, draws=2000)
    b = paired_statistics(matrix, draws=2000)
    assert all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))
    assert np.allclose(a[1][:, 0], -a[1][:, 1])
    assert np.allclose(a[1][:, 0], a[1][:, 2])


def test_bca_agrees_with_scipy_on_same_resamples():
    data = np.array([-.8, -.2, .1, .4, .6, .8, 1.3, 1.9])
    res = bootstrap((data,), np.mean, n_resamples=20000, method='BCa', rng=np.random.default_rng(77))
    jack = np.array([np.delete(data, i).mean() for i in range(len(data))])
    result = component(data.mean(), res.bootstrap_distribution, jack, 0.)
    assert result['ci95'] == pytest.approx([res.confidence_interval.low, res.confidence_interval.high], abs=.02)


def test_null_centering_and_plus_one():
    boot = np.array([.1, .2, .3, .4])
    jack = np.array([.1, .2, .3, .4])
    result = component(.25, boot, jack, .2)
    assert result['p'] == pytest.approx(3 / 5)


def test_degenerate_not_estimable():
    result = component(1., np.ones(200), np.ones(10), .5)
    assert result['status'] == 'NOT_ESTIMABLE' and result['p'] is None


def test_missingness_denominators():
    rows = []
    for i in range(4):
        arms = {name: {'automated': name == 'S1', 'decision': 'PASS' if name == 'S1' else 'REVIEW'}
                for name in ['S0', 'S1', 'S2', 'S3', 'S4']}
        outcome = {'status': 'VERIFIED', 'label': 1} if i == 0 else {'status': 'MISSING', 'label': None}
        rows.append({'cik': str(i), 'outcome': outcome, 'arms': arms})
    matrix = company_matrix(rows, 'S1')
    estimates, _, _ = paired_statistics(matrix, draws=100)
    assert estimates.tolist() == [1., -1., 0.]
    result = analyze(rows, delta=.01, margin=.05, floor=.6, draws=100)
    assert result['comparisons']['P1']['verified_n'] == 1
    assert result['comparisons']['P1']['result'] == 'NOT_ESTIMABLE'


@pytest.mark.parametrize('name', ['global_null', 'error_boundary', 'coverage_boundary', 'absolute_boundary', 'mixed_boundary'])
def test_null_simulation_exact_boundaries(name):
    patterns, probabilities, expected = null_distribution(name, 200, .01, .05, .6, .25)
    assert probabilities.sum() == pytest.approx(1.)
    assert np.all(np.abs(patterns[:, 1]) <= patterns[:, 0])
    if name == 'error_boundary':
        assert expected[0] == pytest.approx(.01)
    if name == 'coverage_boundary':
        assert expected[1] == pytest.approx(-.05)
    if name == 'absolute_boundary':
        assert expected[2] == pytest.approx(.6)


def test_incomplete_generation_does_not_silently_repeat(tmp_path):
    calls = []
    def fail(_):
        calls.append(1)
        raise RuntimeError('fixture provider failure')
    p = FrozenProposalProducer(producer_identity(), fail)
    with pytest.raises(RuntimeError):
        p.run(feature(), tmp_path / 'p.json')
    with pytest.raises(GateError):
        p.run(feature(), tmp_path / 'p.json')
    assert calls == [1]


@pytest.mark.parametrize('field', ['proposal_hash', 'policy_hash'])
def test_certificate_binding_rejects_wrong_proposal_and_policy(field):
    from finrisk.assurance.policy import AssurancePolicy

    from research.e5.execution.core import verify_certificate_binding
    policy = AssurancePolicy()
    certificate = {'policy_hash': policy.policy_hash, 'component_versions': {'proposal_hash': H}}
    if field == 'proposal_hash':
        certificate['component_versions']['proposal_hash'] = 'b' * 64
    else:
        certificate['policy_hash'] = 'b' * 64
    with pytest.raises(GateError):
        verify_certificate_binding(certificate, proposal_hash=H, policy=policy)


def test_historical_s0_replay_without_rewriting_nan_fixture():
    from research.e5.execution.qualification import qualify_s0
    path = ROOT / 'research/strong_tabular_reference/artifacts/replay_sample.json'
    before = file_hash(path)
    result = qualify_s0(ROOT)
    assert result['maximum_absolute_difference'] <= result['tolerance']
    assert file_hash(path) == before


def test_corrected_absolute_null_matches_exact_binomial_and_is_reproducible():
    from scipy.stats import binom

    from research.e5.coverage_null_v2 import absolute_pvalue
    exact = binom.sf(330 - 1, 500, .6244444444444444)
    p = absolute_pvalue(330, 500, .6244444444444444)
    assert p == absolute_pvalue(330, 500, .6244444444444444)
    assert p == pytest.approx(exact, abs=.01)
    assert absolute_pvalue(0, 500, .6244444444444444) == 1.
    assert absolute_pvalue(500, 500, .6244444444444444) >= 1/20001


def test_corrected_null_keeps_undefined_primary_undefined():
    from research.e5.coverage_null_v2 import analyze as corrected_analyze
    arms = {name: {'automated': False, 'decision': 'REVIEW'} for name in ['S0', 'S1', 'S2', 'S3', 'S4']}
    rows = [{'cik': str(i), 'outcome': {'status': 'VERIFIED', 'label': i % 2}, 'arms': arms} for i in range(6)]
    result = corrected_analyze(rows, delta=.01, margin=.05, floor=.6, draws=100)
    assert result['comparisons']['P1']['result'] == 'NOT_ESTIMABLE'
    assert result['comparisons']['P2']['iut_p'] is None
