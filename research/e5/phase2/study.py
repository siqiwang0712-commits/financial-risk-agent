"""Calibrated numeric study boundary and one-proposal S2/S3/S4 fanout.

Production defaults and all production Assurance vetoes remain intact. This
internal calibration applies only to this numerical study, not narrative/LLM
outputs or the released Agent. Source verification does not regenerate proposals.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from finrisk.assurance.domain import PolicyMaturity
from finrisk.assurance.engine import AssuranceEngine, AssuranceInput
from finrisk.assurance.evidence import assess_evidence
from finrisk.assurance.policy import AssurancePolicy
from finrisk.assurance.shift import (
    ReferenceProfile,
    separate_financial_and_reporting_features,
)
from finrisk.enterprise.decision import build_decision_trace
from finrisk.enterprise.decision_bundle import build_decision_bundle
from finrisk.enterprise.integrity import CalibrationStatus
from finrisk.metrics import calculate_metrics

from ..execution.core import (
    digest,
    file_hash,
    read_json,
    require,
    shared_proposals,
    validate_proposal,
    verify_certificate_binding,
)
from .calibration import apply
from .producer import FIELDS, NumericProposalProducer
from .sources import extract_packets

REFERENCE = 'research/strong_tabular_reference/artifacts/empirical_development_reference.json'
CALIBRATION = 'research/e5/phase2/qualification/numeric-v2'


def band(score):
    return 'ABSTAIN' if score is None else 'PASS' if score < .35 else 'FLAG' if score >= .65 else 'REVIEW'


class CalibratedStudyProducer:
    def __init__(self, root: Path):
        self.root = root
        self.raw = NumericProposalProducer(root)
        directory = root / CALIBRATION
        report = read_json(directory / 'calibration_report.json')
        for name, sha in report['artifact_hashes'].items():
            require(file_hash(directory / name) == sha, 'development qualification artifact changed')
        require(read_json(directory / 'raw_producer_identity.json')['identity'] == self.raw.identity,
                'calibration does not belong to exact raw producer')
        self.artifact = read_json(directory / 'calibration_artifact.json')
        self.bindings = {p: file_hash(root / p) for p in (
            'research/e5/phase2/study.py', 'research/e5/phase2/calibration.py',
            'research/e5/phase2/sources.py', 'research/e5/execution/core.py', REFERENCE)}
        self.calibration_hash = file_hash(directory / 'calibration_artifact.json')
        self.identity = self.raw.identity | {
            'version': 'E5-NUMERIC-CALIBRATED-STUDY-V2-CONSISTENT-EVIDENCE-ADMISSION',
            'code_hash': digest({'raw': self.raw.identity, 'bindings': self.bindings,
                                 'calibration': self.calibration_hash}),
            'score_semantics': 'DEVELOPMENT_ONLY_ISOTONIC_OR_LOGISTIC_CALIBRATED_RISK',
            'model': 'STRUCTURED_NUMERIC_STUDY_NOT_RELEASED_AGENT_OR_LLM'}
        # Released fusion outputs are rounded to one decimal risk point. Translate
        # frozen probability thresholds onto that complete grid for fragility.
        self.fusion_policy = deepcopy(self.raw.fusion_policy)
        self.fusion_policy['status'] = 'study-internal-development-calibrated-decision-bands'
        for key, threshold in [('review_score', .35), ('flag_score', .65)]:
            self.fusion_policy[key] = next((j/10 for j in range(1001)
                                           if apply(self.artifact, j/1000) >= threshold), 100.1)
        self.policy = replace(AssurancePolicy(), version='e5-numeric-internal-study-v1-' + self.calibration_hash[:12],
                              maturity=PolicyMaturity.CALIBRATED_INTERNAL)

    def __call__(self, packet):
        require(all(file_hash(self.root / p) == h for p, h in self.bindings.items()), 'study code/reference drift')
        require(file_hash(self.root / CALIBRATION / 'calibration_artifact.json') == self.calibration_hash,
                'study calibration drift')
        result = self.raw(packet)
        raw = result['raw_structured_output']
        score = apply(self.artifact, result['normalized_risk_score'])
        decision = band(score)
        if raw['computational_input_completeness'] < self.policy.minimum_verified_coverage:
            decision = 'ABSTAIN'
        elif raw['fusion']['disagreement'] >= self.policy.maximum_disagreement:
            decision = 'REVIEW'
        raw['calibrated_probability'] = score
        raw['calibration_artifact_sha256'] = self.calibration_hash
        raw['study_fusion_policy'] = self.fusion_policy
        return {'raw_structured_output': raw, 'normalized_risk_score': score, 'proposed_decision': decision}


def reference(root: Path) -> ReferenceProfile:
    value = read_json(root / REFERENCE)
    require(value['construction_uses_labels'] is False, 'label-dependent reference forbidden')
    return ReferenceProfile(name='E4-S frozen financial reference', version='e5-study-adapter-v1',
                            scope='DEVELOPMENT_REFERENCE_ONLY', artifact_hash=file_hash(root / REFERENCE),
                            feature_bounds={k: (v['quantiles']['q01'], v['quantiles']['q99'])
                                            for k, v in value['financial_value_profile'].items()},
                            maximum_outside_fraction=0.)


def verify_source_bundle(root, case, manifests, frozen_bundle):
    """Re-extract from hash-verified original SEC ZIP, never regenerate a proposal."""
    actual = extract_packets(root, [case], manifests,
                             reference_hash=frozen_bundle['packet']['reference_distribution_hash'])
    require(len(actual) == 1 and actual[0] == frozen_bundle, 'independent source re-extraction differs')
    return actual[0]


def verified_paths(packet, evidence, raw):
    """Resolve actual computational dependencies; unknown ones stay unverified."""
    current = {k: packet['features']['current__'+k] for k in FIELDS}
    previous = {k: packet['features']['previous__'+k] for k in FIELDS}
    metrics = calculate_metrics(current, packet['features']['fiscal_year'], previous)
    provenance = evidence['provenance']
    bases = {'assets_basis': 'total_assets', 'equity_basis': 'shareholder_equity',
             'receivables_basis': 'accounts_receivable', 'inventory_basis': 'inventory',
             'payables_basis': 'accounts_payable'}

    def resolve(name, period='current', visited=frozenset()):
        token = period+'__'+name
        if token in visited:
            return None
        visited = visited | {token}
        if name in FIELDS:
            source = provenance.get(token)
            if not source or packet['features'].get(token) is None:
                return None
            if source['status'] == 'DERIVED_FROM_BOUND_SOURCE_ROWS':
                refs = [resolve(p.split('__', 1)[1], p.split('__', 1)[0], visited) for p in source['parents']]
                return None if any(r is None for r in refs) else [item for group in refs for item in group]
            if source['status'] != 'SOURCE_ROW_BOUND' or digest(source['row']) != source['row_hash']:
                return None
            return [{'id': source['row_hash'], 'source_hash': evidence['source_sha256'],
                     'source': evidence['source_url'], 'accession': packet['accession'], 'cik': packet['cik'],
                     'concept': source['row']['tag'], 'raw_value': source['row']['value'],
                     'unit': source['row']['uom'], 'verification_status': 'verified'}]
        dependencies = None
        if name in bases:
            base = bases[name]
            dependencies = [(base, 'current')]
            if previous.get(base) is not None:
                dependencies.append((base, 'previous'))
        elif name in {'EBIT', 'ebit'}:
            dependencies = [('operating_income', period)]
        elif name == 'COGS':
            dependencies = [('revenue', period), ('gross_profit', period)]
        elif name.endswith('_growth'):
            dependencies = [(name[:-7], 'current'), (name[:-7], 'previous')]
        elif name in metrics and metrics[name].value is not None:
            dependencies = [(k, period) for k in metrics[name].inputs]
        elif name.endswith('_change'):
            dependencies = [(name[:-7], 'current'), (name[:-7], 'previous')]
        elif name.endswith('_revenue_growth_gap'):
            dependencies = [(name[:-19]+'_growth', 'current'), ('revenue_growth', 'current')]
        if not dependencies:
            return None
        refs = [resolve(n, p, visited) for n, p in dependencies]
        return None if any(r is None for r in refs) else [item for group in refs for item in group]

    assessment = {'dimensions': raw['dimensions'], 'triggered_rules': deepcopy(raw['triggered_rules'])}
    for signal in assessment['triggered_rules']:
        inputs = signal.get('required_inputs', [])
        refs = {name: resolve(name) for name in inputs}
        signal['input_provenance'] = {name: value or [] for name, value in refs.items()}
        signal['source_refs'] = list({r['id']: r for value in refs.values() for r in (value or [])}.values())
    return build_decision_trace(assessment, raw['fusion'])['paths']


def evidence_only_decision(proposed, paths, policy):
    coverage = assess_evidence(paths, policy.minimum_verified_coverage)
    if proposed == 'ABSTAIN' or not coverage.verified_path_count:
        return 'ABSTAIN'
    if (coverage.coverage < policy.minimum_verified_coverage
            or coverage.verified_path_count < coverage.material_path_count):
        return 'REVIEW'
    return proposed


def fanout(producer: CalibratedStudyProducer, proposal: dict, frozen_bundle: dict, *, case: dict, manifests: list[Path]):
    h = validate_proposal(proposal, producer_hash=digest(producer.identity))
    shared_proposals({a: proposal for a in ('S2', 'S3', 'S4')}, digest(producer.identity))
    require(proposal['input_hash'] == digest(frozen_bundle['packet']), 'proposal/input mismatch')
    verified = verify_source_bundle(producer.root, case, manifests, frozen_bundle)
    raw = proposal['raw_structured_output']
    paths = verified_paths(verified['packet'], verified['evidence'], raw)
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
        document_hashes={'SEC_FSDS': verified['evidence']['source_sha256']},
        frozen_input=verified['packet'], frozen_output=proposal,
        risk_state={'risk_points': raw['risk_points'], 'calibrated_probability': proposal['normalized_risk_score']},
        evidence_paths=paths, calculations=raw['metrics'], agent_trace=[],
        component_versions={'proposal_hash': h, 'producer_hash': digest(producer.identity)},
        final_decision=final, proposed_decision=proposed, assurance=result.to_dict(),
        assurance_policy=producer.policy).to_dict()
    verify_certificate_binding(certificate, proposal_hash=h, policy=producer.policy)
    return {'proposal_hash': h, 'S2': proposed, 'S3': s3, 'S4': final,
            'certificate': certificate, 'evidence_paths': paths}
