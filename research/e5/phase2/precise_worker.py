"""No-network/no-host-volume S0, proposal and Assurance computation roles."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from finrisk.metrics import calculate_metrics

from ..execution.core import digest, file_hash, read_json, require, validate_features
from .producer import FIELDS
from .study import CalibratedStudyProducer


def worker():
    root = Path(__file__).resolve().parents[3]
    request = json.load(sys.stdin)
    role = request.get('role', 'PROPOSAL')
    feature = request if role == 'PROPOSAL' else request['feature']
    producer = CalibratedStudyProducer(root)
    allowed = {file_hash(root/'research/e5/phase2'/name) for name in ('precise_source.py', 'live_source.py')}
    require(feature['extraction_code_hash'] in allowed, 'unqualified exact-clock extractor')
    require(set(feature['features']) == set(producer.raw.schema['features']), 'feature/label schema substitution')
    validate_features(feature, schema_hash=digest(producer.raw.schema), code_hash=feature['extraction_code_hash'])
    identity = producer.identity
    if role == 'PROPOSAL':
        result = producer(feature)
    elif role == 'S0':
        from research.strong_tabular_reference.artifact import predict_scores
        manifest = read_json(root/'research/strong_tabular_reference/artifacts/artifact_manifest.json')
        names = manifest['feature_contract']['ordered_feature_names']
        data = feature['features']
        current = {k: data['current__'+k] for k in FIELDS}
        previous = {k: data['previous__'+k] for k in FIELDS}
        metrics = {k: v.value for k, v in calculate_metrics(current, data['fiscal_year'], previous).items()}
        values = [float(metrics.get(n.removeprefix('observed__')) is not None) if n.startswith('observed__')
                  else metrics.get(n, float('nan')) for n in names]
        score = predict_scores([values], ordered_feature_names=names)[0]
        identity = {'model': 'StrongTabularReference-v1', 'fitted_identity': manifest['hashes']['fitted_artifact_hash']}
        result = {'score': score, 'model_refitted': False, 'score_semantics': 'UNCALIBRATED_RANKING_SCORE'}
    elif role == 'ADMISSION':
        from .precise_arms import evaluate_verified
        require(set(request) == {'role', 'feature', 'proposal', 'paths', 'source_hash'}, 'admission envelope fields differ')
        result = evaluate_verified(root, feature, request['proposal'], request['paths'], request['source_hash'])
    else:
        raise ValueError('unsupported isolated computation role')
    print(json.dumps({'producer_identity': identity, 'input_hash': digest(request), 'result': result}, sort_keys=True))


if __name__ == '__main__':
    worker()
