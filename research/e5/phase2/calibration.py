"""Development-only calibration for the exact raw structured-numeric producer."""
from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

from ..execution.core import digest, file_hash, freeze_json, read_json, require, utcnow
from .producer import NumericProposalProducer, flatten


def fit(kind, scores, labels):
    if kind == 'platt':
        return LogisticRegression(C=1e6, solver='lbfgs', max_iter=2000).fit(scores.reshape(-1, 1), labels)
    return IsotonicRegression(out_of_bounds='clip').fit(scores, labels)


def probabilities(model, kind, scores):
    return model.predict_proba(scores.reshape(-1, 1))[:, 1] if kind == 'platt' else model.predict(scores)


def apply(artifact: dict, score: float | None) -> float | None:
    if score is None:
        return None
    if artifact['method'] == 'platt':
        from scipy.special import expit
        return float(expit(artifact['coefficient'] * score + artifact['intercept']))
    return float(np.interp(score, artifact['x_thresholds'], artifact['y_thresholds']))


def diagnostics(labels, predictions):
    clipped = np.clip(predictions, 1e-6, 1-1e-6)
    logits = np.log(clipped / (1-clipped)).reshape(-1, 1)
    regression = LogisticRegression(C=1e6, max_iter=2000).fit(logits, labels)
    bins = []
    for index in range(10):
        selected = (clipped >= index/10) & (clipped < (index+1)/10)
        if selected.any():
            bins.append({'lower': index/10, 'n': int(selected.sum()),
                         'mean_probability': float(clipped[selected].mean()),
                         'event_fraction': float(labels[selected].mean())})
    return {'intercept': float(regression.intercept_[0]), 'slope': float(regression.coef_[0, 0]),
            'reliability_bins': bins,
            'ece10': sum(b['n'] * abs(b['mean_probability'] - b['event_fraction']) for b in bins) / len(labels)}


def qualify(root: Path, output: Path) -> dict:
    producer = NumericProposalProducer(root)
    if (output / 'calibration_report.json').exists():
        saved = read_json(output / 'calibration_report.json')
        require(saved['producer_hash'] == digest(producer.identity), 'producer drift requires a new calibration identity')
        require(saved['calculation_code_sha256'] == file_hash(Path(__file__)), 'calibration code drift requires a new identity')
        for name, expected in saved['artifact_hashes'].items():
            require(file_hash(output / name) == expected, 'calibration artifact drift')
        return saved
    manifest = read_json(root / 'research/strong_tabular_reference/development_data_manifest.json')
    provenance = manifest['provenance']['source_artifact_hashes']
    base = root / 'research/e4_statistical_audit/replication'
    for filename in ('features.json.gz', 'outcomes.json'):
        require(file_hash(base / filename) == provenance[filename], 'historical development identity mismatch')
    raw_rows = __import__('json').loads(gzip.decompress((base / 'features.json.gz').read_bytes()))
    outcomes = read_json(base / 'outcomes.json')
    by_id = {r['observation_id']: r for r in outcomes}
    rows = []
    for row in raw_rows:
        endpoint = by_id[row['observation_id']]
        if endpoint['label_status'] != 'VERIFIED':
            continue
        result = producer({'features': flatten(row['current'], row.get('previous'), row['fiscal_year'])})
        rows.append({'cik': row['cik'], 'observation_id': row['observation_id'],
                     'input_hash': digest({'current': row['current'], 'previous': row.get('previous'), 'year': row['fiscal_year']}),
                     'raw_score': result['normalized_risk_score'], 'proposed_decision': result['proposed_decision'],
                     'label': endpoint['financial_deterioration_12m'], 'proposal_hash': digest(result)})
    require(len(rows) == 675 and len({r['cik'] for r in rows}) == 675, 'development company population differs')
    usable = [r for r in rows if r['raw_score'] is not None]
    scores = np.asarray([r['raw_score'] for r in usable])
    y = np.asarray([r['label'] for r in usable])
    require(len(usable) >= 100 and np.unique(scores).size >= 3 and np.unique(y).size == 2,
            'scalar calibration target not estimable')
    auc = float(roc_auc_score(y, scores))
    association = float(spearmanr(scores, y).statistic)
    require(auc > .5 and association > 0, 'raw score does not support the declared increasing-risk calibration direction')
    cv = StratifiedKFold(5, shuffle=True, random_state=20261019)
    methods = {}
    for kind in ('platt', 'isotonic'):
        predictions = np.empty(len(y))
        folds = []
        for train, test in cv.split(scores, y):
            model = fit(kind, scores[train], y[train])
            p = np.clip(probabilities(model, kind, scores[test]), 1e-9, 1-1e-9)
            predictions[test] = p
            folds.append({'brier': float(brier_score_loss(y[test], p)), 'log_loss': float(log_loss(y[test], p)),
                          'n': len(test)})
        methods[kind] = {'brier': float(brier_score_loss(y, predictions)),
                         'log_loss': float(log_loss(y, predictions)), 'folds': folds,
                         'predictions': predictions.tolist(), 'diagnostics': diagnostics(y, predictions)}
    # Outcome-blind predeclared practical tie: prefer logistic within .001 Brier.
    selected = 'isotonic' if methods['isotonic']['brier'] + .001 < methods['platt']['brier'] else 'platt'
    model = fit(selected, scores, y)
    artifact = {'method': selected, 'score_semantics': 'HISTORICAL_DEVELOPMENT_CALIBRATED',
                'producer_hash': digest(producer.identity), 'training_input_rows_hash': digest(rows),
                'evaluation_outcomes_used': False}
    if selected == 'platt':
        artifact.update(coefficient=float(model.coef_[0, 0]), intercept=float(model.intercept_[0]))
    else:
        artifact.update(x_thresholds=model.X_thresholds_.tolist(), y_thresholds=model.y_thresholds_.tolist())
    output.mkdir(parents=True, exist_ok=True)
    for name, value in [('raw_producer_identity.json', {'identity': producer.identity, 'files': producer.files}),
                        ('raw_feature_schema.json', producer.schema), ('development_proposals.json', rows),
                        ('calibration_artifact.json', artifact)]:
        freeze_json(output / name, value)
    report = {'created_at': utcnow(), 'status': 'HISTORICAL_DEVELOPMENT_CALIBRATED',
              'n_total': len(rows), 'n_scored': len(usable), 'n_score_unavailable': len(rows)-len(usable),
              'training_companies': [r['cik'] for r in usable], 'raw_auc': auc, 'spearman': association,
              'methods': methods, 'artifact_hashes': {name: file_hash(output / name) for name in ['raw_producer_identity.json', 'raw_feature_schema.json', 'development_proposals.json', 'calibration_artifact.json']}, 'selected': selected, 'selection_rule': 'MIN_CV_BRIER_PLATT_WINS_WITHIN_0_001',
              'calibration_artifact_sha256': file_hash(output / 'calibration_artifact.json'),
              'producer_hash': digest(producer.identity), 'development_feature_sha256': file_hash(base / 'features.json.gz'),
              'development_endpoint_sha256': file_hash(base / 'outcomes.json'),
              'calculation_code_sha256': file_hash(Path(__file__)), 'evaluation_outcomes_used': False,
              'limitations': ['Selected VERIFIED historical development population, not external calibration.',
                              'No narrative provider or LLM execution.', 'CV evaluates calibration of fixed rules, not an independent prospective study.']}
    freeze_json(output / 'calibration_report.json', report)
    return report
