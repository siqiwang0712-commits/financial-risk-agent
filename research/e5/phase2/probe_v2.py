"""Probe the existing V2 NI component in nested paired automation null cases."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from ..execution.core import file_hash, freeze_json
from ..execution.inference import component


def main():
    output = Path(__file__).parent / 'qualification/v2_nested_ni_probe.json'
    if output.exists():
        print(output.read_text())
        return
    rows = []
    for n in (100, 200, 500):
        rng = np.random.default_rng(20261019 + n)
        observed = rng.binomial(n, .05, 5000)
        rejected = 0
        estimable = 0
        for k in observed:
            x = np.r_[np.full(k, -1.), np.zeros(n-k)]
            boots = -rng.binomial(n, k/n, 20000) / n
            jack = (x.sum() - x) / (n-1)
            result = component(float(x.mean()), boots, jack, -.05)
            estimable += result['p'] is not None
            rejected += result['p'] is not None and result['p'] <= .05
        lower = float(binomtest(rejected, 5000).proportion_ci(.98).low)
        row = {'n': n, 'replicates': 5000, 'draws': 20000, 'boundary': -.05,
               'nested_discordance_probability': .05, 'estimable': estimable,
               'rejections': rejected, 'rate': rejected/5000, 'one_sided99_lower': lower,
               'material_anti_conservatism': lower > .05}
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = {'status': 'FAILED' if any(x['material_anti_conservatism'] for x in rows) else 'PASSED_GRID',
              'scenarios': rows, 'v2_source_sha256': file_hash(Path(__file__).parents[1] / 'coverage_null_v2.py'),
              'ni_component_source_sha256': file_hash(Path(__file__).parents[1] / 'execution/inference.py'),
              'method': 'Exact binomial compression of paired empirical company bootstrap means for differences in {0,-1}; actual existing component() is called for every trial.',
              'outcomes_accessed': False}
    freeze_json(output, report)


if __name__ == '__main__':
    main()
