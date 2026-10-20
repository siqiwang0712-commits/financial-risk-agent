"""Outcome-blind full-family operating-characteristic and power experiments."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from ..execution.core import digest, file_hash, freeze_json, read_json, require
from .inference import infer_matrix, specification


def sample_matrix(case: dict, rng: np.random.Generator, *, n_override: int | None = None) -> np.ndarray:
    n = case['n'] if n_override is None else n_override
    n = int(rng.binomial(n, case.get('packet_success', 1.)))
    require(n >= 3, 'simulation attrition leaves too few paired companies')
    pi, v = case['prevalence'], case['verified_fraction']
    if case['missingness'] == 'informative':
        contrast = min(.5, v/(1-pi), (1-v)/pi)
        v1, v0 = v-contrast*(1-pi), v+contrast*pi
    else:
        v1 = v0 = v
    pi_known = pi*v1/v
    error_factor_mean = .5 + pi_known
    y = rng.binomial(1, pi, n)
    known = rng.random(n) < np.where(y == 1, v1, v0)
    # Label-dependent errors keep the stated VERIFIED-population error incidence
    # exactly at the configured value, even under informative observability.
    error_factor = np.where(y == 1, 1.5, .5) / error_factor_mean
    rho = case['dependence']
    common_a, common_e = rng.random(n), rng.random(n)
    a_uniform = np.where(rng.random((3, n)) < rho, common_a, rng.random((3, n)))
    e_uniform = np.where(rng.random((3, n)) < rho, common_e, rng.random((3, n)))
    prop = case.get('proposal_success', 1.)
    proposal_success = rng.random(n) < prop
    automations, errors = [], []
    for i, arm in enumerate(('1', '3', '4')):
        q, e = case['q'+arm], case['e'+arm]
        conditional_q = q if arm == '1' else q / prop
        require(conditional_q <= 1. and np.max(e/q*error_factor) <= 1., 'invalid synthetic population rates')
        a = a_uniform[i] < conditional_q
        if arm != '1':
            a &= proposal_success
        error = a & (e_uniform[i] < e/q*error_factor)
        automations.append(a.astype(int))
        errors.append(error.astype(int))
    a1, a3, a4 = automations
    e1, e3, e4 = errors
    return np.column_stack((known.astype(int), known*(e1-e4), known*(e3-e4), a4-a1, a4-a3, a4)).astype(float)


def null_cases(spec: dict) -> list[dict]:
    delta, floor, margin = spec['delta'], spec['c'], spec['m']
    cases = []
    def add(name, n, pi, v, missing, rho, q1, q3, q4, e1, e3, e4, **extra):
        cases.append(dict(name=name, n=n, prevalence=pi, verified_fraction=v, missingness=missing,
                          dependence=rho, q1=q1, q3=q3, q4=q4, e1=e1, e3=e3, e4=e4, **extra))
    add('global_null', 100, .1, 1., 'independent', 1., .8, .8, .8, .1, .1, .1)
    add('error_boundary_independent', 200, .35, 1., 'independent', 0., .8, .8, .8, .05+delta, .05+delta, .05)
    add('NI_boundary_nested', 500, .35, .8, 'informative', 1., .85, .85, .85-margin, .18, .18, .05)
    add('NI_boundary_discordant', 200, .6, .75, 'independent', 0., .85, .85, .85-margin, .18, .18, .05)
    add('absolute_boundary', 500, .6, .75, 'informative', .5, floor, floor, floor, .18, .18, .05)
    add('mixed_boundary', 500, .1, .6, 'informative', .5, floor+margin, floor+margin, floor, .05+delta, .05+delta, .05)
    add('P1_null_P2_alternative', 500, .6, .8, 'informative', .5, .8, .8, .8, .05+delta, .18, .05)
    add('P2_null_P1_alternative', 500, .1, .8, 'independent', 0., .8, .8, .8, .18, .05+delta, .05)
    add('high_informative_missingness', 1000, .6, .5, 'informative', .8, .8, .8, .8, .05+delta, .05+delta, .05)
    add('packet_and_proposal_attrition', 1000, .35, .75, 'independent', .5,
        floor+margin, floor+margin, floor, .18, .18, .05, proposal_success=.9, packet_success=.9)
    add('rare_events_nested_NI', 1500, .02, .8, 'informative', 1., .85, .85, .85-margin, .18, .18, .05)
    add('small_paired_error_boundary', 100, .35, .75, 'independent', .5, .8, .8, .8, .05+delta, .05+delta, .05)
    return cases


def expected(case: dict, spec: dict):
    values = [[case['e1']-case['e4'], case['q4']-case['q1'], case['q4']],
              [case['e3']-case['e4'], case['q4']-case['q3'], case['q4']]]
    boundaries = [spec['delta'], -spec['m'], spec['c']]
    masks = [[v <= b+1e-12 for v, b in zip(row, boundaries, strict=True)] for row in values]
    return values, masks


def qualify(root: Path, *, replicates: int = 5000) -> dict:
    require(replicates >= 5000, 'critical null configurations require at least 5000 trials')
    spec = specification(root)
    identity = {'analysis_specification': spec, 'analysis_identity': digest(spec),
                'simulation_source_sha256': file_hash(Path(__file__)), 'replicates': replicates,
                'anti_conservatism_rule': 'One-sided 99% exact binomial lower bound > .05 for any true-null component, primary IUT or family.',
                'cases': null_cases(spec), 'all_data': 'SYNTHETIC_OPERATING_CHARACTERISTICS_NOT_E5_EVIDENCE'}
    run_id = digest(identity)
    directory = root / 'research/e5/phase2/qualification/inference' / run_id
    freeze_json(directory / 'identity.json', identity)
    reports = []
    for index, case in enumerate(identity['cases']):
        destination = directory / f'{index:02d}.json'
        if destination.exists():
            reports.append(read_json(destination))
            continue
        means, null_masks = expected(case, spec)
        primary_null = [any(m) for m in null_masks]
        component_counts = np.zeros((2, 3), dtype=int)
        iut_counts = np.zeros(2, dtype=int)
        family_count = 0
        # Trial batches are immutable, so an interrupted configuration resumes too.
        batches = []
        for first in range(0, replicates, 250):
            batch_path = directory / f'{index:02d}-batch-{first:05d}.json'
            if batch_path.exists():
                batches.append(read_json(batch_path))
                continue
            comp = np.zeros((2, 3), dtype=int)
            pair = np.zeros(2, dtype=int)
            family = 0
            for trial in range(first, min(first+250, replicates)):
                seed = 20261019 + index*100000 + trial
                matrix = sample_matrix(case, np.random.default_rng(seed))
                result = infer_matrix(matrix, spec, simulation_seed=seed)
                bad_family = False
                for p, name in enumerate(('P1', 'P2')):
                    comparison = result['comparisons'][name]
                    for k, c in enumerate(comparison['components'].values()):
                        comp[p, k] += c['p'] is not None and c['p'] <= .05
                    pair[p] += (comparison['iut_p'] is not None and comparison['iut_p'] <= .05
                                and comparison['effect_inequalities'])
                    bad_family |= primary_null[p] and comparison['result'] == 'PASS'
                family += bad_family
            batch = {'first_trial': first, 'n_trials': min(250, replicates-first),
                     'component_rejections': comp.tolist(), 'iut_rejections': pair.tolist(),
                     'family_false_rejections': int(family)}
            freeze_json(batch_path, batch)
            batches.append(batch)
            print(f"null {index+1}/{len(identity['cases'])} {case['name']}: {first+batch['n_trials']}/{replicates}", flush=True)
        for batch in batches:
            component_counts += np.asarray(batch['component_rejections'])
            iut_counts += np.asarray(batch['iut_rejections'])
            family_count += batch['family_false_rejections']
        component_lower = [[float(binomtest(int(x), replicates).proportion_ci(.98).low) for x in row]
                           for row in component_counts]
        iut_lower = [float(binomtest(int(x), replicates).proportion_ci(.98).low) for x in iut_counts]
        family_lower = float(binomtest(family_count, replicates).proportion_ci(.98).low)
        failure = any(null_masks[p][k] and component_lower[p][k] > .05 for p in range(2) for k in range(3))
        failure |= any(primary_null[p] and iut_lower[p] > .05 for p in range(2))
        failure |= family_lower > .05
        report = {'case': case, 'expected_statistics': means, 'true_null_components': null_masks,
                  'true_null_primaries': primary_null, 'replicates': replicates,
                  'component_rejections': component_counts.tolist(),
                  'component_rejection_rates': (component_counts / replicates).tolist(),
                  'component_one_sided99_lower': component_lower, 'iut_rejections': iut_counts.tolist(),
                  'iut_rates': (iut_counts / replicates).tolist(), 'iut_one_sided99_lower': iut_lower,
                  'holm_fwer_rejections': family_count, 'holm_fwer': family_count/replicates,
                  'holm_fwer_one_sided99_lower': family_lower, 'material_anti_conservatism': bool(failure)}
        freeze_json(destination, report)
        reports.append(report)
    report = {'status': 'FAILED' if any(r['material_anti_conservatism'] for r in reports) else 'PASSED',
              'analysis_identity': digest(spec), 'analysis_specification': spec, 'run_id': run_id,
              'simulation_identity': identity, 'configurations': reports, 'outcomes_accessed': False}
    freeze_json(directory / 'qualification.json', report)
    return report


def main():
    root = Path(__file__).resolve().parents[3]
    report = qualify(root)
    print(json.dumps({'status': report['status'], 'run_id': report['run_id'],
                      'configurations': len(report['configurations']),
                      'trials': sum(x['replicates'] for x in report['configurations'])}), flush=True)
    raise SystemExit(0 if report['status'] == 'PASSED' else 2)


if __name__ == '__main__':
    main()
