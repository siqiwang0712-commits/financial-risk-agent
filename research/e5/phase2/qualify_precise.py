"""Real source and role-isolation qualification on already-excluded issuers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from finrisk.e4_core import EXTENDED_ALIASES
from finrisk.metrics import calculate_metrics

from ..execution.core import (
    FrozenProposalProducer,
    digest,
    file_hash,
    freeze_json,
    read_json,
    require,
)
from .isolated import call
from .live_source import extract as live_extract
from .precise_arms import fanout
from .precise_source import extract_packets, resolve_universe
from .producer import FIELDS
from .sources import source_manifest, tsv
from .study import REFERENCE, CalibratedStudyProducer


def sources(root, directory, output):
    records = []
    for filename in ('known-historical-source-path-avnet-v2.json', 'known-historical-source-path.json'):
        old = read_json(root/'research/e5/phase2/qualification'/filename)
        p = old['bundle']['packet']
        case = {'cik': p['cik'], 'accession': p['accession'], 'accepted': p['prediction_cutoff'],
                'period': old['bundle']['evidence']['period'], 'fiscal_year': p['features']['fiscal_year'],
                'filed': old['bundle']['evidence']['filed'], 'source_hash': old['source_sha256']}
        universe = {'candidates': [case], 'exclusions': [], 'window': ['2025-07-01', '2025-09-30'], 'outcome_values_used': False}
        case = resolve_universe(universe, root/'.runtime/e5-index-clock')['candidates'][0]
        archive = extract_packets(root, [case], [directory/'2025q3.manifest.json'], reference_hash=file_hash(root/REFERENCE))[0]
        live = live_extract(root, case['cik'], case['accession'], root/'.runtime/e5-live-source'/case['cik']/case['accession'])
        differences = {key: {'archive': archive['packet']['features'].get(key),
                             'live': live['packet']['features'].get(key), 'historical': value}
                       for key, value in p['features'].items()
                       if not archive['packet']['features'].get(key) == live['packet']['features'].get(key) == value}
        if differences:
            archive_path = Path(source_manifest(directory/'2025q3.manifest.json')['archive_path'])
            tags = {tag for field in differences for tag in EXTENDED_ALIASES.get(field.split('__', 1)[1], ())}
            source_rows = [r for r in tsv(archive_path, 'num.txt')
                           if r.get('adsh') == case['accession'] and r.get('tag') in tags]
            freeze_json(output.parent/'source-comparison-failure.json',
                        {'status': 'FAILED', 'case': case, 'differences': differences,
                         'source_sha256': file_hash(root/'research/e5/phase2/live_source.py'),
                         'archive_bundle': archive, 'live_bundle': live, 'diagnostic_archive_rows': source_rows,
                         'scope': 'EXCLUDED_ENGINEERING_FIXTURES_ONLY', 'E5_outcomes_accessed': False})
        require(not differences, 'real source financial feature mismatch')
        require(archive['packet']['prediction_cutoff'] == live['packet']['prediction_cutoff'], 'primary clock mismatch')
        records.append({'case': case, 'archive_bundle': archive, 'live_bundle': live, 'diagnostic_archive_rows': source_rows,
                        'financial_features_exactly_equal': True, 'primary_second_resolution_clock_equal': True})
    report = {'status': 'PASSED', 'scope': 'ALREADY_EXCLUDED_HISTORICAL_SOURCE_QUALIFICATION_NOT_E5_EVIDENCE',
              'source_sha256': file_hash(root/'research/e5/phase2/live_source.py'),
              'archive_clock_sha256': file_hash(root/'research/e5/phase2/precise_source.py'),
              'cases': records, 'E5_predictions_generated': 0, 'E5_outcomes_accessed': False}
    freeze_json(output, report)
    return report


def runtime(root, source_path, image, output):
    source = read_json(source_path)
    require(source['status'] == 'PASSED', 'real exact-clock source qualification required')
    producer = CalibratedStudyProducer(root)
    from research.strong_tabular_reference.artifact import predict_scores
    manifest = read_json(root/'research/strong_tabular_reference/artifacts/artifact_manifest.json')
    s0_identity = {'model': 'StrongTabularReference-v1', 'fitted_identity': manifest['hashes']['fitted_artifact_hash']}
    names = manifest['feature_contract']['ordered_feature_names']
    records = []
    for entry in source['cases']:
        for mode in ('archive', 'live'):
            bundle, case = entry[mode+'_bundle'], entry['case']
            packet = bundle['packet']
            score, s0_receipt = call(image, {'role': 'S0', 'feature': packet}, s0_identity)
            features = packet['features']
            current = {k: features['current__'+k] for k in FIELDS}
            previous = {k: features['previous__'+k] for k in FIELDS}
            metrics = {k: v.value for k, v in calculate_metrics(current, features['fiscal_year'], previous).items()}
            values = [float(metrics.get(n.removeprefix('observed__')) is not None) if n.startswith('observed__')
                      else metrics.get(n, float('nan')) for n in names]
            expected_s0 = predict_scores([values], ordered_feature_names=names)[0]
            require(abs(score['score']-expected_s0) <= 1e-12, 'isolated S0 replay differs')
            def produce(value):
                result, _ = call(image, value, producer.identity)
                return result
            proposal = FrozenProposalProducer(producer.identity, produce).run(packet, output.parent/('proposal-'+case['cik']+'-'+mode+'.json'))
            outcome = fanout(producer, proposal, bundle, case=case,
                             manifests=[source_path.parent/'sec/2025q3.manifest.json'], image_id=image)
            records.append({'cik': case['cik'], 'accession': case['accession'], 'source_mode': mode,
                            'packet_hash': digest(packet), 'proposal': proposal, 'S0': score,
                            'S0_isolation_receipt': s0_receipt, 'fanout': outcome})
    paths = ('live_source.py', 'precise_source.py', 'sec_access.py', 'precise_worker.py', 'precise_arms.py')
    report = {'status': 'PASSED', 'scope': 'ALREADY_EXCLUDED_HISTORICAL_ALL_ROLE_ISOLATION_NOT_E5_EVIDENCE',
              'producer_identity': producer.identity, 'image_id': image, 'cases': records,
              'adapter_source_hashes': {'research/e5/phase2/'+p: file_hash(root/'research/e5/phase2'/p) for p in paths},
              'Dockerfile_sha256': file_hash(root/'research/e5/phase2/Dockerfile.precise-prediction'),
              'E5_predictions_generated': 0, 'E5_outcomes_accessed': False}
    freeze_json(output, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['sources', 'runtime'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--image')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    if args.stage == 'sources':
        result = sources(root, args.directory/'sec', args.directory/'live-source-qualified.json')
    else:
        result = runtime(root, args.directory/'live-source-qualified.json', args.image, args.directory/'precise-isolation-qualified.json')
    print(json.dumps({'status': result['status'], 'scope': result['scope']}))
