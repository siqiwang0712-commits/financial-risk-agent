"""The frozen full Assurance fanout with original-index source verification."""
from pathlib import Path

from finrisk.assurance.engine import AssuranceEngine, AssuranceInput
from finrisk.assurance.shift import separate_financial_and_reporting_features
from finrisk.enterprise.decision_bundle import build_decision_bundle
from finrisk.enterprise.integrity import CalibrationStatus

from ..execution.core import (
    digest,
    require,
    shared_proposals,
    validate_proposal,
    verify_certificate_binding,
)
from .live_source import extract as live_extract
from .precise_source import extract_packets
from .study import (
    CalibratedStudyProducer,
    evidence_only_decision,
    reference,
    verified_paths,
)


def verify_source_bundle(root, case, manifests, frozen_bundle):
    mode = frozen_bundle['evidence']['source_mode']
    if mode == 'SEC_FSDS_WITH_PRIMARY_INDEX_CLOCK':
        actual = extract_packets(root, [case], manifests, reference_hash=frozen_bundle['packet']['reference_distribution_hash'])[0]
    elif mode == 'LIVE_SEC_EXACT_INDEX_ACCESSION':
        actual = live_extract(root, case['cik'], case['accession'], root/'.runtime/e5-live-source'/case['cik']/case['accession'])
    else:
        raise ValueError('unqualified source mode')
    require(actual == frozen_bundle, 'independent immutable source re-extraction differs')
    return actual


def evaluate_verified(root, packet, proposal, paths, source_hash):
    producer = CalibratedStudyProducer(root)
    h = validate_proposal(proposal, producer_hash=digest(producer.identity))
    require(proposal['input_hash'] == digest(packet), 'admission input/proposal mismatch')
    raw = proposal['raw_structured_output']
    proposed = proposal['proposed_decision']
    s3 = evidence_only_decision(proposed, paths, producer.policy)
    profile = reference(producer.root)
    financial, reporting = separate_financial_and_reporting_features(raw['metrics'], set(profile.feature_bounds))
    engine = AssuranceEngine(producer.policy)
    result = engine.evaluate(AssuranceInput(
        proposed_decision=proposed, risk_score=raw['risk_points'], evidence_paths=tuple(paths),
        financial_features=financial, reporting_observability=reporting,
        disagreement=raw['fusion']['disagreement'], calibration_status=CalibrationStatus.CALIBRATED_INTERNAL,
        reference_profile=profile, fusion_policy=producer.fusion_policy))
    final = engine.authorize(result)
    certificate = build_decision_bundle(
        organization_id='E5-structured-numeric-study', entity_id=proposal['cik'],
        document_hashes={'INDEX_ACCESSION_SOURCE': source_hash},
        frozen_input=packet, frozen_output=proposal,
        risk_state={'risk_points': raw['risk_points'], 'calibrated_probability': proposal['normalized_risk_score']},
        evidence_paths=paths, calculations=raw['metrics'], agent_trace=[],
        component_versions={'proposal_hash': h, 'producer_hash': digest(producer.identity)},
        final_decision=final, proposed_decision=proposed, assurance=result.to_dict(),
        assurance_policy=producer.policy).to_dict()
    verify_certificate_binding(certificate, proposal_hash=h, policy=producer.policy)
    return {'proposal_hash': h, 'S2': proposed, 'S3': s3, 'S4': final,
            'certificate': certificate, 'evidence_paths': paths}


def fanout(producer: CalibratedStudyProducer, proposal: dict, frozen_bundle: dict, *, case: dict, manifests: list[Path], image_id: str):
    h = validate_proposal(proposal, producer_hash=digest(producer.identity))
    shared_proposals({a: proposal for a in ('S2', 'S3', 'S4')}, digest(producer.identity))
    require(proposal['input_hash'] == digest(frozen_bundle['packet']), 'proposal/input mismatch')
    verified = verify_source_bundle(producer.root, case, manifests, frozen_bundle)
    paths = verified_paths(verified['packet'], verified['evidence'], proposal['raw_structured_output'])
    from .isolated import call
    envelope = {'role': 'ADMISSION', 'feature': verified['packet'], 'proposal': proposal,
                'paths': paths, 'source_hash': verified['evidence']['source_sha256']}
    result, receipt = call(image_id, envelope, producer.identity)
    require(result['proposal_hash'] == h, 'isolated admission proposal mismatch')
    verify_certificate_binding(result['certificate'], proposal_hash=h, policy=producer.policy)
    result['admission_isolation_receipt'] = receipt
    return result
