"""Paired-company selective-authorization inference, independent of product code."""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.stats import norm

from .core import require, verified_label

NOT_ESTIMABLE = {'status': 'NOT_ESTIMABLE', 'estimate': None, 'ci95': None, 'p': None}


def holm(pvalues: Sequence[float], alpha: float = .05) -> list[dict]:
    require(len(pvalues) == 2, 'frozen family has exactly P1 and P2')
    require(all(type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1 for p in pvalues),
            'finite p-values required')
    order = sorted(range(2), key=lambda i: (pvalues[i], i))
    adjusted = [0., 0.]
    maximum = 0.
    for rank, i in enumerate(order):
        maximum = max(maximum, (2 - rank) * pvalues[i])
        adjusted[i] = min(1., maximum)
    return [{'adjusted_p': p, 'reject': p <= alpha} for p in adjusted]


def iut(pvalues: Sequence[float | None]) -> float | None:
    require(len(pvalues) == 3, 'three IUT components required')
    if any(p is None for p in pvalues):
        return None
    require(all(math.isfinite(p) and 0 <= p <= 1 for p in pvalues), 'invalid component p')
    return float(max(pvalues))


def component(estimate: float, bootstrap: np.ndarray, jackknife: np.ndarray,
              boundary: float) -> dict:
    """Greater-than alternative; bootstrap distribution is centered on null boundary."""
    if (not math.isfinite(estimate) or len(bootstrap) < 2 or len(jackknife) < 3
            or not np.isfinite(bootstrap).all() or not np.isfinite(jackknife).all()
            or np.ptp(bootstrap) == 0):
        return dict(NOT_ESTIMABLE)
    deviations = jackknife.mean() - jackknife
    square_sum = np.sum(deviations ** 2)
    if square_sum <= 0:
        return dict(NOT_ESTIMABLE)
    acceleration = float(np.sum(deviations ** 3) / (6 * square_sum ** 1.5))
    # Mid-rank correction handles the ties expected for bounded incidence statistics.
    proportion = float((np.sum(bootstrap < estimate) + .5 * np.sum(bootstrap == estimate)) / len(bootstrap))
    if not 0 < proportion < 1:
        return dict(NOT_ESTIMABLE)
    z0 = norm.ppf(proportion)
    z = norm.ppf([.025, .975])
    denominators = 1 - acceleration * (z0 + z)
    if np.any(denominators <= 0):
        return dict(NOT_ESTIMABLE)
    quantiles = norm.cdf(z0 + (z0 + z) / denominators)
    if not np.isfinite(quantiles).all() or quantiles[0] >= quantiles[1]:
        return dict(NOT_ESTIMABLE)
    ci = np.quantile(bootstrap, quantiles).tolist()
    # Equivalent to boundary + (bootstrap - estimate) >= estimate, without cancellation.
    p = (1 + int(np.sum(bootstrap - estimate >= estimate - boundary - 1e-14))) / (len(bootstrap) + 1)
    return {'status': 'ESTIMATED', 'estimate': estimate, 'ci95': ci, 'p': p,
            'null_boundary': boundary, 'bca_acceleration': acceleration,
            'bca_bias_correction': float(z0)}


def company_matrix(rows: list[dict], comparator: str) -> np.ndarray:
    """Columns: verified, error difference numerator, coverage difference, S4 issuance."""
    require(bool(rows), 'nonempty paired cohort required')
    require(len({r['cik'] for r in rows}) == len(rows), 'one independent company per row')
    matrix = []
    for row in rows:
        label = verified_label(row['outcome'])
        arms = row['arms']
        require(set(arms) >= {'S0', 'S1', 'S2', 'S3', 'S4'}, 'missing paired arm')
        for arm in arms.values():
            require(set(arm) >= {'automated', 'decision'}, 'arm output incomplete')
            require(type(arm['automated']) is bool, 'automation must be boolean')
            require(arm['decision'] in {'PASS', 'FLAG', 'REVIEW', 'ABSTAIN'}, 'invalid disposition')
            require(not arm['automated'] or arm['decision'] in {'PASS', 'FLAG'}, 'invalid automated disposition')
        ac = int(arms[comparator]['automated'])
        a4 = int(arms['S4']['automated'])
        ec = ac * int(label is not None and int(arms[comparator]['decision'] == 'FLAG') != label)
        e4 = a4 * int(label is not None and int(arms['S4']['decision'] == 'FLAG') != label)
        matrix.append([int(label is not None), ec - e4, a4 - ac, a4])
    return np.asarray(matrix, dtype=float)


def paired_statistics(matrix: np.ndarray, *, draws: int = 20_000,
                      seed: int = 20261019) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Multinomial row-pattern counts are exactly paired company resampling.

    Compress only identical sufficient-statistic rows, never resample arms or
    verified labels independently. Every original company has probability 1/N.
    """
    require(matrix.ndim == 2 and matrix.shape[1] == 4 and len(matrix) >= 3,
            'paired company matrix required')
    n = len(matrix)
    patterns, counts = np.unique(matrix, axis=0, return_counts=True)
    rng = np.random.default_rng(seed)
    weights = rng.multinomial(n, counts / n, size=draws)
    sums = weights @ patterns
    totals = matrix.sum(axis=0)
    def statistics(values, denominator):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.column_stack((values[:, 1] / values[:, 0],
                                    values[:, 2] / denominator,
                                    values[:, 3] / denominator))
    return (statistics(totals[None, :], n)[0], statistics(sums, n),
            statistics(totals - matrix, n - 1))


def comparison(rows: list[dict], comparator: str, *, delta: float, margin: float,
               floor: float, draws: int = 20_000, seed: int = 20261019) -> dict:
    require(delta > 0 and 0 <= margin <= 1 and 0 < floor < 1, 'invalid frozen utility')
    matrix = company_matrix(rows, comparator)
    estimate, boot, jack = paired_statistics(matrix, draws=draws, seed=seed)
    components = {name: component(float(estimate[i]), boot[:, i], jack[:, i], boundary)
                  for i, (name, boundary) in enumerate(zip(
                      ('error_benefit', 'coverage_difference', 'absolute_s4_coverage'),
                      (delta, -margin, floor), strict=True))}
    return {'comparator': comparator, 'eligible_n': len(rows),
            'verified_n': int(matrix[:, 0].sum()), 'components': components,
            'iut_p': iut([v['p'] for v in components.values()]),
            'effect_inequalities': bool(estimate[0] > delta and estimate[1] > -margin and estimate[2] > floor)}


def analyze(rows: list[dict], *, delta: float, margin: float, floor: float,
            draws: int = 20_000, seed: int = 20261019) -> dict:
    results = {name: comparison(rows, comp, delta=delta, margin=margin, floor=floor,
                               draws=draws, seed=seed)
               for name, comp in [('P1', 'S1'), ('P2', 'S3')]}
    pvalues = [r['iut_p'] for r in results.values()]
    # Undefined tests remain undefined; reserve their place conservatively in the
    # two-member family rather than silently reducing the multiplicity burden.
    adjustments = holm([p if p is not None else 1. for p in pvalues])
    for result, adj in zip(results.values(), adjustments, strict=True):
        if result['iut_p'] is None:
            result.update(holm_adjusted_p=None, holm_reject=False, result='NOT_ESTIMABLE')
        else:
            passed = bool(adj['reject'] and result['effect_inequalities'])
            result.update(holm_adjusted_p=adj['adjusted_p'], holm_reject=adj['reject'],
                          result='PASS' if passed else 'FAIL')
    return {'comparisons': results, 'family_success': all(r['result'] == 'PASS' for r in results.values()),
            'bootstrap': {'draws': draws, 'seed': seed, 'unit': 'company',
                          'method': 'paired multinomial sufficient-statistic row counts'},
            'classification': 'RETROSPECTIVE_TEMPORAL_VALIDATION' }
