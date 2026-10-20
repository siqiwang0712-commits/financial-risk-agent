"""Development-only joint planning using the exact canonical inference kernel."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.stats import binom

from ..execution.core import digest, file_hash, freeze_json, read_json, require
from .calibration import apply
from .inference import infer_matrix, specification
from .study import CALIBRATION, CalibratedStudyProducer, band


def planning_rows(root):
    producer = CalibratedStudyProducer(root)
    raw = read_json(root / CALIBRATION / 'development_proposals.json')
    oof = read_json(root / 'research/strong_tabular_reference/artifacts/oof_predictions.json')['candidates']['histogram_gradient_boosting__VO']
    s1 = {r['cik']: r for r in oof}
    rows = []
    for r in raw:
        score = apply(producer.artifact, r['raw_score'])
        d = band(score)
        # Optimistic envelope: no additional structural/evidence/reference veto.
        a3 = int(d in {'PASS', 'FLAG'})
        e3 = a3 * int(int(d == 'FLAG') != r['label'])
        other = s1[r['cik']]
        a1 = int(other['score'] < .35 or other['score'] >= .65)
        e1 = a1 * int(int(other['score'] >= .65) != r['label'])
        rows.append([r['label'], a1, e1, a3, e3])
    return np.asarray(rows), producer


def run(root: Path):
    rows, producer = planning_rows(root)
    spec = specification(root)
    identity = {'analysis_specification': spec, 'producer_identity': producer.identity,
                'source_sha256': file_hash(Path(__file__)), 'replicates_per_case': 1000,
                'sample_sizes': [100, 500, 2000], 'verified_fraction': .75,
                'packet_success': .9, 'additional_proposal_success': .95,
                'S4_error_retention': .5, 'S4_withholds_removed_errors': True,
                'interpretation': 'OPTIMISTIC_S4_COVERAGE_ENVELOPE_WITH_HYPOTHETICAL_HALF_ERROR_REMOVAL; NOT_A_VALIDATED_ASSURANCE_EFFECT',
                'selection_rule': 'No N can rescue the development-derived absolute-coverage deficit; use largest valid mature cohort without changing utility.',
                'evaluation_outcomes_used': False}
    output = root/'research/e5/phase2/qualification/power'/digest(identity)
    freeze_json(output/'identity.json', identity)
    reports = []
    for index, n in enumerate(identity['sample_sizes']):
        target = output/f'{n}.json'
        if target.exists():
            reports.append(read_json(target))
            continue
        success = [0, 0, 0]
        for first in range(0, 1000, 100):
            path = output/f'{n}-batch-{first}.json'
            if path.exists():
                batch = read_json(path)
            else:
                count = np.zeros(3, dtype=int)
                for trial in range(first, first+100):
                    seed = 20261019+9000000+index*10000+trial
                    rng = np.random.default_rng(seed)
                    chosen = rows[rng.integers(len(rows), size=n)]
                    chosen = chosen[rng.random(n) < .9]
                    y, a1, e1, a3, e3 = chosen.T
                    # Informative verification, lower for event-positive cases.
                    pi = rows[:, 0].mean()
                    known = rng.random(len(y)) < .75+.2*(pi-y)
                    proposal = rng.random(len(y)) < .95
                    a3 = a3*proposal
                    e3 = e3*proposal
                    removed = e3*(rng.random(len(y)) >= .5)
                    a4 = a3-removed
                    e4 = e3-removed
                    matrix = np.column_stack((known, known*(e1-e4), known*(e3-e4), a4-a1, a4-a3, a4))
                    result = infer_matrix(matrix, spec, simulation_seed=seed)
                    count += [result['comparisons']['P1']['result']=='PASS',
                              result['comparisons']['P2']['result']=='PASS', result['family_success']]
                batch = {'replicates': 100, 'successes': count.tolist()}
                freeze_json(path, batch)
                print(f'power N={n}: {first+100}/1000', flush=True)
            success = [a+b for a, b in zip(success, batch['successes'], strict=True)]
        q = float(rows[:, 3].mean())*.95
        report = {'enrolled_n': n, 'replicates': 1000, 'successes': success,
                  'P1_P2_joint_rates': [v/1000 for v in success],
                  'optimistic_automation_rate_before_additional_vetoes': q,
                  'necessary_absolute_effect_probability_upper_bound_before_packet_attrition': float(binom.sf(int(n*spec['c']), n, q)),
                  'powered_at_80pct': success[2] >= 800}
        freeze_json(target, report)
        reports.append(report)
    result = {'status': 'COMPLETED_DEVELOPMENT_ONLY_UNDERPOWERED', 'analysis_identity': digest(spec),
              'identity': identity, 'cases': reports, 'selected_n': None,
              'sample_size_action': 'LARGEST_VALID_MATURE_COHORT_PENDING_NONOVERLAP_AND_AVAILABILITY_PROOF',
              'thresholds_unchanged': True, 'evaluation_outcomes_used': False}
    require(all(not r['powered_at_80pct'] for r in reports), 'unexpected planning result requires honest review')
    freeze_json(output/'report.json', result)
    return result


if __name__ == '__main__':
    print(run(Path(__file__).resolve().parents[3]))
