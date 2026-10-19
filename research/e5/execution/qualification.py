"""Development and synthetic-only qualification. Never read E5 outcome data."""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from .core import digest, file_hash, freeze_json, read_json, require
from .development import utility
from .inference import component, holm, iut, paired_statistics


def qualify_s0(root: Path) -> dict:
    from research.strong_tabular_reference.artifact import predict_scores
    base = root / 'research/strong_tabular_reference/artifacts'
    manifest = read_json(base / 'artifact_manifest.json')
    sample = read_json(base / 'replay_sample.json')
    scores = predict_scores(sample['matrix'], ordered_feature_names=manifest['feature_contract']['ordered_feature_names'])
    deviation = float(np.max(np.abs(np.asarray(scores) - sample['expected_scores'])))
    require(deviation <= sample['absolute_tolerance'], 'S0 replay mismatch')
    return {'status': 'HISTORICAL_REPLAY_PASSED_NOT_E5_MODEL_FREEZE',
            'fitted_identity': manifest['hashes']['fitted_artifact_hash'],
            'replay_sample_sha256': file_hash(base / 'replay_sample.json'),
            'n': len(scores), 'maximum_absolute_difference': deviation,
            'tolerance': sample['absolute_tolerance'], 'model_refitted': False}


def null_distribution(name: str, n: int, delta: float, margin: float,
                      floor: float, missing: float) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float]]:
    """Finite company distribution; analytic means exactly equal stated boundaries.

    E <= A always. Error indicators are generated jointly with issuance, and
    missingness is independent here. These simulations are not endpoint outcomes.
    """
    q4, qc, e4, ec = .8, .8, .05, .05
    if name == 'error_boundary':
        ec = e4 + delta
    elif name == 'coverage_boundary':
        qc, q4, ec = .85, .85 - margin, .18
    elif name == 'absolute_boundary':
        q4, qc, ec = floor, floor, .18
    elif name == 'mixed_boundary':
        q4, qc, ec = floor, floor + margin, e4 + delta
    elif name != 'global_null':
        raise ValueError(name)
    # State 0 withheld; 1 automated correct; 2 automated error.
    p4, pc = [1-q4, q4-e4, e4], [1-qc, qc-ec, ec]
    patterns, probabilities = [], []
    for known, s4, sc in itertools.product((0, 1), range(3), range(3)):
        probability = (1-missing if known else missing) * p4[s4] * pc[sc]
        if probability > 0:
            patterns.append([known, known * (int(sc == 2) - int(s4 == 2)),
                             int(s4 > 0) - int(sc > 0), int(s4 > 0)])
            probabilities.append(probability)
    patterns = np.asarray(patterns, dtype=float)
    probabilities = np.asarray(probabilities)
    expected = probabilities @ patterns
    require(np.isclose(expected[1] / expected[0], ec-e4), 'null error boundary mismatch')
    return patterns, probabilities, (ec-e4, q4-qc, q4)


def null_qualification(root: Path, output: Path, *, replicates: int = 5000,
                       draws: int = 20_000, seed: int = 20261019) -> dict:
    values = utility(root)
    delta, margin, floor = values['delta'], values['m'], values['c']
    configurations = [(name, n, missing) for name, n, missing in [
        ('global_null', 100, 0.), ('error_boundary', 200, 0.),
        ('coverage_boundary', 200, 0.), ('absolute_boundary', 200, 0.),
        ('mixed_boundary', 200, 0.), ('error_boundary', 100, .25),
        ('coverage_boundary', 500, .25), ('absolute_boundary', 500, .25)]]
    identity = {'inference_sha256': file_hash(Path(__file__).with_name('inference.py')),
                'qualification_code_sha256': file_hash(Path(__file__)),
                'utility_hash': digest(values), 'replicates': replicates, 'draws': draws,
                'seed': seed, 'configurations': configurations,
                'rejection_threshold': .05,
                'material_anti_conservatism_rule': 'one-sided 99% exact binomial lower bound > .05',
                'scope': 'finite synthetic paired error/issuance distributions; not E5 outcomes'}
    run_id = digest(identity)
    run_dir = output / 'null_runs' / run_id
    freeze_json(run_dir / 'identity.json', identity)
    reports = []
    for index, (name, n, missing) in enumerate(configurations):
        path = run_dir / f'{index:02d}.json'
        if path.exists():
            reports.append(read_json(path))
            continue
        patterns, probabilities, expected = null_distribution(name, n, delta, margin, floor, missing)
        rng = np.random.default_rng(seed + index)
        component_reject = np.zeros(3, dtype=int)
        estimable = np.zeros(3, dtype=int)
        iut_reject = family_reject = 0
        for trial in range(replicates):
            counts = rng.multinomial(n, probabilities)
            matrix = np.repeat(patterns, counts, axis=0)
            estimate, bootstrap, jackknife = paired_statistics(matrix, draws=draws, seed=seed+index*1_000_000+trial)
            results = [component(float(estimate[k]), bootstrap[:, k], jackknife[:, k], boundary)
                       for k, boundary in enumerate((delta, -margin, floor))]
            ps = [r['p'] for r in results]
            for k, p in enumerate(ps):
                estimable[k] += p is not None
                component_reject[k] += p is not None and p <= .05
            p_iut = iut(ps)
            iut_reject += p_iut is not None and p_iut <= .05
            # Duplicate comparator configuration gives exact dependence. Separate
            # Holm fixtures test unequal values. Broader dependence remains limited.
            family_reject += p_iut is not None and any(x['reject'] for x in holm([p_iut, p_iut]))
            if (trial + 1) % 500 == 0:
                print(f'null {index+1}/{len(configurations)} {name}: {trial+1}/{replicates}', flush=True)
        null_components = [expected[k] <= boundary + 1e-12
                           for k, boundary in enumerate((delta, -margin, floor))]
        lower = [float(binomtest(int(count), replicates).proportion_ci(.98).low)
                 for count in component_reject]
        anti = any(is_null and bound > .05 for is_null, bound in zip(null_components, lower, strict=True))
        report = {'configuration': name, 'n': n, 'missing_fraction': missing,
                  'expected_statistics': expected, 'null_components': null_components,
                  'replicates': replicates, 'draws': draws,
                  'component_estimable': estimable.tolist(), 'component_rejections': component_reject.tolist(),
                  'component_rates': (component_reject / replicates).tolist(),
                  'component_one_sided99_lower': lower,
                  'iut_rejections': int(iut_reject), 'iut_rate': iut_reject / replicates,
                  'holm_family_rejections': int(family_reject), 'holm_fwer': family_reject / replicates,
                  'material_anti_conservatism': bool(anti)}
        freeze_json(path, report)
        reports.append(report)
        print('finished null configuration', name, flush=True)
    return {'identity': identity, 'run_id': run_id, 'configurations': reports,
            'status': 'FAILED_ANTI_CONSERVATISM' if any(r['material_anti_conservatism'] for r in reports)
                      else 'SIMULATION_GRID_PASSED_SCOPE_LIMITED',
            'limitations': ['Comparator duplication tests perfect dependence, not a broad P1/P2 correlation grid.',
                           'No event-prevalence or informative-missingness grid; this is not full mandate qualification.',
                           'No scientific freeze is authorized by these engineering results alone.']}
