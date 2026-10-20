"""Prespecified descriptive and missing-outcome sensitivity summaries."""
from __future__ import annotations

from sklearn.metrics import average_precision_score, roc_auc_score

from ..execution.core import require, verified_label


def describe(rows):
    require(bool(rows), 'no empirical description of empty cohort')
    known = [r for r in rows if verified_label(r['outcome']) is not None]
    missing = [r for r in rows if verified_label(r['outcome']) is None]
    n, v = len(rows), len(known)
    arms = {}
    for name in ('S0', 'S1', 'S2', 'S3', 'S4'):
        automated = sum(r['arms'][name]['automated'] for r in rows)
        issued_known = sum(r['arms'][name]['automated'] for r in known)
        wrong = sum(r['arms'][name]['automated'] and
                    int(r['arms'][name]['decision'] == 'FLAG') != r['outcome']['label'] for r in known)
        score_rows = [r for r in known if r['arms'][name]['score'] is not None]
        y = [r['outcome']['label'] for r in score_rows]
        scores = [r['arms'][name]['score'] for r in score_rows]
        arms[name] = {'eligible_n': n, 'verified_n': v, 'automated': automated,
                      'coverage': automated/n, 'automated_verified': issued_known,
                      'verified_authorization_errors': wrong,
                      'error_incidence_common_verified': wrong/v if v else None,
                      'selective_error_rate': wrong/issued_known if issued_known else None,
                      'review_rate': sum(r['arms'][name]['decision'] == 'REVIEW' for r in rows)/n,
                      'abstain_rate': sum(r['arms'][name]['decision'] == 'ABSTAIN' for r in rows)/n,
                      'auroc': float(roc_auc_score(y, scores)) if len(set(y)) == 2 else None,
                      'pr_auc_average_precision': float(average_precision_score(y, scores)) if len(set(y)) == 2 else None,
                      'scored_verified_n': len(y)}
    bounds = {}
    for name in ('S1', 'S3'):
        def difference(row, label, comparator=name):
            def error(arm):
                a = row['arms'][arm]
                return int(a['automated'] and int(a['decision'] == 'FLAG') != label)
            return error(comparator)-error('S4')
        fixed = sum(difference(r, r['outcome']['label']) for r in known)
        lo = fixed+sum(min(difference(r, 0), difference(r, 1)) for r in missing)
        hi = fixed+sum(max(difference(r, 0), difference(r, 1)) for r in missing)
        bounds[name] = {'eligible_population_error_benefit_lower': lo/n,
                        'eligible_population_error_benefit_upper': hi/n,
                        'label_scenarios_only_not_primary_imputation': True,
                        'common_binary_label_preserved_across_arms': True}
    statuses = {}
    for row in rows:
        status = row['outcome']['status']
        statuses[status] = statuses.get(status, 0)+1
    return {'eligible_n': n, 'verified_n': v, 'nonverified_n': len(missing),
            'endpoint_status_counts': statuses, 'arms': arms,
            'missing_outcome_bounds': bounds,
            'interpretation': 'Unknown endpoints remain null in primary analysis. Withheld cases are not counted as correct predictions.'}
