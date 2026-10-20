"""Single Phase-II analysis engine; V3 paired-null repair of inherited V2.

Only BCa mechanics are reused from V1. V1/V2 residual-centered error/NI p-values
are never used. Their nested-automation failure is preserved in qualification/.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..coverage_null_v2 import absolute_pvalue
from ..execution.core import digest, file_hash, read_json, require
from ..execution.inference import company_matrix, component, holm, iut

ENGINE_ID = 'E5-CANONICAL-V3-PAIRED-NULL-REPAIR-OF-V2'


def specification(root: Path) -> dict:
    u = read_json(root / 'research/e5/qualification/utility_rule.json')
    paths = ['research/e5/phase2/inference.py', 'research/e5/coverage_null_v2.py',
             'research/e5/execution/inference.py', 'research/e5/execution/core.py']
    return {'engine_id': ENGINE_ID, 'parent': 'E5-INFERENCE-V2-PRE-OUTCOME',
            'code_hashes': {p: file_hash(root / p) for p in paths},
            'draws': 20000, 'seed': 20261019, 'delta': u['delta'], 'm': u['m'], 'c': u['c'],
            'utility_sha256': file_hash(root / 'research/e5/qualification/utility_rule.json'),
            'error_null': 'CONSTRAINED_TRINOMIAL_PAIRED_COMPANY_NULL_CONDITIONAL_ON_VERIFIED',
            'coverage_ni_null': 'CONSTRAINED_TRINOMIAL_PAIRED_COMPANY_NULL',
            'absolute_null': 'V2_BOUNDARY_BERNOULLI_COMPANY_NULL',
            'confidence_intervals': 'BCA_JOINT_PAIRED_COMPANY_EMPIRICAL_BOOTSTRAP',
            'iut': 'MAXIMUM_THREE_COMPONENT_PVALUES', 'multiplicity': 'HOLM_P1_P2_ALPHA_0_05',
            'undefined_component': 'NOT_ESTIMABLE_NO_PRIMARY_SUCCESS'}


def validate_spec(root: Path, spec: dict) -> None:
    require(spec == specification(root), 'canonical inference identity/code/utility drift or legacy V1 selection')


def constrained_probabilities(values: np.ndarray, boundary: float) -> np.ndarray:
    """Constrained MLE for {-1,0,1} probabilities with E[X]=boundary.

    Maximize multinomial likelihood with discordance s=p(+1)+p(-1),
    p(+1)=(s+b)/2, p(-1)=(s-b)/2. This samples under the actual null boundary,
    instead of retaining the observed alternative's variance/support lattice.
    """
    require(-1 < boundary < 1 and len(values) >= 3, 'invalid paired null')
    require(np.isin(values, [-1, 0, 1]).all(), 'paired incidence/coverage contrast required')
    a, c, z = int(np.sum(values == 1)), int(np.sum(values == -1)), int(np.sum(values == 0))
    n, total, difference = len(values), a+c, a-c
    coefficient = total + difference * boundary
    discriminant = max(0., coefficient**2 - 4*n*(difference*boundary-z*boundary**2))
    s = (coefficient + np.sqrt(discriminant)) / (2*n)
    s = float(np.clip(s, abs(boundary), 1.))
    p = np.asarray([(s-boundary)/2, 1-s, (s+boundary)/2])
    require(np.all(p >= -1e-12) and np.isclose(p.sum(), 1.), 'invalid constrained null')
    p = np.maximum(p, 0.)
    return p / p.sum()


def paired_null_pvalue(values: np.ndarray, boundary: float, *, draws: int, seed: int) -> float | None:
    if len(values) < 3 or np.ptp(values) == 0:
        return None
    p = constrained_probabilities(values, boundary)
    counts = np.random.default_rng(seed).multinomial(len(values), p, size=draws)
    null_means = (counts[:, 2] - counts[:, 0]) / len(values)
    observed = float(values.mean())
    return (1 + int(np.sum(null_means >= observed - 1e-14))) / (draws + 1)


def matrix_from_rows(rows: list[dict]) -> np.ndarray:
    a, b = company_matrix(rows, 'S1'), company_matrix(rows, 'S3')
    require(np.array_equal(a[:, 0], b[:, 0]) and np.array_equal(a[:, 3], b[:, 3]), 'unpaired populations')
    return np.column_stack((a[:, 0], a[:, 1], b[:, 1], a[:, 2], b[:, 2], a[:, 3]))


def statistics(sums: np.ndarray, denominator: int) -> np.ndarray:
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.column_stack((sums[:, 1]/sums[:, 0], sums[:, 2]/sums[:, 0],
                                sums[:, 3]/denominator, sums[:, 4]/denominator,
                                sums[:, 5]/denominator))


def infer_matrix(matrix: np.ndarray, spec: dict, *, simulation_seed: int | None = None) -> dict:
    require(spec['engine_id'] == ENGINE_ID and spec['draws'] == 20000, 'canonical qualified engine required')
    require(matrix.ndim == 2 and matrix.shape[1] == 6 and len(matrix) >= 3, 'paired companies required')
    n, draws = len(matrix), spec['draws']
    seed = spec['seed'] if simulation_seed is None else simulation_seed
    unique, counts = np.unique(matrix, axis=0, return_counts=True)
    weights = np.random.default_rng(seed).multinomial(n, counts/n, size=draws)
    totals = matrix.sum(axis=0)
    estimate = statistics(totals[None, :], n)[0]
    bootstrap = statistics(weights @ unique, n)
    jackknife = statistics(totals-matrix, n-1)
    boundaries = [spec['delta'], spec['delta'], -spec['m'], -spec['m'], spec['c']]
    components = []
    known = matrix[:, 0] == 1
    for k, boundary in enumerate(boundaries):
        ci = component(float(estimate[k]), bootstrap[:, k], jackknife[:, k], boundary)
        # The old p-value is deliberately discarded, even in synthetic analysis.
        ci['p'] = None
        ci['observed_estimate'] = float(estimate[k]) if np.isfinite(estimate[k]) else None
        if ci['status'] == 'ESTIMATED':
            if k == 4:
                ci['p'] = absolute_pvalue(int(totals[5]), n, spec['c'], draws=draws, seed=seed+17)
            else:
                values = matrix[known, k+1] if k < 2 else matrix[:, k+1]
                ci['p'] = paired_null_pvalue(values, boundary, draws=draws, seed=seed+(101 if k < 2 else 103))
        ci['null_method'] = spec['absolute_null'] if k == 4 else spec['error_null'] if k < 2 else spec['coverage_ni_null']
        components.append(ci)
    results = {}
    for name, indices in [('P1', (0, 2, 4)), ('P2', (1, 3, 4))]:
        selected = {key: components[i] for key, i in zip(
            ('error_benefit', 'coverage_difference', 'absolute_s4_coverage'), indices, strict=True)}
        p = iut([c['p'] for c in selected.values()])
        inequalities = all(np.isfinite(estimate[i]) and estimate[i] > boundaries[i] for i in indices)
        results[name] = {'components': selected, 'iut_p': p, 'effect_inequalities': bool(inequalities)}
    adjustments = holm([v['iut_p'] if v['iut_p'] is not None else 1. for v in results.values()])
    for value, adjustment in zip(results.values(), adjustments, strict=True):
        value['holm_adjusted_p'] = adjustment['adjusted_p'] if value['iut_p'] is not None else None
        value['holm_reject'] = adjustment['reject'] and value['iut_p'] is not None
        value['result'] = ('NOT_ESTIMABLE' if value['iut_p'] is None else
                           'PASS' if value['holm_reject'] and value['effect_inequalities'] else 'FAIL')
    return {'engine_id': ENGINE_ID, 'analysis_identity': digest(spec), 'eligible_n': n,
            'verified_n': int(totals[0]), 'comparisons': results,
            'family_success': all(v['result'] == 'PASS' for v in results.values()),
            'bootstrap': {'draws': draws, 'seed': seed, 'unit': 'company', 'all_arms_sampled_together': True}}


def analyze(root: Path, rows: list[dict], spec: dict, qualification: dict) -> dict:
    validate_spec(root, spec)
    require(qualification['analysis_identity'] == digest(spec) and qualification['status'] == 'PASSED',
            'complete canonical qualification identity required')
    return infer_matrix(matrix_from_rows(rows), spec)
