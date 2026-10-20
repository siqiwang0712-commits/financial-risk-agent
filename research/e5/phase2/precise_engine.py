"""Exact-clock execution extending the immutable common method core."""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..execution.core import (
    FrozenProposalProducer,
    digest,
    file_hash,
    freeze_json,
    read_json,
    require,
    timestamp,
    validate_features,
    verify_files,
)
from .cohort import prove_exclusions, select
from .engine import Execution, arm
from .precise_arms import fanout
from .precise_endpoint import extract as extract_outcomes
from .precise_source import extract_packets, resolve_universe
from .study import REFERENCE, band


class PreciseExecution(Execution):
    def write(self, stage, payload):
        if stage == 'protocol':
            live = read_json(self.root/'research/e5/phase2/qualification/live-source-qualified.json')
            isolation = read_json(self.root/'research/e5/phase2/qualification/precise-isolation-qualified.json')
            require(live['status'] == 'PASSED' and isolation['status'] == 'PASSED', 'exact-clock source/runtime qualification required')
            require(live['source_sha256'] == file_hash(self.root/'research/e5/phase2/live_source.py'), 'live source qualification drift')
            require(isolation['producer_identity'] == self.producer.identity, 'precise runtime producer mismatch')
            require(isolation['Dockerfile_sha256'] == file_hash(self.root/'research/e5/phase2/Dockerfile.precise-prediction'), 'qualified role image build definition drift')
            for name, sha in isolation['adapter_source_hashes'].items():
                require(file_hash(self.root/name) == sha, 'qualified precise source/worker drift')
            payload = payload | {
                'study_id': 'E5-STRUCTURED-NUMERIC-PRIMARY-INDEX-CLOCK',
                'common_core_parent_sha256': file_hash(self.root/'research/e5/phase2/e5p-core/protocol.json'),
                'acceptance_clock': 'ORIGINAL_EDGAR_INDEX_SECOND_RESOLUTION_EASTERN_TO_UTC',
                'archive_minute_timestamp': 'RETAINED_AS_PROVENANCE_NEVER_USED_AS_EXACT_CLOCK',
                'api_acceptanceDateTime': 'NOT_A_CLOCK_AUTHORITY; FAILED_COMPARISON_PRESERVED',
                'prediction_runtime': isolation,
                'source_qualification': live,
                'retrospective_source': 'ORIGINAL_FSDS_VALUES_WITH_ORIGINAL_INDEX_CLOCK',
                'prospective_source': 'ORIGINAL_ACCESSION_EXTRACTED_XBRL_INSTANCE_NO_LATEST_API_VALUES',
                'source_observability': 'R_RETAINS_FSDS_PRIMARY_STATEMENT_FIELDS; P_ORIGINAL_INSTANCE_MAY_INCLUDE_ADDITIONAL_VALID_FACTS; REPORT_SEPARATELY_NO_R_P_POOLING',
                'prospective_deadline_seconds': 86400,
                'prospective_enrollment': 'ROLLING_FIRST_ORIGINAL_10K_PER_CIK_FROM_FROZEN_OFFICIAL_FEED_SNAPSHOTS',
                'prospective_source_frame': 'FIRST_1000_OFFICIAL_CURRENT_10K_FEED_ENTRIES_PER_POLL',
                'prospective_poll_cadence': 'AT_LEAST_HOURLY_WHILE_WINDOW_OPEN; SNAPSHOT_GAPS_AND_MISSED_DEADLINES_REPORTED',
                'prospective_failed_cases': 'RETAINED_PENDING_NO_SILENT_REGENERATION_OR_POST_OUTCOME_EXCLUSION',
                'endpoint_clock_adapter_sha256': file_hash(self.root/'research/e5/phase2/precise_endpoint.py'),
                'live_packet_extractor_sha256': file_hash(self.root/'research/e5/phase2/live_source.py'),
                'archive_clock_extractor_sha256': file_hash(self.root/'research/e5/phase2/precise_source.py')}
            payload['bindings'] = dict(payload['bindings']) | {
                'research/e5/run_e5.py': file_hash(self.root/'research/e5/run_e5.py'),
                'research/e5/phase2/Dockerfile.precise-prediction': file_hash(self.root/'research/e5/phase2/Dockerfile.precise-prediction')}
        return super().write(stage, payload)

    def check_protocol(self):
        payload = super().check_protocol()
        verify_files(self.root, payload['assurance_source_hashes'])
        require(file_hash(self.root/'backend/finrisk/enterprise/decision_bundle.py') == payload['certificate_schema_hash'],
                'frozen certificate implementation drift')
        return payload

    def cohort(self, universe: Path, previous: Path, availability: Path):
        p = self.check_protocol()
        excluded, proof = prove_exclusions(self.root, previous)
        parent = read_json(universe)
        require(parent['outcome_values_used'] is False, 'outcome-driven universe forbidden')
        precise = resolve_universe(parent, self.root/'.runtime/e5-index-clock')
        catalog = read_json(availability)
        verify_files(self.root, catalog['evidence_files'])
        # Date-only availability evidence uses a two-day interior buffer. Verify
        # it remains strictly inside each newly resolved second-resolution window.
        by_cik = {c['cik']: c for c in precise['candidates']}
        catalog = dict(catalog) | {'companies': [dict(c) for c in catalog['companies']]}
        from finrisk.sec_bulk import add_twelve_months
        for item in catalog['companies']:
            if not item['window_fully_observable'] or item['cik'] not in by_cik:
                continue
            case = by_cik[item['cik']]
            evidence = read_json(self.root/'research/e5/phase2/sources/outcome-availability'/(item['cik']+'.json'))
            require(evidence['index_accession'] == case['accession'], 'availability accession substitution')
            lo, hi = evidence['conservative_interior_filed_dates']
            require(timestamp(case['accepted']).date().isoformat() < lo
                    and hi < add_twelve_months(timestamp(case['accepted'])).date().isoformat(),
                    'availability evidence lies outside exact index window')
        salt = digest([digest(p), 'v0.4.2', 'E5-company-order-v1'])
        payload = select(precise, excluded, n=p['N'], salt=salt, availability=catalog)
        payload.update(historical_nonoverlap_proof=proof, precise_candidate_universe=precise,
                       clock_extractor_sha256=file_hash(self.root/'research/e5/phase2/precise_source.py'))
        return self.write('cohort', payload)

    def features(self, manifests: list[Path]):
        self.check_protocol()
        self.source_manifest_paths = list(manifests)
        cohort = self.load('cohort')['payload']['cases']
        require(not (self.directory/'outcome-inputs').exists(), 'outcome inputs accessible before predictions')
        bundles = extract_packets(self.root, cohort, manifests, reference_hash=file_hash(self.root/REFERENCE))
        require(len(bundles) == len(cohort), 'feature cohort incomplete')
        for bundle in bundles:
            packet = bundle['packet']
            validate_features(packet, schema_hash=digest(self.producer.raw.schema),
                              code_hash=file_hash(self.root/'research/e5/phase2/precise_source.py'))
        return self.write('features', {'bundles': bundles, 'source_manifests': [{'manifest': read_json(p), 'sha256': file_hash(p)} for p in manifests]})

    def predictions(self, manifests=None):
        protocol = self.check_protocol()
        require(not (self.directory/'outcome-inputs').exists(), 'outcome inputs accessible before predictions')
        if (self.directory/'predictions.json').exists():
            return self.load('predictions')
        features = self.load('features')['payload']
        source_paths = list(manifests or getattr(self, 'source_manifest_paths', []))
        live = all(b['evidence']['source_mode'] == 'LIVE_SEC_EXACT_INDEX_ACCESSION' for b in features['bundles'])
        require(live or source_paths and sorted(file_hash(p) for p in source_paths) ==
                sorted(s['sha256'] for s in features['source_manifests']), 'original feature source manifests must be supplied for verification')
        cases = {c['cik']: c for c in self.load('cohort')['payload']['cases']}
        manifest = read_json(self.root/'research/strong_tabular_reference/artifacts/artifact_manifest.json')
        from .isolated import call as isolated_call
        image = protocol['prediction_runtime']['image_id']
        subprocess.check_output(['docker', 'image', 'inspect', image], text=True)
        rows = []
        for bundle in features['bundles']:
            packet = bundle['packet']
            s0_identity = {'model': 'StrongTabularReference-v1', 'fitted_identity': manifest['hashes']['fitted_artifact_hash']}
            s0_result, s0_receipt = isolated_call(image, {'role': 'S0', 'feature': packet}, s0_identity)
            score0 = s0_result['score']
            receipt_path = self.directory/'isolation-receipts'/(packet['case_id']+'.json')
            def produce_once(value, output_receipt=receipt_path):
                result, isolation_receipt = isolated_call(image, value, self.producer.identity)
                freeze_json(output_receipt, isolation_receipt)
                return result
            proposal = FrozenProposalProducer(self.producer.identity, produce_once).run(
                packet, self.directory/'proposals'/(packet['case_id']+'.json'))
            isolation_receipt = read_json(receipt_path)
            require(isolation_receipt['input_hash'] == digest(packet) and isolation_receipt['image_id'] == image,
                    'prediction isolation receipt mismatch')
            consumers = fanout(self.producer, proposal, bundle, case=cases[packet['cik']],
                               manifests=source_paths, image_id=image)
            freeze_json(self.directory/'isolation-receipts'/(packet['case_id']+'.s0.json'), s0_receipt)
            freeze_json(self.directory/'isolation-receipts'/(packet['case_id']+'.admission.json'), consumers['admission_isolation_receipt'])
            arms = {'S0': arm('FLAG' if score0 >= .5 else 'PASS', score0), 'S1': arm(band(score0), score0)}
            for name in ('S2', 'S3', 'S4'):
                arms[name] = arm(consumers[name], proposal['normalized_risk_score'])
            if cases[packet['cik']].get('prediction_deadline'):
                from ..execution.core import utcnow
                require(timestamp(utcnow()) <= timestamp(cases[packet['cik']]['prediction_deadline']),
                        'prospective deadline exceeded: actual proposal preserved, case remains pending, no silent regeneration or exclusion')
            rows.append({'cik': packet['cik'], 'case_id': packet['case_id'], 'arms': arms,
                         'proposal': proposal, 'isolation_receipt': isolation_receipt,
                         'S0_isolation_receipt': s0_receipt, 'admission_isolation_receipt': consumers['admission_isolation_receipt'], 'certificate': consumers['certificate']})
        require(len(rows) == len(cases), 'missing predictions')
        return self.write('predictions', {'rows': rows, 'proposal_mismatch_count': 0, 'all_certificates_verified': True})

    def outcomes(self, manifests: list[Path], *, as_of: str):
        self.check_protocol()
        self.load('outcome-unlock')
        values = extract_outcomes(self.load('features')['payload']['bundles'], manifests, as_of=as_of)
        require({r['case_id'] for r in values['outcomes']} ==
                {r['case_id'] for r in self.load('predictions')['payload']['rows']}, 'unpaired outcomes')
        return self.write('outcomes', values)


    def pre_outcome_audit(self, isolation_receipt=None):
        self.check_protocol()
        predictions = self.load('predictions')
        features = {b['packet']['case_id']: b['packet'] for b in self.load('features')['payload']['bundles']}
        evidence, containers = {}, []
        for row in predictions['payload']['rows']:
            packet = features[row['case_id']]
            expected = {
                '': digest(packet),
                '.s0': digest({'role': 'S0', 'feature': packet}),
                '.admission': digest({'role': 'ADMISSION', 'feature': packet, 'proposal': row['proposal'],
                                      'paths': row['certificate']['evidence_paths'],
                                      'source_hash': packet['sources'][0]['sha256']})}
            keys = {'': 'isolation_receipt', '.s0': 'S0_isolation_receipt', '.admission': 'admission_isolation_receipt'}
            for suffix, key in keys.items():
                receipt = row[key]
                require(receipt['input_hash'] == expected[suffix]
                        and receipt['image_id'] == self.load('protocol')['payload']['prediction_runtime']['image_id']
                        and receipt['network_mode'] == 'none' and receipt['read_only_rootfs'] is True
                        and not receipt['host_binds'] and receipt['exit_code'] == 0,
                        'S0/proposal/admission isolation is not fully enforced')
                require(all(m.get('Type') == 'tmpfs' and not m.get('Source') for m in receipt['host_mounts'] or []),
                        'host volume leaked into a computation role')
                path = self.directory/'isolation-receipts'/(row['case_id']+suffix+'.json')
                require(read_json(path) == receipt, 'computation receipt changed')
                evidence[str(path.relative_to(self.root))] = file_hash(path)
                containers.append(receipt['container_id'])
            require(row['arms']['S4']['decision'] == row['certificate']['final_decision'], 'final decision/certificate mismatch')
        require(bool(containers), 'no completed real isolated computation roles')
        from ..execution.core import utcnow
        combined = {'prediction_manifest_sha256': digest(predictions),
                    'mechanism': 'DOCKER_FEATURE_ONLY_NO_NETWORK_OR_HOST_VOLUMES',
                    'enforcement_evidence': evidence, 'prediction_runner_identity': 'docker:'+digest(containers),
                    'outcome_reader_identity': 'OUTCOME_STAGE_NOT_STARTED_NO_OUTCOME_INPUT_VOLUME_MOUNTED',
                    'verified_at': utcnow(), 'independent_human_review_claimed': False,
                    'all_computation_roles': ['S0', 'SHARED_RAW_PROPOSAL', 'EVIDENCE_ROUTING_AND_FULL_ASSURANCE']}
        if (self.directory/'pre-outcome-audit.json').exists():
            return self.load('pre-outcome-audit')
        frozen = self.directory/'all-role-isolation-audit.json'
        freeze_json(frozen, combined)
        return super().pre_outcome_audit(frozen)
