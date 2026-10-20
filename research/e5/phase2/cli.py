"""Active Phase-II CLI; historical V1 execution commands are retired here."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..execution.core import (
    GateError,
    digest,
    file_hash,
    freeze_json,
    read_json,
    require,
    verify_files,
)
from .engine import Execution


def status(root):
    base = root/'research/e5/phase2'
    null = base/'qualification/canonical-v3-complete.json'
    universe_path = base/'sources/2025q3.universe-inspection-v2.json'
    if not universe_path.exists():
        universe_path = base/'sources/2025q3.universe-inspection.json'
    state = {'study_scope': 'INTERNAL_STRUCTURED_NUMERIC',
             'SEC_feature_source': 'ACQUIRED_AND_HASH_VERIFIED_ON_GITHUB_ACTIONS',
             'source_metadata_records': len(read_json(base/'sources/2025q3.10k-submissions.json')),
             'candidate_universe_before_C01': len(read_json(universe_path)['candidates']),
             'C01': read_json(base/'C01_BOUNDARY_ASSESSMENT.json'),
             'canonical_inference': read_json(null)['status'] if null.exists() else 'QUALIFICATION_IN_PROGRESS',
             'power': 'DEVELOPMENT_ONLY_UNDERPOWERED',
             'E5R': 'NOT_EVALUATED', 'E5P': 'DRAFT', 'empirical_claim': 'Assurance benefit was not evaluated.'}
    for study, directory in [('E5R', base/'e5r'), ('E5P', base/'e5p-core')]:
        if (directory/'protocol.json').exists():
            state[study] = 'PROTOCOL_FROZEN_ENROLLMENT_REQUIRES_C01'
        if (directory/'final-report.json').exists():
            state[study] = read_json(directory/'final-report.json')['payload']['status']
    return state


def audit(root):
    baseline = read_json(root/'research/e5/execution/BASELINE_AUDIT.json')
    verify_files(root, baseline['file_inventory'])
    base = root/'research/e5/phase2'
    calibration = base/'qualification/numeric-v2'
    report = read_json(calibration/'calibration_report.json')
    for name, expected in report['artifact_hashes'].items():
        require(file_hash(calibration/name) == expected, 'calibration artifact drift')
    raw = read_json(calibration/'raw_producer_identity.json')
    verify_files(root, raw['files'])
    manifest = read_json(base/'sources/2025q3.provenance.json')['manifest']
    require(file_hash(base/'sources/2025q3.10k-submissions.json') == manifest['submission_metadata_sha256'], 'official metadata changed')
    for directory in (base/'e5r', base/'e5p-core'):
        if (directory/'protocol.json').exists():
            run = Execution(root, directory)
            run.check_protocol()
            from .engine import ORDER
            for stage in ORDER:
                if (directory/(stage+'.json')).exists():
                    run.load(stage)
    return {'integrity': 'PASS', 'historical_baseline_files_verified': len(baseline['file_inventory']),
            'calibration_artifacts_verified': len(report['artifact_hashes']), 'state': status(root)}


def prereq(path, description):
    require(path is not None and path.is_file(), description+' not supplied')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'audit', 'qualify', 'null-qualify', 'run-e5r',
                                         'freeze-e5r', 'freeze-e5p', 'pre-outcome-audit', 'unlock-outcomes'])
    parser.add_argument('--run', type=Path)
    parser.add_argument('--universe', type=Path)
    parser.add_argument('--availability', type=Path)
    parser.add_argument('--previous-270', type=Path)
    parser.add_argument('--isolation-receipt', type=Path)
    parser.add_argument('--manifest', action='append', type=Path, default=[])
    parser.add_argument('--outcome-manifest', action='append', type=Path, default=[])
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    base = root/'research/e5/phase2'
    try:
        if args.command == 'status':
            result = status(root)
        elif args.command == 'audit':
            result = audit(root)
        elif args.command == 'qualify':
            from .qualify_endpoint import run
            result = run(root)
        elif args.command == 'null-qualify' and (base/'qualification/canonical-v3-complete.json').exists():
            from .inference import specification
            result = read_json(base/'qualification/canonical-v3-complete.json')
            require(result['analysis_identity'] == digest(specification(root)), 'canonical qualification code drift')
            verify_files(root, result['qualification_artifact_hashes'])
        elif args.command == 'null-qualify':
            from .qualification import combine, supplement
            from .simulation import qualify
            full = qualify(root)
            extra = supplement(root)
            # Both canonical-run functions freeze content-addressed artifacts.
            full_path = base/'qualification/inference'/full['run_id']/'qualification.json'
            candidates = list((base/'qualification/supplement').glob('*/qualification.json'))
            extra_path = next(p for p in candidates if read_json(p) == extra)
            result = combine(root, full_path, extra_path)
        else:
            directory = args.run or base/('e5p-core' if args.command == 'freeze-e5p' else 'e5r')
            run = Execution(root, directory)
            if args.command == 'pre-outcome-audit':
                result = run.pre_outcome_audit(args.isolation_receipt)
            elif args.command == 'unlock-outcomes':
                result = run.unlock()
            else:
                if args.command in {'run-e5r', 'freeze-e5r'}:
                    from .cohort import prove_exclusions
                    prove_exclusions(root, prereq(args.previous_270, 'C01 exact historical exclusion artifact or independently verified boundary proof'))
                null = prereq(base/'qualification/canonical-v3-complete.json', 'Complete canonical null qualification')
                powers = list((base/'qualification/power').glob('*/report.json'))
                require(len(powers) == 1, 'one active matched joint-power report required')
                endpoint = prereq(base/'qualification/endpoint-qualification-v2.json', 'Endpoint qualification')
                result = run.load('protocol') if (directory/'protocol.json').exists() else run.protocol(null, powers[0], endpoint)
                run.check_protocol()
                if args.command == 'freeze-e5p':
                    freeze_json(directory/'prospective-state.json', {
                        'status': 'PROTOCOL_FROZEN', 'protocol_manifest_hash': digest(result),
                        'enrollment_status': 'NOT_STARTED_REQUIRES_HISTORICAL_NONOVERLAP_PROOF_AND_OPERATIONAL_TIMELY_COLLECTION',
                        'predictions_generated': 0, 'outcomes_accessed': False})
                elif args.command == 'run-e5r':
                    def done(stage):
                        if (directory/(stage+'.json')).exists():
                            run.load(stage)
                            return True
                        return False
                    if not done('cohort'):
                        run.cohort(prereq(args.universe, 'Frozen outcome-blind universe'),
                                   prereq(args.previous_270, 'C01 exact artifact'),
                                   prereq(args.availability, 'Authoritative outcome-observability catalog'))
                    if not done('features'):
                        run.features(args.manifest)
                    if not done('predictions'):
                        run.predictions(args.manifest)
                    if not done('pre-outcome-audit'):
                        run.pre_outcome_audit(args.isolation_receipt)
                    if not done('outcome-unlock'):
                        run.unlock()
                    if not done('outcomes'):
                        from ..execution.core import utcnow
                        sources = args.outcome_manifest
                        if not sources:
                            from datetime import datetime

                            from finrisk.sec_bulk import add_twelve_months

                            from .acquire_outcomes import acquire
                            cases = run.load('cohort')['payload']['cases']
                            start = min(datetime.fromisoformat(c['accepted']) for c in cases)
                            end = max(add_twelve_months(datetime.fromisoformat(c['accepted'])) for c in cases)
                            quarters = []
                            year, quarter = start.year, (start.month-1)//3+1
                            last = (end.year, (end.month-1)//3+1)
                            while (year, quarter) <= last:
                                quarters.append(f'{year}q{quarter}')
                                year, quarter = (year+1, 1) if quarter == 4 else (year, quarter+1)
                            sources = acquire(root, directory, quarters)
                        run.outcomes(sources, as_of=utcnow())
                    if not done('analysis'):
                        run.analysis()
                    if not done('sensitivities'):
                        run.sensitivities()
                    result = run.load('final-report') if done('final-report') else run.final_report()
        print(json.dumps(result, indent=2))
        return 0
    except (GateError, OSError, ValueError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'actual_prerequisite': str(exc),
                          'empirical_claim': 'Assurance benefit was not evaluated.'}), file=sys.stderr)
        return 2
