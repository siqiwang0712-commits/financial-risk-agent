"""Outcome-blind design guards. No data acquisition, fitting or stage execution."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = Path(__file__).resolve().parent
AUTHORITY = ['research/e5/STUDY_PROTOCOL_DRAFT.md', 'research/e5/experiment_config.json']
IDENTITY_SOURCES = frozenset(['backend/finrisk/__init__.py', 'backend/finrisk/agent/__init__.py', 'backend/finrisk/agent/orchestrator.py', 'backend/finrisk/agent/planner.py', 'backend/finrisk/agent/reflection.py', 'backend/finrisk/agent/review.py', 'backend/finrisk/agent/state.py', 'backend/finrisk/agent/synthesis.py', 'backend/finrisk/agent/tool_registry.py', 'backend/finrisk/agent/verification.py', 'backend/finrisk/api.py', 'backend/finrisk/assurance/__init__.py', 'backend/finrisk/assurance/certificate.py', 'backend/finrisk/assurance/domain.py', 'backend/finrisk/assurance/engine.py', 'backend/finrisk/assurance/evidence.py', 'backend/finrisk/assurance/fragility.py', 'backend/finrisk/assurance/policy.py', 'backend/finrisk/assurance/reason_codes.py', 'backend/finrisk/assurance/semantics.py', 'backend/finrisk/assurance/shift.py', 'backend/finrisk/benchmark.py', 'backend/finrisk/benchmark_protocol.py', 'backend/finrisk/contradictions.py', 'backend/finrisk/document_worker.py', 'backend/finrisk/domain.py', 'backend/finrisk/e4_agent.py', 'backend/finrisk/e4_core.py', 'backend/finrisk/e4_evaluation.py', 'backend/finrisk/e4_outcomes.py', 'backend/finrisk/e4_posthoc.py', 'backend/finrisk/empirical_validation.py', 'backend/finrisk/enterprise/__init__.py', 'backend/finrisk/enterprise/alerts.py', 'backend/finrisk/enterprise/api.py', 'backend/finrisk/enterprise/applicability.py', 'backend/finrisk/enterprise/auth.py', 'backend/finrisk/enterprise/calibration.py', 'backend/finrisk/enterprise/decision.py', 'backend/finrisk/enterprise/decision_bundle.py', 'backend/finrisk/enterprise/domain.py', 'backend/finrisk/enterprise/evidence_graph.py', 'backend/finrisk/enterprise/fusion.py', 'backend/finrisk/enterprise/governance.py', 'backend/finrisk/enterprise/integrity.py', 'backend/finrisk/enterprise/jobs.py', 'backend/finrisk/enterprise/observability.py', 'backend/finrisk/enterprise/policy.py', 'backend/finrisk/enterprise/portfolio.py', 'backend/finrisk/enterprise/postgres.py', 'backend/finrisk/enterprise/repository.py', 'backend/finrisk/enterprise/scenario.py', 'backend/finrisk/enterprise/schemas.py', 'backend/finrisk/enterprise/security.py', 'backend/finrisk/enterprise/service.py', 'backend/finrisk/enterprise/storage.py', 'backend/finrisk/enterprise/telemetry.py', 'backend/finrisk/enterprise/temporal.py', 'backend/finrisk/enterprise/tension.py', 'backend/finrisk/enterprise/workflow.py', 'backend/finrisk/evaluation.py', 'backend/finrisk/evidence.py', 'backend/finrisk/extraction_reference.py', 'backend/finrisk/facts.py', 'backend/finrisk/human_study.py', 'backend/finrisk/llm.py', 'backend/finrisk/metrics.py', 'backend/finrisk/models.py', 'backend/finrisk/normalization.py', 'backend/finrisk/numeric_benchmark.py', 'backend/finrisk/parser.py', 'backend/finrisk/pipeline.py', 'backend/finrisk/process_isolation.py', 'backend/finrisk/public_pilot.py', 'backend/finrisk/report.py', 'backend/finrisk/reproducibility.py', 'backend/finrisk/request_boundary.py', 'backend/finrisk/research_eval.py', 'backend/finrisk/research_schema.py', 'backend/finrisk/resources.py', 'backend/finrisk/rules.py', 'backend/finrisk/runtime.py', 'backend/finrisk/scoring.py', 'backend/finrisk/sec_bulk.py', 'backend/finrisk/secret_files.py', 'backend/finrisk/severity.py', 'backend/finrisk/tools/__init__.py', 'backend/finrisk/tools/ingestion.py', 'backend/finrisk/tools/registry.py', 'backend/finrisk/upload_boundary.py', 'backend/finrisk/verification_http.py', 'backend/finrisk/xbrl.py', 'config/assurance_policy.json', 'config/consistency_policy.json', 'config/decision_policy.json', 'config/model_scoring.json', 'config/scoring.json', 'requirements.lock', 'research/e5/narrative/NARRATIVE_PROTOCOL.md', 'research/e5/narrative/experiment_config.json', 'research/strong_tabular_reference/artifacts/artifact_manifest.json', 'research/strong_tabular_reference/artifacts/e5_exclusion_companies_2000.json', 'research/strong_tabular_reference/artifacts/empirical_development_reference.json', 'research/strong_tabular_reference/artifacts/generation_requirements.lock', 'research/strong_tabular_reference/artifacts/model.pkl', 'research/strong_tabular_reference/artifacts/preprocessor.pkl', 'research/strong_tabular_reference/artifacts/runtime_identity.json', 'research/strong_tabular_reference/contract_identity.json', 'research/strong_tabular_reference/development_data_manifest.json', 'research/strong_tabular_reference/development_run_config.json', 'research/strong_tabular_reference/experiment_config.json', 'research/strong_tabular_reference/feature_schema.json', 'rules/disabled_rules.json', 'rules/rules.json'])
CONFIG_KEYS = frozenset(['assurance', 'authoritative_protocol', 'calibration', 'cohort', 'comparison_questions', 'conceptual_arms', 'design_governance', 'eligibility_design', 'endpoint_contract', 'environment_variables', 'estimand_families', 'freeze_prerequisites', 'governance', 'historical_anchors', 'narrative_study', 'outcomes', 'predictions', 'primary_family', 'reference_distribution', 'schema_version', 'status', 'strong_tabular_reference', 'study_id', 'study_title'])
STATE_FIELDS = {'schema_version', 'state', 'readiness', 'protocol_freeze', 'cohort',
                'predictions', 'outcomes', 'external_validation', 'calibration'}
BLOCKER_FIELDS = {'id', 'scope', 'status', 'unresolved_decision', 'evidence_insufficient_because',
                  'missing_information', 'confirmatory_risk', 'allowed_next_actions',
                  'prohibited_shortcuts', 'config_paths'}
SCIENTIFIC_FIELDS = {'endpoint', 'model', 'feature_schema', 'threshold', 'primary_estimand',
                     'assurance_policy', 'statistical_test', 'coverage', 'claim_wording'}


class GovernanceError(ValueError):
    """An invariant failed; callers must not replace this with successful output."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GovernanceError(message)


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, f'duplicate JSON field: {key}')
        value[key] = item
    return value


def load(path: Path) -> dict:
    value = json.loads(path.read_text(), object_pairs_hook=_pairs,
                       parse_constant=lambda value: (_ for _ in ()).throw(GovernanceError('nonfinite JSON')))
    require(isinstance(value, dict), f'object required: {path}')
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix != '.pkl':
        raw = raw.replace(b'\r\n', b'\n')
    return hashlib.sha256(raw).hexdigest()


def safe_path(root: Path, name: str) -> Path:
    require(isinstance(name, str) and bool(name) and not Path(name).is_absolute(), 'relative path required')
    path = root / name
    require(path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(), 'path escape/symlink')
    return path


def unresolved(value: Any, prefix: str = '') -> list[str]:
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            result.extend(unresolved(item, f'{prefix}.{key}'.strip('.')))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(unresolved(item, f'{prefix}.{index}'))
    elif value is None or isinstance(value, str) and ('TO_BE_' in value or value.startswith('BLOCKED')):
        result.append(prefix)
    return result


def validate_blockers(value: dict) -> list[dict]:
    require(set(value) == {'schema_version', 'blockers'} and type(value['schema_version']) is int
            and value['schema_version'] == 1, 'blocker envelope')
    blockers = value['blockers']
    require(isinstance(blockers, list) and bool(blockers), 'explicit blockers required')
    ids = set()
    for item in blockers:
        require(isinstance(item, dict) and set(item) == BLOCKER_FIELDS, 'blocker schema/unknown field')
        require(item['id'] not in ids and re.fullmatch(r'E5-[PCF][0-9]{2}', item['id']) is not None, 'blocker ID')
        ids.add(item['id'])
        require(item['scope'] in {'PROTOCOL_FREEZE', 'COHORT_FREEZE', 'FUTURE_DATA'}
                and item['status'] == 'OPEN', 'fabricated blocker resolution')
        for key in BLOCKER_FIELDS - {'allowed_next_actions', 'prohibited_shortcuts', 'config_paths'}:
            require(isinstance(item[key], str) and bool(item[key]), f'blocker missing {key}')
        for key in ('allowed_next_actions', 'prohibited_shortcuts', 'config_paths'):
            require(isinstance(item[key], list) and all(isinstance(x, str) and x for x in item[key]), 'blocker list')
        require(bool(item['allowed_next_actions']) and bool(item['prohibited_shortcuts']), 'blocker actions required')
    return blockers


def resolve(root: Path = ROOT, *, config: dict | None = None) -> dict:
    config = load(root / AUTHORITY[1]) if config is None else config
    require(set(config) == CONFIG_KEYS, 'unknown/missing config authority field')
    require(config['assurance']['policy_maturity'] == 'HEURISTIC_POLICY' and config['assurance']['certificate_schema'] == 'decision-certificate-v0.4', 'policy/certificate downgrade')
    rules = load(root / 'research/e5/autonomy/DESIGN_RULES.json')
    require(rules['scientific_authority'] == AUTHORITY and rules['autopilot_is_scientific_authority'] is False
            and rules['legacy_freeze_authority'] is False, 'scientific authority changed')
    require(config['authoritative_protocol']['path'] == AUTHORITY[0], 'legacy protocol authority')
    require(config['authoritative_protocol']['freeze_allowed'] is False
            and config['governance']['protocol_freeze_allowed'] is False, 'freeze not authorized for this mandate')
    require(config['calibration']['score_status'] == 'UNCALIBRATED'
            and config['calibration']['probability_interpretation_allowed'] is False, 'calibration drift')
    family = config['primary_family']
    require(type(family['family_wise_alpha']) is float and family['family_wise_alpha'] == .05
            and family['multiplicity'] == 'HOLM_STEP_DOWN_P1_P2', 'primary alpha/multiplicity drift')
    require([(x['id'], x['comparison']) for x in family['hypotheses']] == [('P1','S4_vs_S1'),('P2','S4_vs_S3')], 'primary family drift')
    simple = config['conceptual_arms'][1]
    require(simple['flag_at_or_above'] == .65 and simple['pass_below'] == .35
            and simple['policy_id'] == 's1-fixed-review-band-v1', 'S1 policy drift')
    blockers = validate_blockers(load(root / 'research/e5/autonomy/blockers.json'))
    all_open_paths = unresolved(config)
    deferred = {
        'environment_variables.status': 'EXECUTION_ENVIRONMENT_MANIFEST_NOT_CREATED',
        'cohort.company_disjointness': 'COHORT_FREEZE_PROOF_NOT_PROTOCOL_CHOICE',
        'cohort.previous_270_exclusion': 'COHORT_FREEZE_INPUT_NOT_PROTOCOL_CHOICE',
    }
    explicit_values = {'endpoint_contract.nonverified_label', 'design_governance.readiness'}
    paths = [path for path in all_open_paths if path not in deferred and path not in explicit_values]
    critical = [item['id'] for item in blockers if item['scope'] == 'PROTOCOL_FREEZE']
    # The config cannot bless itself; unresolved fields and independent feasibility
    # blockers both prevent readiness, even if the flags say otherwise.
    policy = load(root / 'config/assurance_policy.json')
    if policy['maturity'] == 'HEURISTIC_POLICY':
        require('E5-P01' in critical, 'default policy zero-automation blocker disappeared')
    require('E5-P02' in critical and 'E5-P03' in critical and 'E5-P04' in critical,
            'unresolved scientific blockers require explicit approved redesign')
    return {'status': 'BLOCKED' if paths or critical else 'READY_TO_FREEZE',
            'freeze_critical_unresolved_count': len(paths), 'unresolved_config_paths': paths,
            'deferred_stage_fields': deferred,
            'protocol_blockers': critical,
            'cohort_blockers': [x['id'] for x in blockers if x['scope'] == 'COHORT_FREEZE'],
            'future_data_blockers': [x['id'] for x in blockers if x['scope'] == 'FUTURE_DATA'],
            'protocol_sha256': file_hash(root / AUTHORITY[0]),
            'config_sha256': file_hash(root / AUTHORITY[1])}


def verify_readiness_report(report: dict, decision: dict) -> None:
    require(report['status'] == decision['status'] and report['readiness'] == decision,
            'readiness report contradicts independent gates')
    require(report['current_protocol_sha256'] == decision['protocol_sha256']
            and report['current_config_sha256'] == decision['config_sha256'], 'readiness report identity drift')
    expected = {'COHORT':'NOT_ENUMERATED','PREDICTIONS':'NOT_GENERATED','OUTCOMES':'NOT_ACCESSED',
                'PROTOCOL FREEZE':'NOT_EXECUTED','E5 VALIDATION':'NOT_ESTABLISHED','CALIBRATION':'UNCALIBRATED'}
    require(report['critical_assertions'] == expected, 'readiness report fabricates execution')
    current_sources = {str(p.relative_to(ROOT)): file_hash(p) for p in [*DIRECTORY.glob('*.py'), ROOT/'research/e5/harness/e5_harness.py', ROOT/'research/e5/validate_study_contract.py']}
    require(report['validated_code_sha256'] == current_sources, 'readiness audit code identity drift')


def verify_state(root: Path = ROOT) -> dict:
    value = load(root / 'research/e5/autonomy/state.json')
    expected = {'schema_version': 1, 'state': 'DRAFT', 'readiness': 'BLOCKED',
                'protocol_freeze': 'NOT_EXECUTED', 'cohort': 'NOT_ENUMERATED',
                'predictions': 'NOT_GENERATED', 'outcomes': 'NOT_ACCESSED',
                'external_validation': 'NOT_ESTABLISHED', 'calibration': 'UNCALIBRATED'}
    require(set(value) == STATE_FIELDS and type(value['schema_version']) is int
            and value == expected, 'state claims execution/readiness not established by evidence')
    stages = root / 'research/e5/freeze'
    require(not stages.exists() or not any(stages.iterdir()), 'actual freeze artifact forbidden')
    for name in ('cohort', 'predictions', 'outcomes', 'results', 'feature_packets'):
        p = root / 'research/e5' / name
        require(not p.exists(), f'actual E5 execution artifact forbidden: {name}')
    decision = resolve(root)
    require(value['readiness'] == decision['status'], 'state disagrees with resolver')
    report_path = root / 'research/e5/final_readiness.json'
    if report_path.exists():
        verify_readiness_report(load(report_path), decision)
    return decision


def transition(current: str, target: str, *, root: Path = ROOT) -> dict:
    rules = load(root / 'research/e5/autonomy/transition_rules.json')
    require([current, target] in rules['edges'], 'illegal transition/stage skipping')
    require(target == 'READY_TO_FREEZE' and current == 'DRAFT', 'task ceiling: actual freeze/execution prohibited')
    evidence = verify_state(root)
    require(evidence['status'] == 'READY_TO_FREEZE', 'scientific gates BLOCKED')
    return {'from': current, 'to': target, 'evidence_hash': digest(evidence)}


def verify_identities(root: Path = ROOT) -> None:
    value = load(root / 'research/e5/autonomy/design_identities.json')
    require(value['status'] == 'CANDIDATE_BINDING_NOT_PROTOCOL_FREEZE', 'identity is not an executed freeze')
    require(value['released_source'] == '6a6f2053dd168d74aa97533ad901af47a7a5023a', 'released source drift')
    require(set(value['sources']) == IDENTITY_SOURCES, 'identity coverage')
    declared_policy = load(root / 'research/v042_development/runtime_identities.json')['assurance_policy']
    require(value['policy_hash'] == declared_policy['policy_hash'] and value['policy_version'] == declared_policy['version'], 'policy identity metadata drift')
    # Require exact expected source membership against the immutable baseline; a
    # removed hash cannot silently exempt a source from checking.
    baseline = subprocess.check_output(['git', 'show', f"{value['released_source']}:requirements.lock"], cwd=root)
    require(hashlib.sha256(baseline.replace(b'\r\n', b'\n')).hexdigest() == value['sources']['requirements.lock'], 'lock base identity')
    for name, expected in value['sources'].items():
        path = safe_path(root, name)
        require(path.is_file() and file_hash(path) == expected, f'identity drift: {name}')
        original = subprocess.check_output(['git', 'show', f"{value['released_source']}:{name}"], cwd=root)
        original = original if path.suffix == '.pkl' else original.replace(b'\r\n', b'\n')
        require(hashlib.sha256(original).hexdigest() == expected, f'rehashed replacement of released identity: {name}')
    history = load(root / 'research/e5/autonomy/historical_integrity.json')
    require(history['base'] == value['released_source'], 'historical base drift')
    tree = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', history['base'], 'research'], cwd=root, text=True).splitlines()
    expected_paths = {p for p in tree if not p.startswith(('research/e5/', 'research/e5_readiness/'))}
    require(set(history['files']) == expected_paths, 'historical manifest coverage drift')
    for name, expected in history['files'].items():
        actual = subprocess.check_output(['git', 'hash-object', '--path', name, name], cwd=root, text=True).strip()
        original = subprocess.check_output(['git', 'rev-parse', f"{history['base']}:{name}"], cwd=root, text=True).strip()
        require(actual == expected == original, f'historical content drift: {name}')


def validate_selection(evidence: str, *, outcomes_accessible: bool = False) -> None:
    require(outcomes_accessible is False and evidence in {'APPROVED_HISTORICAL_DEVELOPMENT', 'OUTCOME_BLIND_DESIGN', 'SYNTHETIC_ENGINEERING'},
            'E5 evidence cannot influence selection')


def validate_packet(packet: dict, *, expected_schema_hash: str) -> None:
    fields = {'case_id', 'cik', 'accession', 'schema_hash', 'prediction_cutoff', 'sources'}
    require(set(packet) == fields and packet['schema_hash'] == expected_schema_hash, 'packet schema drift/unknown fields')
    require(isinstance(packet['case_id'], str) and bool(packet['case_id']), 'one exact case ID required')
    require(re.fullmatch(r'[0-9]{10}', packet['cik']) is not None
            and re.fullmatch(r'[0-9]{10}-[0-9]{2}-[0-9]{6}', packet['accession']) is not None, 'CIK/accession')
    cutoff = datetime.fromisoformat(packet['prediction_cutoff'])
    require(cutoff.tzinfo is not None, 'timezone required')
    require(isinstance(packet['sources'], list) and bool(packet['sources']), 'source records required')
    for source in packet['sources']:
        require(set(source) == {'company', 'cik', 'accession', 'filing_timestamp', 'period', 'source', 'unit', 'source_hash', 'available_at'}, 'material provenance schema')
        require(all(isinstance(x, str) and x for x in source.values()), 'material provenance values')
        require(source['cik'] == packet['cik'] and source['accession'] == packet['accession'], 'source identity substitution')
        for field in ('available_at', 'filing_timestamp'):
            timestamp = datetime.fromisoformat(source[field])
            require(timestamp.tzinfo is not None and timestamp <= cutoff, 'future timestamp leakage')
        require(re.fullmatch(r'[a-f0-9]{64}', source['source_hash']) is not None, 'source hash')


def shared_proposals(proposals: dict) -> str:
    require(set(proposals) == {'S2', 'S3', 'S4'}, 'exactly three shared proposals required')
    hashes = []
    for proposal in proposals.values():
        require(set(proposal) == {'case_id', 'input_hash', 'producer_hash', 'risk_score', 'proposed_decision'}, 'proposal schema')
        require(isinstance(proposal['case_id'], str) and bool(proposal['case_id']), 'case ID')
        for name in ('input_hash', 'producer_hash'):
            require(re.fullmatch(r'[a-f0-9]{64}', proposal[name]) is not None, 'proposal identity')
        score = proposal['risk_score']
        require(score is None or type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100, 'invalid proposal score')
        require(proposal['proposed_decision'] in {'PASS', 'FLAG', 'REVIEW', 'ABSTAIN'}, 'proposal decision')
        hashes.append(digest(proposal))
    require(len(set(hashes)) == 1, 'S2/S3/S4 proposal mismatch')
    return hashes[0]


def assert_disjoint(candidates: set[str], historical: set[str]) -> None:
    require(all(re.fullmatch(r'[0-9]{10}', x) is not None for x in candidates | historical), 'company identity normalization')
    require(not candidates & historical, 'company overlap')


def verify_exclusions(candidates: set[str], historical: set[str], previous_path: Path) -> None:
    require(previous_path.is_file(), 'missing historical exclusion input previous_270')
    require(hashlib.sha256(previous_path.read_bytes()).hexdigest() == 'd73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603', 'previous_270 not exact original')
    assert_disjoint(candidates, historical)
    original = json.loads(previous_path.read_text())
    require(isinstance(original, list) and len(original) == 270 and all(isinstance(x, str) and x.isdigit() for x in original), 'original exclusion schema requires review')
    previous = {x.zfill(10) for x in original}
    known = load(DIRECTORY / 'historical_exclusions.json')
    mandatory = load(ROOT / known['strong_reference_2000']['path'])
    require(file_hash(ROOT / known['strong_reference_2000']['path']) == known['strong_reference_2000']['sha256'], 'historical exclusion identity')
    all_prior = historical | previous | {x['cik'] for x in mandatory['rows']}
    require(not candidates & all_prior, 'company overlap')
    # Actual enumeration is deliberately not provided by this library.


def outcome_label(status: str, label: Any) -> int | None:
    if status != 'VERIFIED':
        require(label is None, 'missing outcome coerced to negative')
        require(status in {'REQUIRES_REVIEW', 'INSUFFICIENT_DATA'}, 'unknown endpoint status')
        return None
    require(type(label) is int and label in (0, 1), 'verified label must be binary integer')
    return label


def amendment(record: dict, stage: str) -> dict:
    required = {'id', 'utc_timestamp', 'reason', 'changes', 'old_hashes', 'new_hashes',
                'cohort_visible', 'predictions_existed', 'outcomes_accessible', 'scientific_impact'}
    require(set(record) == required, 'amendment schema')
    states = load(DIRECTORY / 'transition_rules.json')['lifecycle']
    require(stage in states, 'unknown stage')
    index = states.index(stage)
    for name, minimum in [('cohort_visible', 'COHORT_FROZEN'), ('predictions_existed', 'PREDICTIONS_FROZEN'), ('outcomes_accessible', 'OUTCOMES_UNLOCKED')]:
        require(type(record[name]) is bool and (index < states.index(minimum) or record[name]), 'amendment hides exposure')
    offset = datetime.fromisoformat(record['utc_timestamp']).utcoffset()
    require(offset is not None and offset.total_seconds() == 0, 'amendment UTC timestamp')
    require(record['id'] and record['reason'] and record['scientific_impact'], 'amendment rationale')
    require(isinstance(record['changes'], list) and bool(record['changes']), 'amendment changes')
    require(set(record['old_hashes']) == set(record['new_hashes']) and bool(record['old_hashes']), 'amendment artifact linkage')
    for hashes in (record['old_hashes'], record['new_hashes']):
        require(all(isinstance(v, str) and re.fullmatch(r'[a-f0-9]{64}', v) for v in hashes.values()), 'amendment hashes')
    scientific = bool(SCIENTIFIC_FIELDS & set(record['changes']))
    disposition = 'INVALIDATED' if scientific and (record['outcomes_accessible'] or record['predictions_existed'] or index >= states.index('PREDICTIONS_FROZEN')) else 'NEW_PROTOCOL_IDENTITY_REQUIRED' if scientific and index >= states.index('PROTOCOL_FROZEN') else 'REVIEW_REQUIRED'
    return {'record_hash': digest(record), 'confirmatory_identity': disposition}


def primary_claim(*, family: str, primary_passed: bool) -> None:
    require(family == 'PRIMARY' and primary_passed is True, 'post-hoc/failed primary cannot support a primary claim')
