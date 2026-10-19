"""Pre-outcome correction: use the specified Bernoulli null for absolute coverage.

The Efron residual-centered bootstrap plugs in the observed variance for a binary
mean. Its lattice/variance error failed the recorded synthetic qualification.
At the absolute-coverage boundary, the Bernoulli distribution is fully specified:
A~Bernoulli(c). Null resampling therefore uses that boundary distribution directly.
Paired empirical bootstrap BCa intervals and the other two tests are unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import binom, binomtest

from .execution.core import digest, file_hash, freeze_json, read_json, require
from .execution.inference import comparison, holm, iut


def absolute_pvalue(issued: int, n: int, floor: float, *, draws: int = 20_000,
                    seed: int = 20261019) -> float:
    require(type(issued) is int and type(n) is int and 0 <= issued <= n and n >= 3,
            'binary company issuance counts required')
    require(0 < floor < 1 and draws >= 2, 'valid boundary and resample count required')
    # Each null company bootstrap count is Binomial(n,c). Each extreme indicator
    # is Bernoulli(P[count>=observed]). Generating their sum is exactly equivalent
    # to generating B counts and counting extremes, without materializing them.
    tail = float(binom.sf(issued - 1, n, floor))
    extreme = int(np.random.default_rng(seed).binomial(draws, tail))
    return (1 + extreme) / (draws + 1)


def analyze(rows: list[dict], *, delta: float, margin: float, floor: float,
            draws: int = 20_000, seed: int = 20261019) -> dict:
    results = {}
    issued = sum(int(r['arms']['S4']['automated']) for r in rows)
    for name, comparator in [('P1', 'S1'), ('P2', 'S3')]:
        result = comparison(rows, comparator, delta=delta, margin=margin, floor=floor,
                            draws=draws, seed=seed)
        absolute = result['components']['absolute_s4_coverage']
        if absolute['status'] == 'ESTIMATED':
            absolute['p'] = absolute_pvalue(issued, len(rows), floor, draws=draws, seed=seed)
            absolute['null_method'] = 'BOUNDARY_BERNOULLI_COMPANY_BOOTSTRAP_V2'
        result['iut_p'] = iut([x['p'] for x in result['components'].values()])
        results[name] = result
    adjusted = holm([x['iut_p'] if x['iut_p'] is not None else 1. for x in results.values()])
    for result, correction in zip(results.values(), adjusted, strict=True):
        if result['iut_p'] is None:
            result.update(holm_adjusted_p=None, holm_reject=False, result='NOT_ESTIMABLE')
        else:
            passed = correction['reject'] and result['effect_inequalities']
            result.update(holm_adjusted_p=correction['adjusted_p'], holm_reject=correction['reject'],
                          result='PASS' if passed else 'FAIL')
    return {'comparisons': results, 'family_success': all(x['result'] == 'PASS' for x in results.values()),
            'analysis_identity': 'E5-INFERENCE-V2-PRE-OUTCOME',
            'paired_ci_and_error_ni_engine_sha256': file_hash(Path(__file__).parent / 'execution/inference.py'),
            'coverage_null_engine_sha256': file_hash(Path(__file__)),
            'seed': seed, 'draws': draws}


def qualify(root: Path) -> dict:
    q = root / 'research/e5/qualification'
    utility = read_json(q / 'utility_rule.json')
    cases = [(n, floor) for n in (50, 100, 200, 500, 1000, 1500, 5000)
             for floor in (.5, utility['c'], .75)]
    reports = []
    for index, (n, floor) in enumerate(cases):
        rng = np.random.default_rng(20261019 + index)
        observed = rng.binomial(n, floor, size=5000)
        tails = binom.sf(observed - 1, n, floor)
        extremes = rng.binomial(20000, tails)
        p = (1 + extremes) / 20001
        rejected = int(np.sum(p <= .05))
        ci = binomtest(rejected, 5000).proportion_ci(.98)
        reports.append({'n': n, 'floor': floor, 'replicates': 5000, 'null_draws_per_trial': 20000,
                        'rejections': rejected, 'rejection_rate': rejected / 5000,
                        'one_sided99_lower': float(ci.low),
                        'anti_conservatism': bool(ci.low > .05)})
    identity = {'source_sha256': file_hash(Path(__file__)),
                'unchanged_engine_sha256': file_hash(root / 'research/e5/execution/inference.py'),
                'old_failed_grid_sha256': file_hash(q / 'type1_simulation_report.json'),
                'utility_sha256': file_hash(q / 'utility_rule.json'), 'seed': 20261019,
                'method': 'Boundary Bernoulli null; binomial compression of extreme replicate indicators',
                'comparisons_unchanged': ['paired BCa intervals', 'error null', 'coverage-NI null', 'IUT maximum', 'Holm'],
                'e5_outcomes_accessed': False}
    return {'identity': identity, 'identity_hash': digest(identity), 'cases': reports,
            'status': 'FAILED' if any(r['anti_conservatism'] for r in reports) else 'ABSOLUTE_COMPONENT_CORRECTION_PASSED',
            'scope': 'Corrected absolute component only; broader joint IUT+Holm dependence and power qualification remain unfinished.'}


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    report = qualify(root)
    path = root / 'research/e5/qualification/v2/absolute_coverage_null_report.json'
    freeze_json(path, report)
    print(json.dumps({'status': report['status'], 'configurations': len(report['cases']),
                      'trials': len(report['cases']) * 5000, 'identity_hash': report['identity_hash']}, indent=2))
    return 0 if report['status'] == 'ABSOLUTE_COMPONENT_CORRECTION_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
