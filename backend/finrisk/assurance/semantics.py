"""Validate the serialized runtime representation, independently of its hash.

This verifies observable invariants, not issuer authenticity or a recomputation
from absent financial inputs/reference bounds. Legacy v0.3 bundles stay separate.
"""
from collections.abc import Mapping
from dataclasses import fields
from math import isfinite

from .domain import (
    DecisionSufficientEvidence,
    DistributionValidity,
    EvidenceAssurance,
    EvidenceFragility,
    SufficientEvidenceMethod,
)


def _shape(value, cls):
    return isinstance(value, Mapping) and set(value) == {f.name for f in fields(cls)}


def _count(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in {int, float} and isfinite(value)


def _strings(value, *, ordered=False):
    return (isinstance(value, (list, tuple))
            and all(isinstance(v, str) and v for v in value)
            and (not ordered or list(value) == sorted(set(value))))


def verify_structures(value, policy):
    """Check nested types, redundant aggregates and evidence identity links."""
    evidence = value['evidence_assurance']
    fragility = value['evidence_fragility']
    distribution = value['distribution_validity']
    sufficient = value['decision_sufficient_evidence']
    diagnostics = value['diagnostics']
    if not all((_shape(evidence, EvidenceAssurance), _shape(fragility, EvidenceFragility),
                _shape(distribution, DistributionValidity), _shape(sufficient, DecisionSufficientEvidence))):
        return False
    if (not isinstance(diagnostics, Mapping) or set(diagnostics) != {
            'authorization_blockers', 'runtime_failures', 'reliability', 'probability'}
            or diagnostics['probability'] is not None
            or (diagnostics['reliability'] is not None and not _number(diagnostics['reliability']))
            or not _strings(diagnostics['runtime_failures'])
            or not _strings(diagnostics['authorization_blockers'])
            or not _strings(value['reason_codes'])):
        return False
    for name in ('verified_evidence_ids', 'supported_claims'):
        if not _strings(evidence[name], ordered=True):
            return False
    if not _strings(evidence['diagnostics']):
        return False
    if evidence['verified_path_count'] == 0 and (evidence['verified_evidence_ids'] or evidence['supported_claims']):
        return False
    nodes = list(evidence['verified_evidence_ids'])
    ablations = fragility['ablations']
    if not isinstance(ablations, (list, tuple)) or len(ablations) != len(nodes):
        return False
    ablation_keys = {'evidence_id', 'score_delta', 'severity_change', 'proposed_decision_change',
                     'final_decision_impact', 'recomputed_proposed_decision',
                     'affected_dimensions', 'affected_claims'}
    for row, node in zip(ablations, nodes, strict=True):
        if not isinstance(row, Mapping) or set(row) != ablation_keys or row['evidence_id'] != node:
            return False
        if len(nodes) == 1 and (row['recomputed_proposed_decision'] != 'ABSTAIN'
                                or row['score_delta'] is not None):
            return False
        if row['score_delta'] is not None and not _number(row['score_delta']):
            return False
        if any(type(row[k]) is not bool for k in (
                'severity_change', 'proposed_decision_change', 'final_decision_impact')):
            return False
        if (row['recomputed_proposed_decision'] not in {'PASS', 'FLAG', 'REVIEW', 'ABSTAIN'}
                or row['proposed_decision_change'] != (row['recomputed_proposed_decision'] != value['proposed_decision'])
                or row['final_decision_impact'] != row['proposed_decision_change']
                or not _strings(row['affected_dimensions'], ordered=True)
                or not _strings(row['affected_claims'], ordered=True)):
            return False
    for field, row_field in (('decision_flip_count', 'proposed_decision_change'),
                             ('severity_change_count', 'severity_change')):
        if not _count(fragility[field]) or fragility[field] != sum(row[row_field] for row in ablations):
            return False
    expected_rate = round(fragility['decision_flip_count'] / len(nodes), 6) if nodes else None
    rate = fragility['decision_flip_rate']
    if rate != expected_rate or (rate is not None and not _number(rate)):
        return False
    impacts = [abs(row['score_delta']) for row in ablations if row['score_delta'] is not None]
    impact = fragility['largest_single_evidence_impact']
    if impact != (max(impacts) if impacts else None) or (impact is not None and not _number(impact)):
        return False
    for field in ('affected_dimensions', 'affected_claims'):
        expected = sorted({v for row in ablations for v in row[field]})
        if not _strings(fragility[field], ordered=True) or list(fragility[field]) != expected:
            return False
    if not nodes:
        if fragility['state'] != 'NOT_ESTIMABLE':
            return False
    elif policy is not None:
        expected_state = ('FRAGILE' if fragility['decision_flip_count'] or (
            impact is not None and impact >= policy.fragile_score_delta) else
            'SENSITIVE' if impact is not None and impact >= policy.sensitive_score_delta else 'STABLE')
        if fragility['state'] != expected_state:
            return False
    elif (fragility['state'] == 'NOT_ESTIMABLE'
          or (fragility['decision_flip_count'] and fragility['state'] != 'FRAGILE')):
        return False

    if (not _strings(sufficient['evidence_ids'], ordered=True)
            or not set(sufficient['evidence_ids']).issubset(nodes)
            or type(sufficient['exact']) is not bool
            or type(sufficient['preserves_proposed_decision']) is not bool
            or not _count(sufficient['evaluated_subsets'])
            or sufficient['baseline_decision'] != value['proposed_decision']):
        return False
    method = SufficientEvidenceMethod(sufficient['method'])
    if not nodes:
        if (method is not SufficientEvidenceMethod.NOT_ESTIMABLE or sufficient['exact']
                or sufficient['preserves_proposed_decision'] or sufficient['evidence_ids']
                or sufficient['evaluated_subsets']):
            return False
    elif (method is SufficientEvidenceMethod.NOT_ESTIMABLE or not sufficient['evidence_ids']
          or sufficient['evaluated_subsets'] == 0
          or sufficient['exact'] != (method is SufficientEvidenceMethod.EXACT)) or policy is not None and (method is SufficientEvidenceMethod.EXACT) != (
            len(nodes) <= policy.maximum_fragility_nodes_exact):
        return False

    if nodes:
        evaluations = sufficient['evaluated_subsets']
        if method is SufficientEvidenceMethod.EXACT:
            maximum = (1 << len(nodes)) - 1
            if sufficient['preserves_proposed_decision']:
                if evaluations > maximum:
                    return False
            elif evaluations != maximum + 1 or list(sufficient['evidence_ids']) != nodes:
                return False
        elif evaluations > len(nodes) + 1:
            return False

    if (not _count(distribution['evaluated_feature_count'])
            or not _count(distribution['outside_feature_count'])
            or distribution['outside_feature_count'] > distribution['evaluated_feature_count']
            or not _strings(distribution['diagnostics'])):
        return False
    availability = distribution['reporting_availability_rate']
    if availability is not None and (not _number(availability) or not 0 <= availability <= 1):
        return False
    reference = [distribution[k] for k in ('reference_name', 'reference_version', 'reference_scope')]
    if all(v is None for v in reference):
        if (distribution['state'] != 'UNKNOWN' or distribution['evaluated_feature_count']
                or distribution['outside_feature_count']):
            return False
    elif not all(isinstance(v, str) and v for v in reference):
        return False
    return not (distribution['state'] == 'IN_REFERENCE' and distribution['outside_feature_count'])


def verify_transition(value, policy):
    """Reconstruct the decision transition from the serialized blocker states.

    The disagreement scalar is not persisted, so its recorded blocker remains an
    input; all other blockers and all reason codes are derived here. With no
    policy, policy-dependent optional blockers cannot be fully reconstructed.
    """
    diagnostics = value['diagnostics']
    recorded = list(diagnostics['authorization_blockers'])
    blockers, reasons = [], []

    def add(reason, blocker=None):
        reasons.append(reason)
        if blocker:
            blockers.append(blocker)

    if value['evidence_assurance']['state'] != 'VERIFIED':
        add('INSUFFICIENT_VERIFIED_EVIDENCE', 'evidence')
    state = value['evidence_fragility']['state']
    if state == 'FRAGILE':
        add('EVIDENCE_FRAGILITY_HIGH', 'fragility')
    elif state == 'NOT_ESTIMABLE' and (policy.review_on_fragility_not_estimable if policy else 'fragility_unknown' in recorded):
        add('EVIDENCE_FRAGILITY_NOT_ESTIMABLE', 'fragility_unknown')
    state = value['distribution_validity']['state']
    if state == 'OUTSIDE_REFERENCE':
        add('OUTSIDE_VALIDATED_DISTRIBUTION', 'distribution')
    elif state == 'WARNING':
        add('REPORTING_OBSERVABILITY_ANOMALY', 'distribution_warning')
    elif state == 'UNKNOWN' and (policy.require_distribution_reference if policy else 'DISTRIBUTION_VALIDITY_UNKNOWN' in value['reason_codes']):
        add('DISTRIBUTION_VALIDITY_UNKNOWN', 'distribution_unknown' if (
            policy.review_on_unknown_distribution if policy else 'distribution_unknown' in recorded) else None)
    if 'disagreement' in recorded:
        add('HIGH_MODEL_DISAGREEMENT', 'disagreement')
    failures = diagnostics['runtime_failures']
    if failures:
        add('RUNTIME_FAILURE_REQUIRES_REVIEW', 'runtime_failure')
    if value['calibration_status'] == 'UNCALIBRATED':
        add('ASSURANCE_POLICY_UNCALIBRATED')
    elif value['policy_status'] == 'HEURISTIC_POLICY':
        add('CALIBRATION_SCOPE_MISMATCH')
    proposed = value['proposed_decision']
    if proposed == 'ABSTAIN':
        add('PROPOSED_DECISION_WITHHELD')
    if recorded != blockers or list(value['reason_codes']) != reasons:
        return False
    abstain = (proposed == 'ABSTAIN' or value['evidence_assurance']['verified_path_count'] == 0
               or bool(set(failures) & {'parser_failure', 'stale_data', 'missing_evidence'}))
    final = 'ABSTAIN' if abstain else 'REVIEW' if blockers else proposed
    if value['final_decision'] != final:
        return False
    if policy is not None:
        automation = (not blockers and final in {'PASS', 'FLAG'}
                      and value['policy_status'] != 'HEURISTIC_POLICY'
                      and (value['calibration_status'] != 'UNCALIBRATED' or not policy.require_calibration_for_automation))
        if value['automation_allowed'] != automation:
            return False
    return True
