"""Study-only shared-packet adapters; not a qualified E5 proposal producer.

No files, provider calls, model selection or cohort construction. Qualification
and scientific readiness are still blocked. S2/S3 routing is study issuance,
never FinRisk product final authorization.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict

from finrisk.assurance.engine import AssuranceEngine, AssuranceInput
from finrisk.assurance.evidence import assess_evidence
from finrisk.assurance.policy import AssurancePolicy
from finrisk.enterprise.decision_bundle import build_decision_bundle

from .governance import digest, require, shared_proposals


def evidence_only(value: AssuranceInput) -> dict:
    evidence = assess_evidence(list(value.evidence_paths), AssurancePolicy().minimum_verified_coverage)
    decision = value.proposed_decision
    if not evidence.verified_path_count:
        decision = 'ABSTAIN'
    elif evidence.coverage < AssurancePolicy().minimum_verified_coverage:
        decision = 'REVIEW'
    return {'study_disposition': decision, 'evidence': evidence.to_dict(),
            'final_authorization_authority': 'NONE', 'certificate': None}


def compare_adapters(value: AssuranceInput, *, case_id: str, producer_hash: str,
                     organization_id: str, entity_id: str) -> dict:
    require(value.calibration_status.value == 'UNCALIBRATED', 'candidate study is UNCALIBRATED')
    frozen = deepcopy(value)
    proposal = {'case_id': case_id, 'input_hash': digest(asdict(frozen)),
                'producer_hash': producer_hash, 'risk_score': frozen.risk_score,
                'proposed_decision': frozen.proposed_decision}
    proposals = {name: deepcopy(proposal) for name in ('S2', 'S3', 'S4')}
    proposal_hash = shared_proposals(proposals)
    s3 = evidence_only(frozen)
    engine = AssuranceEngine()  # Actual released default policy, never a permissive test policy.
    assurance = engine.evaluate(frozen)
    final = engine.authorize(assurance)
    certificate = build_decision_bundle(
        organization_id=organization_id, entity_id=entity_id, document_hashes={},
        frozen_input=asdict(frozen), frozen_output={'proposal': proposal}, risk_state={},
        evidence_paths=list(frozen.evidence_paths), calculations={}, agent_trace=[],
        component_versions={'producer_hash': producer_hash, 'release_source': '6a6f2053dd168d74aa97533ad901af47a7a5023a'},
        final_decision=final,
        proposed_decision=frozen.proposed_decision, assurance=assurance.to_dict(),
        assurance_policy=engine.policy,
    )
    require(asdict(value) == asdict(frozen), 'adapter mutated shared proposal/input')
    return {'status': 'CANDIDATE_ADAPTER_NOT_PRODUCER_QUALIFICATION',
            'proposals': proposals, 'proposal_hash': proposal_hash,
            'S2': {'study_disposition': frozen.proposed_decision, 'final_authorization_authority': 'NONE'},
            'S3': s3, 'S4': {'assurance': assurance.to_dict(), 'final_decision': final,
                            'study_automated_issuance': assurance.automation_allowed,
                            'certificate': certificate.to_dict()}}
