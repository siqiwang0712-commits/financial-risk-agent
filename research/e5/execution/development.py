"""The sponsor-authorized utility calculation on immutable historical OOF rows."""
from __future__ import annotations

from pathlib import Path

from .core import digest, file_hash, read_json, require


def utility(root: Path) -> dict:
    base = root / 'research/strong_tabular_reference'
    source = base / 'artifacts/oof_predictions.json'
    manifest = read_json(base / 'artifacts/artifact_manifest.json')
    require(file_hash(source) == manifest['hashes']['oof_predictions_sha256'],
            'historical OOF identity mismatch')
    rows = read_json(source)['candidates']['histogram_gradient_boosting__VO']
    require(len(rows) == 675 and len({r['cik'] for r in rows}) == 675,
            'historical development population differs')
    records = []
    errors = issued = 0
    for row in rows:
        require(row['score_semantics'] == 'UNCALIBRATED_RANKING_SCORE', 'score semantics differ')
        require(type(row['label']) is int and row['label'] in (0, 1), 'development label invalid')
        score = row['score']
        automated = score < .35 or score >= .65
        wrong = automated and int(score >= .65) != row['label']
        issued += automated
        errors += wrong
        records.append({'cik': row['cik'], 'observation_id': row['observation_id'],
                        'automated': automated, 'error': wrong})
    q, e = issued / len(rows), errors / len(rows)
    return {'rationale': 'HUMAN_AUTHORIZED_MECHANICAL_HISTORICAL_RULE',
            'population': '675 VERIFIED historical development company OOF rows; not E5 evidence',
            'source': str(source.relative_to(root)), 'source_sha256': file_hash(source),
            'dataset_manifest_sha256': file_hash(base / 'development_data_manifest.json'),
            'calculation_code_sha256': file_hash(Path(__file__)),
            'n': len(rows), 'issued': issued, 'errors': errors, 'e1_dev': e, 'q1_dev': q,
            'delta': max(.005, .10 * e), 'm': min(.05, .10 * q), 'c': max(.50, .75 * q),
            'row_digest': digest(records), 'rows': records,
            'evaluation_outcomes_used': False}
