"""Supported null-grid partition launcher; original scheduler failure is retained."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor

from .shards_v2 import worker

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--indices', type=int, nargs='+', required=True)
    args = parser.parse_args()
    with ProcessPoolExecutor(max_workers=2) as pool:
        for result in pool.map(worker, args.indices):
            print('completed partition', result, flush=True)
