"""Rehashed content must still describe a possible Assurance runtime result."""
from copy import deepcopy

import pytest
from finrisk.assurance import verify_assurance_payload
from finrisk.enterprise.decision import canonical_hash
from test_assurance_runtime import REFERENCE, calibrated_engine, input_for, path


def rehash(value):
    value['certificate_hash'] = canonical_hash({k: v for k, v in value.items() if k != 'certificate_hash'})
    return value


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(decision_sufficient_evidence={}),
    lambda p: p['decision_sufficient_evidence'].update(baseline_decision='PASS'),
    lambda p: p['decision_sufficient_evidence'].update(evidence_ids=('invented',)),
    lambda p: p['decision_sufficient_evidence'].update(evaluated_subsets=True),
    lambda p: p['decision_sufficient_evidence'].update(evaluated_subsets=10**100),
    lambda p: p['decision_sufficient_evidence'].update(preserves_proposed_decision=False),
    lambda p: p['decision_sufficient_evidence'].update(method='NOT_ESTIMABLE'),
    lambda p: p['evidence_fragility'].update(decision_flip_count=-1),
    lambda p: p['evidence_fragility'].update(decision_flip_rate=float('nan')),
    lambda p: p['evidence_fragility'].update(decision_flip_count=2, decision_flip_rate=1.0),
    lambda p: p['evidence_fragility']['ablations'][0].update(proposed_decision_change=True),
    lambda p: p['evidence_fragility']['ablations'][0].update(score_delta=float('inf')),
    lambda p: p['evidence_fragility']['ablations'][0].update(evidence_id='invented'),
    lambda p: p['distribution_validity'].update(evaluated_feature_count=False, outside_feature_count=100),
    lambda p: p['distribution_validity'].update(reporting_availability_rate=-1),
    lambda p: p['distribution_validity'].update(reference_name=None),
    lambda p: p['diagnostics'].pop('probability'),
    lambda p: p['diagnostics'].update(probability=0.99),
    lambda p: p['diagnostics'].update(reliability=float('inf')),
    lambda p: p.update(reason_codes=(*p['reason_codes'], 'RUNTIME_FAILURE_REQUIRES_REVIEW')),
    lambda p: p['evidence_assurance'].update(unrecognized=True),
])
def test_rehashed_impossible_assurance_is_rejected(mutation):
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path('a'), path('b'), reference=REFERENCE)).to_dict()
    assert verify_assurance_payload(payload, engine.policy)
    mutation(payload)
    assert not verify_assurance_payload(rehash(payload), engine.policy)


def test_rehashed_fragile_evidence_cannot_claim_automated_flag():
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path('a'), reference=REFERENCE)).to_dict()
    assert payload['final_decision'] == 'REVIEW'
    payload.update(final_decision='FLAG', automation_allowed=True, assurance_status='PASSED', reason_codes=())
    payload['diagnostics']['authorization_blockers'] = ()
    payload['evidence_fragility']['state'] = 'STABLE'
    assert not verify_assurance_payload(rehash(payload), engine.policy)


def test_runtime_parser_failure_requires_abstention_not_review():
    engine = calibrated_engine()
    value = input_for(path('a'), path('b'), reference=REFERENCE)
    from dataclasses import replace
    payload = engine.evaluate(replace(value, runtime_failures=('parser_failure',))).to_dict()
    assert verify_assurance_payload(payload, engine.policy)
    payload['final_decision'] = 'REVIEW'
    assert not verify_assurance_payload(rehash(payload), engine.policy)


def test_valid_json_roundtrip_and_independent_copy():
    import json
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path('a'), path('b'), reference=REFERENCE)).to_dict()
    assert verify_assurance_payload(json.loads(json.dumps(deepcopy(payload))), engine.policy)


def test_additional_top_level_fields_cannot_hide_outside_the_hash():
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path('a'), path('b'), reference=REFERENCE)).to_dict()
    payload['unrecognized'] = {'final_decision': 'PASS'}
    assert not verify_assurance_payload(payload, engine.policy)


def test_unverified_paths_cannot_claim_verified_source_identities():
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path('a', verified=False), reference=REFERENCE)).to_dict()
    payload['evidence_assurance']['verified_evidence_ids'] = ('invented',)
    assert not verify_assurance_payload(rehash(payload), engine.policy)


def test_rehashed_certificate_cannot_wrap_impossible_assurance():
    from finrisk.assurance import verify_decision_certificate
    from finrisk.enterprise.decision import material_decision_payload
    from finrisk.enterprise.decision_bundle import build_decision_bundle
    engine = calibrated_engine()
    paths = [path('a'), path('b')]
    result = engine.evaluate(input_for(*paths, reference=REFERENCE))
    bundle = build_decision_bundle('org', 'entity', {}, {}, {}, {}, paths, {}, [], {},
                                  result.final_decision, assurance=result.to_dict(), assurance_policy=engine.policy)
    payload = bundle.to_dict()
    payload['assurance']['evidence_fragility']['decision_flip_count'] = -1
    rehash(payload['assurance'])
    content = {k: v for k, v in payload.items() if k not in {'bundle_id', 'created_at', 'bundle_hash', 'certificate_hash'}}
    digest = canonical_hash(material_decision_payload(content))
    payload.update(bundle_hash=digest, certificate_hash=digest)
    assert not verify_decision_certificate(payload, engine.policy)
    assert not verify_decision_certificate(payload)
    with pytest.raises(ValueError, match='valid AssuranceResult'):
        build_decision_bundle('org', 'entity', {}, {}, {}, {}, paths, {}, [], {}, result.final_decision,
                              assurance=payload['assurance'], assurance_policy=engine.policy)


def test_last_source_ablation_cannot_self_consistently_preserve_flag():
    engine = calibrated_engine()
    payload = engine.evaluate(input_for(path('a'), reference=REFERENCE)).to_dict()
    payload.update(final_decision='FLAG', automation_allowed=True, assurance_status='PASSED', reason_codes=())
    payload['diagnostics']['authorization_blockers'] = ()
    fragility = payload['evidence_fragility']
    fragility.update(state='STABLE', decision_flip_count=0, decision_flip_rate=0.0)
    fragility['ablations'][0].update(recomputed_proposed_decision='FLAG',
                                    proposed_decision_change=False, final_decision_impact=False)
    # The counters/flags/hash now agree. Nevertheless removing the only source
    # leaves no retained dependency: fusion must ABSTAIN for every fusion policy.
    assert not verify_assurance_payload(rehash(payload), engine.policy)


def test_certificate_id_must_be_the_content_address():
    from finrisk.assurance import verify_decision_certificate
    from finrisk.enterprise.decision_bundle import build_decision_bundle
    engine = calibrated_engine()
    paths = [path('a'), path('b')]
    result = engine.evaluate(input_for(*paths, reference=REFERENCE))
    bundle = build_decision_bundle('org', 'entity', {}, {}, {}, {}, paths, {}, [], {},
                                  result.final_decision, assurance=result.to_dict(), assurance_policy=engine.policy)
    payload = bundle.to_dict()
    payload['bundle_id'] = 'bundle_unrelated_decision'
    # bundle_id is excluded from the material hash, so all recorded hashes stay valid.
    assert not verify_decision_certificate(payload, engine.policy)
