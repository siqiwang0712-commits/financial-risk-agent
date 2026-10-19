"""Adversarial design guards; synthetic fixtures only, never prospective E5."""
from __future__ import annotations

import copy
import json

import pytest

from research.e5.autonomy import governance as g
from research.e5.harness import e5_harness as h


def test_corrupt_manifest_is_not_silently_an_unfrozen_study(tmp_path):
    (tmp_path/'00-protocol.json').write_text('{broken')
    with pytest.raises(h.HarnessError):
        h.load_manifests(tmp_path)


def test_unknown_manifest_stage_is_rejected(tmp_path):
    (tmp_path/'unknown.json').write_text(json.dumps({'stage':'invented'}))
    with pytest.raises(h.HarnessError):
        h.load_manifests(tmp_path)


def test_rehashed_missing_protocol_hash_is_rejected(tmp_path):
    value=h.build_manifest('protocol',previous=None,artifacts=[])
    value['protocol_sha256']=None
    h.write_manifest(tmp_path,value)
    assert not h.verify(tmp_path).ok


def test_duplicate_stage_manifest_is_rejected(tmp_path):
    value=h.build_manifest('protocol',previous=None,artifacts=[])
    h.write_manifest(tmp_path,value)
    (tmp_path/'duplicate.json').write_text(json.dumps(value))
    with pytest.raises(h.HarnessError):
        h.load_manifests(tmp_path)


def test_cohort_cannot_omit_disjointness_assertion(tmp_path):
    value=h.build_manifest('cohort-freeze',previous=None,artifacts=[])
    h.write_manifest(tmp_path,value)
    report=h.verify(tmp_path)
    assert any('required disjointness' in item['check'] for item in report.failures)


def test_real_protocol_freeze_is_forbidden_by_task_ceiling():
    value=h.build_manifest('protocol',previous=None,artifacts=[])
    with pytest.raises(h.HarnessError,match='mandate'):
        h.write_manifest(h.DEFAULT_STAGE_DIR,value)


def test_declared_blocked_state_is_truthful():
    result=g.verify_state()
    assert result['status']=='BLOCKED' and result['freeze_critical_unresolved_count']>0
    assert 'E5-C01' in result['cohort_blockers'] and 'E5-C01' not in result['protocol_blockers']


@pytest.mark.parametrize(('current','target'),[('DRAFT','PREDICTIONS_FROZEN'),('READY_TO_FREEZE','PROTOCOL_FROZEN'),('DRAFT','READY_TO_FREEZE'),('E5_COMPLETE','DRAFT')])
def test_no_skip_freeze_or_gate_override(current,target):
    with pytest.raises(g.GovernanceError):g.transition(current,target)


@pytest.mark.parametrize('mutation',[lambda x:x['blockers'][0].update(status='RESOLVED'),lambda x:x['blockers'][0].update(resolved=True),lambda x:x['blockers'][0].update(missing_information='')])
def test_fabricated_blocker_resolution_is_rejected(mutation):
    value=g.load(g.DIRECTORY/'blockers.json');mutation(value)
    with pytest.raises(g.GovernanceError):g.validate_blockers(value)


@pytest.mark.parametrize('evidence',['E5_OUTCOMES','E5_COHORT','E5_PREDICTIONS'])
def test_e5_evidence_cannot_select_models_thresholds_or_protocol(evidence):
    with pytest.raises(g.GovernanceError):g.validate_selection(evidence)


def test_even_historical_selection_fails_when_outcomes_accessible():
    with pytest.raises(g.GovernanceError):g.validate_selection('APPROVED_HISTORICAL_DEVELOPMENT',outcomes_accessible=True)


def proposal():
    return {'case_id':'synthetic-one','input_hash':'a'*64,'producer_hash':'b'*64,'risk_score':70,'proposed_decision':'FLAG'}


def test_shared_packet_hash_invariant_is_not_producer_qualification():
    value=proposal();assert g.shared_proposals({name:copy.deepcopy(value) for name in ('S2','S3','S4')})==g.digest(value)


@pytest.mark.parametrize('score',[True,float('nan'),float('inf'),-1,101])
def test_nonfinite_bool_or_out_of_range_proposals_fail(score):
    value=proposal();value['risk_score']=score
    with pytest.raises((g.GovernanceError,ValueError)):g.shared_proposals({name:copy.deepcopy(value) for name in ('S2','S3','S4')})


def test_s4_proposal_cannot_silently_differ():
    values={name:proposal() for name in ('S2','S3','S4')};values['S4']['risk_score']=69
    with pytest.raises(g.GovernanceError,match='mismatch'):g.shared_proposals(values)


def packet():
    return {'case_id':'synthetic-one','cik':'0000000001','accession':'0000000001-27-000001','schema_hash':'a'*64,'prediction_cutoff':'2027-01-01T00:00:00Z','sources':[{'company':'synthetic','cik':'0000000001','accession':'0000000001-27-000001','filing_timestamp':'2027-01-01T00:00:00Z','period':'2026','source':'synthetic-test','unit':'USD','source_hash':'b'*64,'available_at':'2027-01-01T00:00:00Z'}]}


def test_point_in_time_positive_and_future_leakage():
    value=packet();g.validate_packet(value,expected_schema_hash='a'*64)
    value['sources'][0]['available_at']='2027-01-02T00:00:00Z'
    with pytest.raises(g.GovernanceError,match='future'):g.validate_packet(value,expected_schema_hash='a'*64)


@pytest.mark.parametrize('mutate',[lambda x:x.update(outcome=0),lambda x:x.update(schema_hash='c'*64),lambda x:x['sources'][0].update(cik='0000000002')])
def test_schema_outcome_and_company_substitution_fail(mutate):
    value=packet();mutate(value)
    with pytest.raises(g.GovernanceError):g.validate_packet(value,expected_schema_hash='a'*64)


def test_missing_exclusion_never_becomes_exact(tmp_path):
    with pytest.raises(g.GovernanceError,match='missing historical'):g.verify_exclusions(set(),set(),tmp_path/'absent')
    invented=tmp_path/'previous_270.json';invented.write_text('[]')
    with pytest.raises(g.GovernanceError,match='not exact'):g.verify_exclusions(set(),set(),invented)


@pytest.mark.parametrize('status',['REQUIRES_REVIEW','INSUFFICIENT_DATA'])
def test_missing_labels_cannot_be_negative(status):
    assert g.outcome_label(status,None) is None
    with pytest.raises(g.GovernanceError):g.outcome_label(status,0)


def test_bool_is_not_a_verified_binary_label():
    with pytest.raises(g.GovernanceError):g.outcome_label('VERIFIED',False)


def amendment_record():
    return {'id':'SYNTHETIC-AMENDMENT','utc_timestamp':'2027-01-01T00:00:00Z','reason':'negative synthetic result is not a license to retune','changes':['threshold'],'old_hashes':{'config':'a'*64},'new_hashes':{'config':'b'*64},'cohort_visible':True,'predictions_existed':True,'outcomes_accessible':True,'scientific_impact':'changes decision rule'}


def test_unfavorable_results_cannot_preserve_identity_after_retuning():
    assert g.amendment(amendment_record(),'OUTCOMES_UNLOCKED')['confirmatory_identity']=='INVALIDATED'


def test_amendments_cannot_hide_exposure():
    value=amendment_record();value['outcomes_accessible']=False
    with pytest.raises(g.GovernanceError,match='exposure'):g.amendment(value,'OUTCOMES_UNLOCKED')


@pytest.mark.parametrize(('family','passed'),[('POST_HOC',True),('PRIMARY',False)])
def test_failed_primaries_cannot_be_promoted(family,passed):
    with pytest.raises(g.GovernanceError):g.primary_claim(family=family,primary_passed=passed)


def test_duplicate_json_fields_and_nonfinite_constants_fail(tmp_path):
    for text in ('{"state":1,"state":2}','{"value":NaN}'):
        p=tmp_path/'bad.json';p.write_text(text)
        with pytest.raises(g.GovernanceError):g.load(p)


def test_identity_coverage_cannot_drop_the_certificate_verifier(tmp_path,monkeypatch):
    data=g.load(g.DIRECTORY/'design_identities.json');data['sources'].pop('backend/finrisk/assurance/certificate.py')
    original=g.load
    monkeypatch.setattr(g,'load',lambda path:data if path.name=='design_identities.json' else original(path))
    with pytest.raises(g.GovernanceError,match='coverage'):g.verify_identities()


def test_company_overlap_rejected_independent_of_missing_input():
    with pytest.raises(g.GovernanceError,match='company overlap'):
        g.assert_disjoint({'0000000001'},{'0000000001'})


@pytest.mark.parametrize('source',['backend/finrisk/assurance/engine.py','backend/finrisk/assurance/certificate.py','research/strong_tabular_reference/artifacts/model.pkl'])
def test_rehashed_identity_cannot_replace_release_policy_certificate_or_model(monkeypatch,source):
    data=g.load(g.DIRECTORY/'design_identities.json');data['sources'][source]='0'*64
    original=g.load
    monkeypatch.setattr(g,'load',lambda path:data if path.name=='design_identities.json' else original(path))
    with pytest.raises(g.GovernanceError,match='identity drift'):g.verify_identities()


def test_prediction_manifest_requires_analysis_identity_and_is_not_regenerable(tmp_path):
    value=h.build_manifest('prediction-freeze',previous=None,artifacts=[])
    value['scientific_sources'].pop('research/e5/autonomy/INFERENCE_DESIGN.md')
    h.write_manifest(tmp_path,value)
    assert any('analysis/model/policy' in item['check'] for item in h.verify(tmp_path).failures)
    with pytest.raises(h.HarnessError,match='overwrite'):h.write_manifest(tmp_path,value)


def test_future_analysis_source_drift_rejected_even_after_rehash(tmp_path):
    value=h.build_manifest('prediction-freeze',previous=None,artifacts=[])
    value['scientific_sources']['research/e5/autonomy/INFERENCE_DESIGN.md']='0'*64
    h.write_manifest(tmp_path,value)
    assert any('scientific source research/e5/autonomy/INFERENCE_DESIGN' in item['check'] for item in h.verify(tmp_path).failures)


def test_primary_alpha_or_unknown_authority_cannot_drift(tmp_path,monkeypatch):
    original=g.load
    for mutate in (lambda x:x['primary_family'].update(family_wise_alpha=.5),lambda x:x.update(legacy_primary=True)):
        data=original(g.ROOT/g.AUTHORITY[1]);mutate(data)
        monkeypatch.setattr(g,'load',lambda path,data=data:data if path.name=='experiment_config.json' else original(path))
        with pytest.raises(g.GovernanceError):g.resolve()


def test_planning_is_reproducible_and_not_selected_power():
    from research.e5.autonomy.power_design import planning
    first=planning();assert first==planning()
    assert first==g.load(g.DIRECTORY.parent/'power_plan.json')
    assert first['final_sample_size'] is None and len(first['rows'])==144
    assert min(row['joint_design_lower_bound_n'] for row in first['rows'])>0


def test_zero_automation_is_real_released_policy_not_a_fabricated_blocker():
    from finrisk.assurance.engine import AssuranceEngine
    from test_assurance_runtime import input_for, path
    result=AssuranceEngine().evaluate(input_for(path('synthetic-only')))
    assert result.automation_allowed is False


def test_duplicate_material_evidence_cannot_inflate_assurance():
    from finrisk.assurance.evidence import assess_evidence
    from test_assurance_runtime import path
    source=path('synthetic-only')
    assert assess_evidence([source],.4)==assess_evidence([source,copy.deepcopy(source)],.4)


def test_candidate_adapters_share_exact_proposal_without_qualifying_the_producer():
    from dataclasses import replace

    from finrisk.assurance import verify_decision_certificate
    from finrisk.enterprise.integrity import CalibrationStatus
    from test_assurance_runtime import input_for, path

    from research.e5.autonomy.candidate_arms import compare_adapters

    value=replace(input_for(path('synthetic-one'),path('synthetic-two')),
                  calibration_status=CalibrationStatus.UNCALIBRATED,reliability=None)
    result=compare_adapters(value,case_id='synthetic-one',producer_hash='a'*64,
                            organization_id='synthetic-org',entity_id='synthetic-entity')
    assert len({g.digest(item) for item in result['proposals'].values()})==1
    assert verify_decision_certificate(result['S4']['certificate'])
    assert result['S4']['study_automated_issuance'] is False
    assert result['S3']['certificate'] is None


def test_evidence_only_adapter_never_invokes_full_assurance(monkeypatch):
    from test_assurance_runtime import input_for, path

    from research.e5.autonomy import candidate_arms
    def forbidden():
        raise AssertionError('Full Assurance must not be an S3 control')
    monkeypatch.setattr(candidate_arms,'AssuranceEngine',forbidden)
    result=candidate_arms.evidence_only(input_for(path('synthetic-one')))
    assert result['final_authorization_authority']=='NONE' and result['certificate'] is None


@pytest.mark.parametrize('relative',['../outside','/etc/passwd'])
def test_stage_artifact_paths_cannot_escape_repository(relative):
    with pytest.raises(h.HarnessError,match='path'):
        h.build_manifest('protocol',previous=None,artifacts=[{'path':relative}])


def test_rehashed_missing_timestamp_is_rejected(tmp_path):
    value=h.build_manifest('protocol',previous=None,artifacts=[])
    value.pop('created_at_utc')
    h.write_manifest(tmp_path,value)
    assert any('timestamp required' in x['check'] for x in h.verify(tmp_path).failures)


def test_duplicate_manifest_fields_fail_closed(tmp_path):
    (tmp_path/'00-protocol.json').write_text('{"stage":"invented","stage":"protocol"}')
    with pytest.raises(h.HarnessError):h.load_manifests(tmp_path)


def test_rehashed_root_cannot_claim_a_previous_protocol(tmp_path):
    value=h.build_manifest('protocol',previous=None,artifacts=[])
    value['previous_manifest_sha256']='a'*64
    h.write_manifest(tmp_path,value)
    assert any('root has no previous' in x['check'] for x in h.verify(tmp_path).failures)


@pytest.mark.parametrize('mutate', [lambda x:x.update(status='READY_TO_FREEZE'),lambda x:x.update(current_config_sha256='0'*64),lambda x:x['readiness'].update(freeze_critical_unresolved_count=0),lambda x:x['critical_assertions'].update(OUTCOMES='ACCESSED'),lambda x:x.update(validated_code_sha256={})])
def test_readiness_report_cannot_fabricate_readiness_identity_or_execution(mutate):
    report=g.load(g.DIRECTORY.parent/'final_readiness.json')
    mutate(report)
    with pytest.raises(g.GovernanceError):g.verify_readiness_report(report,g.resolve())
