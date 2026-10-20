"""Complete canonical qualification, including the inherited N=100 failure case."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from ..execution.core import digest, file_hash, freeze_json, read_json, require
from .inference import infer_matrix, specification
from .simulation import null_cases, sample_matrix


def supplement(root: Path):
    spec = specification(root)
    case = next(c for c in null_cases(spec) if c['name'] == 'NI_boundary_nested') | {'n': 100, 'name': 'N100_nested_NI_V2_regression'}
    identity = {'analysis_identity': digest(spec), 'case': case, 'replicates': 5000,
                'qualification_source_sha256': file_hash(Path(__file__)), 'seed': 20261019+19000000}
    directory = root/'research/e5/phase2/qualification/supplement'/digest(identity)
    freeze_json(directory/'identity.json', identity)
    counts = np.zeros(5, dtype=int)
    for first in range(0, 5000, 250):
        path = directory/f'batch-{first}.json'
        if path.exists():
            batch = read_json(path)
        else:
            count = np.zeros(5, dtype=int)
            for trial in range(first, first+250):
                seed = identity['seed']+trial
                matrix = sample_matrix(case, np.random.default_rng(seed))
                result = infer_matrix(matrix, spec, simulation_seed=seed)
                for j, name in enumerate(('P1', 'P2')):
                    p = result['comparisons'][name]
                    ni = p['components']['coverage_difference']['p']
                    count[j] += ni is not None and ni <= .05
                    count[j+2] += p['iut_p'] is not None and p['iut_p'] <= .05 and p['effect_inequalities']
                count[4] += any(p['result'] == 'PASS' for p in result['comparisons'].values())
            batch = {'first_trial': first, 'n_trials': 250, 'rejections_NI1_NI2_IUT1_IUT2_FWER': count.tolist()}
            freeze_json(path, batch)
            print(f'supplement N100 nested NI: {first+250}/5000', flush=True)
        counts += np.asarray(batch['rejections_NI1_NI2_IUT1_IUT2_FWER'])
    lower = [float(binomtest(int(c), 5000).proportion_ci(.98).low) for c in counts]
    failed = any(c > .05 for c in lower)
    result = {'case': case, 'replicates': 5000, 'identity': identity,
              'rejections_NI1_NI2_IUT1_IUT2_FWER': counts.tolist(),
              'rates': (counts/5000).tolist(), 'one_sided99_lower': lower,
              'material_anti_conservatism': failed, 'status': 'FAILED' if failed else 'PASSED',
              'analysis_identity': digest(spec), 'outcomes_accessed': False}
    freeze_json(directory/'qualification.json', result)
    return result


def combine(root: Path, full: Path, supplementary: Path):
    base, extra = read_json(full), read_json(supplementary)
    spec = specification(root)
    require(base['analysis_identity'] == extra['analysis_identity'] == digest(spec), 'qualification analysis drift')
    require(base['simulation_identity']['cases'] == null_cases(spec), 'null grid changed')
    require(base['simulation_identity']['simulation_source_sha256'] == file_hash(root/'research/e5/phase2/simulation.py'), 'simulation code drift')
    require(extra['identity']['qualification_source_sha256'] == file_hash(Path(__file__)), 'supplement code drift')
    cases = base['configurations']+[extra]
    status = 'PASSED' if all(c['replicates'] >= 5000 and not c['material_anti_conservatism'] for c in cases) else 'FAILED'
    result = {'status': status, 'analysis_identity': digest(spec), 'analysis_specification': spec,
              'configurations': cases, 'qualification_artifact_hashes': {str(p.relative_to(root)): file_hash(p) for p in (full, supplementary)},
              'complete_grid_trials': sum(c['replicates'] for c in cases), 'outcomes_accessed': False}
    freeze_json(root/'research/e5/phase2/qualification/canonical-v3-complete.json', result)
    return result


if __name__ == '__main__':
    r = supplement(Path(__file__).resolve().parents[3])
    print({'status': r['status'], 'rates': r['rates']})
