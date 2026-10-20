"""Execute prespecified null configurations in independent CPU workers.

Only scheduling changes: every trial calls the identical canonical kernel with
20,000 bootstrap draws. Each worker's complete case and driver hash are recorded;
no p-value approximation, result selection, or alternative engine is introduced.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..execution.core import digest, file_hash, freeze_json
from . import simulation
from .inference import specification


def worker(index):
    root = Path(__file__).resolve().parents[3]
    case = simulation.null_cases(specification(root))[index]
    # The original runner already accepts a closed case list through null_cases.
    # Record this single-case execution partition before invoking that runner.
    identity = {'case_index': index, 'case': case, 'driver_sha256': file_hash(Path(__file__)),
                'simulation_sha256': file_hash(root/'research/e5/phase2/simulation.py'),
                'analysis_identity': digest(specification(root)), 'replicates': 5000,
                'seed_schedule': 'ORIGINAL_SINGLE_CONFIGURATION_RUNNER_20261019_PLUS_TRIAL',
                'outcomes_accessed': False}
    partition = root/'research/e5/phase2/qualification/partitions'/digest(identity)
    freeze_json(partition/'identity.json', identity)
    simulation.null_cases = lambda spec: [case]
    result = simulation.qualify(root)
    freeze_json(partition/'qualification.json', result)
    return index, result['status']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--indices', type=int, nargs='+', required=True)
    args = parser.parse_args()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for result in pool.map(worker, args.indices):
            print('completed partition', result, flush=True)
