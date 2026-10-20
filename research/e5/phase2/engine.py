"""Executable, hash-chained Phase-II stages. No outcome-bearing input before unlock.

This controller executes supplied scientific prerequisites. It never manufactures
an exclusion list, isolation attestation, independent reviewer, source or label.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from finrisk.metrics import calculate_metrics

from ..execution.core import (
    FrozenProposalProducer,
    digest,
    file_hash,
    freeze_json,
    read_json,
    require,
    timestamp,
    utcnow,
    validate_features,
    verify_certificate_binding,
    verify_files,
)
from ..execution.qualification import qualify_s0
from .cohort import prove_exclusions, select
from .endpoint import extract as extract_outcomes
from .inference import analyze, specification, validate_spec
from .producer import FIELDS
from .sources import eligible_universe, extract_packets
from .study import REFERENCE, CalibratedStudyProducer, band, fanout

ORDER = ('protocol', 'cohort', 'features', 'predictions', 'pre-outcome-audit',
         'outcome-unlock', 'outcomes', 'analysis', 'sensitivities', 'final-report')


def arm(decision, score):
    return {'decision': decision, 'automated': decision in {'PASS', 'FLAG'}, 'score': score}


class Execution:
    def __init__(self, root: Path, directory: Path):
        self.root, self.directory = root.resolve(), directory.resolve()
        require(subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip() == 'E5-experiment',
                'Phase-II execution is authorized only on E5-experiment')
        self.producer = CalibratedStudyProducer(root)

    def load(self, stage):
        path = self.directory/(stage+'.json')
        require(path.is_file(), 'required stage absent: '+stage)
        value = read_json(path)
        require(value['payload_hash'] == digest(value['payload']), 'stage payload mutated: '+stage)
        if stage != ORDER[0]:
            previous = ORDER[ORDER.index(stage)-1]
            require(value['previous_hash'] == digest(self.load(previous)), 'stage chain changed')
        return value

    def write(self, stage, payload):
        previous = None if stage == ORDER[0] else digest(self.load(ORDER[ORDER.index(stage)-1]))
        path = self.directory/(stage+'.json')
        if path.exists():
            old = self.load(stage)
            require(old['payload_hash'] == digest(payload), 'immutable stage cannot be replaced')
            return old
        value = {'stage': stage, 'created_at': utcnow(), 'payload': payload,
                 'payload_hash': digest(payload), 'previous_hash': previous,
                 'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()}
        freeze_json(path, value)
        return value

    def protocol(self, qualification: Path, power: Path, endpoint_qualification: Path):
        q, p, endpoint = map(read_json, (qualification, power, endpoint_qualification))
        spec = specification(self.root)
        require(q['status'] == 'PASSED' and q['analysis_identity'] == digest(spec)
                and len(q['configurations']) >= 13
                and all(c['replicates'] >= 5000 and not c['material_anti_conservatism'] for c in q['configurations']),
                'complete canonical inference qualification required')
        require(p['analysis_identity'] == digest(spec) and p['identity']['producer_identity'] == self.producer.identity,
                'joint power must bind exact final inference and producer')
        require(endpoint['status'] == 'PASSED' and endpoint['adapter_sha256'] == file_hash(self.root/'research/e5/phase2/endpoint.py'),
                'endpoint extraction qualification required')
        bindings = {str(path.relative_to(self.root)): file_hash(path)
                    for path in sorted((self.root/'research/e5/phase2').glob('*.py'))}
        require(not subprocess.check_output(['git', 'status', '--porcelain', '--', *bindings], cwd=self.root, text=True),
                'commit scientific implementation before protocol freeze')
        replay = qualify_s0(self.root)
        source_path = self.root/'research/e5/phase2/qualification/known-historical-source-path-avnet.json'
        source_proof = read_json(source_path)
        require(source_proof['producer_identity'] == self.producer.identity
                and source_proof['E5_outcomes_accessed'] is False
                and source_proof['E5_predictions_generated'] == 0, 'matched real-source engineering qualification required')
        verify_certificate_binding(source_proof['fanout']['certificate'],
                                   proposal_hash=source_proof['proposal']['proposal_hash'], policy=self.producer.policy)
        payload = {'study_id': 'E5-STRUCTURED-NUMERIC-PHASE-II', 'scope': 'INTERNAL_NUMERIC_STUDY_NOT_LLM_OR_RELEASED_AGENT_VALIDATION',
                   'producer': self.producer.identity, 'study_policy': self.producer.policy.to_dict(),
                   'study_fusion_policy': self.producer.fusion_policy, 'production_policy_changed': False,
                   'analysis': spec, 'qualification': q, 'power': p, 'endpoint_qualification': endpoint,
                   'source_path_qualification_sha256': file_hash(source_path),
                   'source_path_qualification_scope': source_proof['scope'],
                   'primary_comparisons': {'P1': 'S4 minus S1 authorization benefit with coverage NI and absolute floor',
                                           'P2': 'S4 minus S3 authorization benefit with coverage NI and absolute floor'},
                   'arms': {'S0': 'FROZEN_STRONG_TABULAR_UNCONDITIONAL_THRESHOLD_0_5',
                            'S1': 'EXACT_S0_SCORE_FIXED_REVIEW_BAND', 'S2': 'ONCE_GENERATED_CALIBRATED_NUMERIC_PROPOSAL',
                            'S3': 'SAME_PROPOSAL_EVIDENCE_ONLY_ROUTING', 'S4': 'SAME_PROPOSAL_FULL_ASSURANCE_AND_VERIFIED_CERTIFICATE'},
                   'feature_schema_hash': digest(self.producer.raw.schema),
                   'assurance_source_hashes': {str(f.relative_to(self.root)): file_hash(f)
                                              for f in (self.root/'backend/finrisk/assurance').glob('*.py')},
                   'certificate_schema_hash': file_hash(self.root/'backend/finrisk/enterprise/decision_bundle.py'),
                   'eligibility': 'ORIGINAL_10K_FIRST_PER_CIK_EXCLUDE_SIC_6000_6999_AND_UNKNOWN_SIC_SAME_ACCESSION_INPUTS_ONLY',
                   'runtime': {'python': __import__('sys').version, 'requirements_lock_sha256': file_hash(self.root/'requirements.lock')},
                   'prospective_execution_gate': 'TIMELY_INDEX_FILING_EXTRACTION_AND_INDEPENDENT_OPERATIONAL_OUTCOME_ISOLATION_MUST_BE_PROVEN_BEFORE_ENROLLMENT',
                   'S0_replay': replay, 'S1': {'pass_below': .35, 'flag_at_or_above': .65},
                   'bindings': bindings, 'reference_sha256': file_hash(self.root/REFERENCE),
                   'endpoint': 'deterministic_forward_outcome_rule_v1_WITH_ACCESSION_TIMING_AND_STANDALONE_FCF_ADAPTER',
                   'historical_nonoverlap': 'EXACT_PREVIOUS_270_PLUS_IMMUTABLE_KNOWN_HISTORICAL_SOURCES_BEFORE_ENROLLMENT',
                   'retrospective_window': 'LATEST_COMPLETE_QUARTER_WITH_12M_ELAPSED_AND_AUTHORITATIVE_OBSERVABILITY; EXPAND_BACKWARD_WHOLE_QUARTERS_UNTIL_N_OR_SOURCE_EXHAUSTION',
                   'N': p['selected_n'], 'underpower_rule': 'LARGEST_VALID_MATURE_COHORT_NO_THRESHOLD_REDUCTION',
                   'selection': 'SHA256([salt,CIK,accession]), first original 10-K per CIK, no discretionary strata',
                   'selection_salt_derivation': 'SHA256([protocol_payload_hash,released_source,E5-company-order-v1])',
                   'prospective_window': 'FIRST_12_MONTHS_STARTING_NEXT_UTC_QUARTER_AFTER_FREEZE',
                   'minimum_paired_verified_positive_events': 100,
                   'nonverified_outcomes': 'NULL_LABEL_EXCLUDED_FROM_PRIMARY_ERROR_DENOMINATOR_REPORT_ATTRITION_AND_BOUNDS',
                   'claim_rule': 'Primary success requires all frozen utility inequalities, estimable paired BCa, IUT and Holm. N=0 means Assurance benefit was not evaluated.',
                   'outcome_values_used': False}
        return self.write('protocol', payload)

    def check_protocol(self):
        p = self.load('protocol')['payload']
        verify_files(self.root, p['bindings'])
        require(p['producer'] == self.producer.identity, 'frozen producer identity changed')
        require(p['study_policy'] == self.producer.policy.to_dict(), 'study policy changed')
        require(p['reference_sha256'] == file_hash(self.root/REFERENCE), 'reference changed')
        validate_spec(self.root, p['analysis'])
        return p

    def cohort(self, universe: Path, previous: Path, availability: Path):
        p = self.check_protocol()
        excluded, proof = prove_exclusions(self.root, previous)
        source_universe = read_json(universe)
        require(source_universe['outcome_values_used'] is False, 'outcome-driven universe forbidden')
        catalog = read_json(availability)
        require(bool(catalog['evidence_files']), 'authoritative availability evidence files required')
        verify_files(self.root, catalog['evidence_files'])
        for record in catalog['companies']:
            require(record['authoritative_evidence_url'].startswith('https://www.sec.gov/'), 'authoritative observability evidence required')
            require(record['source_catalog_sha256'] in catalog['evidence_files'].values(), 'availability catalog must bind immutable official metadata')
        salt = digest([digest(p), 'v0.4.2', 'E5-company-order-v1'])
        payload = select(source_universe, excluded, n=p['N'], salt=salt, availability=catalog)
        payload['historical_nonoverlap_proof'] = proof
        return self.write('cohort', payload)

    def features(self, manifests: list[Path]):
        self.check_protocol()
        cohort = self.load('cohort')['payload']['cases']
        require(not (self.directory/'outcome-inputs').exists(), 'outcome inputs accessible before predictions')
        bundles = extract_packets(self.root, cohort, manifests, reference_hash=file_hash(self.root/REFERENCE))
        require(len(bundles) == len(cohort), 'feature cohort incomplete')
        for bundle in bundles:
            packet = bundle['packet']
            validate_features(packet, schema_hash=digest(self.producer.raw.schema),
                              code_hash=file_hash(self.root/'research/e5/phase2/sources.py'))
        return self.write('features', {'bundles': bundles, 'source_manifest_paths': [str(p.resolve()) for p in manifests]})

    def predictions(self):
        self.check_protocol()
        require(not (self.directory/'outcome-inputs').exists(), 'outcome inputs accessible before predictions')
        if (self.directory/'predictions.json').exists():
            return self.load('predictions')
        features = self.load('features')['payload']
        cases = {c['cik']: c for c in self.load('cohort')['payload']['cases']}
        from research.strong_tabular_reference.artifact import predict_scores
        manifest = read_json(self.root/'research/strong_tabular_reference/artifacts/artifact_manifest.json')
        names = manifest['feature_contract']['ordered_feature_names']
        rows = []
        for bundle in features['bundles']:
            packet = bundle['packet']
            feature = packet['features']
            current = {k: feature['current__'+k] for k in FIELDS}
            previous = {k: feature['previous__'+k] for k in FIELDS}
            metrics = {k: v.value for k, v in calculate_metrics(current, feature['fiscal_year'], previous).items()}
            values = [float(metrics.get(n.removeprefix('observed__')) is not None) if n.startswith('observed__')
                      else metrics.get(n, float('nan')) for n in names]
            score0 = predict_scores([values], ordered_feature_names=names)[0]
            proposal = FrozenProposalProducer(self.producer.identity, self.producer).run(
                packet, self.directory/'proposals'/(packet['case_id']+'.json'))
            consumers = fanout(self.producer, proposal, bundle, case=cases[packet['cik']],
                               manifests=[Path(s) for s in features['source_manifest_paths']])
            arms = {'S0': arm('FLAG' if score0 >= .5 else 'PASS', score0), 'S1': arm(band(score0), score0)}
            for name in ('S2', 'S3', 'S4'):
                arms[name] = arm(consumers[name], proposal['normalized_risk_score'])
            rows.append({'cik': packet['cik'], 'case_id': packet['case_id'], 'arms': arms,
                         'proposal': proposal, 'certificate': consumers['certificate']})
        require(len(rows) == len(cases), 'missing predictions')
        return self.write('predictions', {'rows': rows, 'proposal_mismatch_count': 0, 'all_certificates_verified': True})

    def pre_outcome_audit(self, isolation_receipt: Path):
        self.check_protocol()
        require(not (self.directory/'outcome-inputs').exists(), 'outcome inputs already accessible')
        receipt = read_json(isolation_receipt)
        require(receipt['prediction_manifest_sha256'] == digest(self.load('predictions')), 'isolation receipt belongs to another prediction freeze')
        require(receipt['mechanism'] in {'SEPARATE_RUNNER_WITH_SEPARATE_SOURCE_MOUNT', 'OS_ENFORCED_UNMOUNTED_OUTCOME_VOLUME'},
                'path assertion alone is not operational isolation')
        verify_files(self.root, receipt['enforcement_evidence'])
        require(bool(receipt['enforcement_evidence']) and receipt['outcome_reader_identity'] != receipt['prediction_runner_identity'],
                'independent operational enforcement evidence required')
        require(timestamp(receipt['verified_at']) >= timestamp(self.load('predictions')['created_at']), 'stale isolation receipt')
        for row in self.load('predictions')['payload']['rows']:
            verify_certificate_binding(row['certificate'], proposal_hash=row['proposal']['proposal_hash'], policy=self.producer.policy)
        return self.write('pre-outcome-audit', {'isolation_receipt': receipt, 'status': 'PASSED', 'outcomes_accessed': False})

    def unlock(self):
        self.check_protocol()
        audit = self.load('pre-outcome-audit')['payload']
        require(audit['status'] == 'PASSED', 'pre-outcome audit unsatisfied')
        return self.write('outcome-unlock', {'authorized_at': utcnow(), 'prediction_manifest_sha256': digest(self.load('predictions'))})

    def outcomes(self, manifests: list[Path], *, as_of: str):
        self.check_protocol()
        self.load('outcome-unlock')
        values = extract_outcomes(self.load('features')['payload']['bundles'], manifests, as_of=as_of)
        require({r['case_id'] for r in values['outcomes']} ==
                {r['case_id'] for r in self.load('predictions')['payload']['rows']}, 'unpaired outcomes')
        return self.write('outcomes', values)

    def paired_rows(self):
        labels = {r['case_id']: r for r in self.load('outcomes')['payload']['outcomes']}
        return [r | {'outcome': labels[r['case_id']]} for r in self.load('predictions')['payload']['rows']]

    def analysis(self):
        p = self.check_protocol()
        rows = self.paired_rows()
        result = analyze(self.root, rows, p['analysis'], p['qualification'])
        positives = sum(r['outcome']['status'] == 'VERIFIED' and r['outcome']['label'] == 1 for r in rows)
        if positives < p['minimum_paired_verified_positive_events']:
            result['exploratory_kernel_result'] = result['comparisons']
            result['comparisons'] = {name: {'result': 'NOT_ESTIMABLE', 'reason': 'FEWER_THAN_100_PAIRED_VERIFIED_POSITIVES'} for name in ('P1', 'P2')}
            result['family_success'] = False
        result['paired_verified_positive_events'] = positives
        return self.write('analysis', result)

    def sensitivities(self):
        self.check_protocol()
        from .reporting import describe
        return self.write('sensitivities', describe(self.paired_rows()))

    def final_report(self):
        self.check_protocol()
        analysis = self.load('analysis')['payload']
        secondary = self.load('sensitivities')['payload']
        result = {'status': 'E5R_COMPLETE', 'classification': 'INTERNAL_STRUCTURED_NUMERIC_EMPIRICAL_STUDY',
                  'eligible_n': analysis['eligible_n'], 'verified_n': analysis['verified_n'],
                  'family_success': analysis['family_success'], 'analysis': analysis, 'secondary': secondary,
                  'limitations': ['No narrative or external provider model evaluated.',
                                  'Calibration and reference are internal development artifacts.',
                                  'Retrospective accession reconstruction is not prospective production validation.']}
        return self.write('final-report', result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=ORDER+('build-universe',))
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--manifest', action='append', type=Path, default=[])
    parser.add_argument('--previous-270', type=Path)
    parser.add_argument('--availability', type=Path)
    parser.add_argument('--power', type=Path)
    parser.add_argument('--endpoint-qualification', type=Path)
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--as-of', default=utcnow())
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    run = Execution(root, args.run)
    if args.stage == 'build-universe':
        result = eligible_universe(args.manifest, start=args.start, end=args.end, as_of=args.as_of)
        freeze_json(args.run/'universe.json', result)
    elif args.stage == 'protocol':
        result = run.protocol(args.input, args.power, args.endpoint_qualification)
    elif args.stage == 'cohort':
        result = run.cohort(args.input, args.previous_270, args.availability)
    elif args.stage == 'features':
        result = run.features(args.manifest)
    elif args.stage == 'predictions':
        result = run.predictions()
    elif args.stage == 'pre-outcome-audit':
        result = run.pre_outcome_audit(args.input)
    elif args.stage == 'outcome-unlock':
        result = run.unlock()
    elif args.stage == 'outcomes':
        result = run.outcomes(args.manifest, as_of=args.as_of)
    else:
        result = getattr(run, args.stage.replace('-', '_'))()
    print(json.dumps({'stage': args.stage, 'artifact_hash': digest(result)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
