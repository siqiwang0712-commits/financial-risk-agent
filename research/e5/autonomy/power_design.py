"""Analytic planning sensitivity only; no cohort, predictions or outcome simulation."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist


def planning() -> dict:
    rows = []
    alpha = 0.025  # Worst-case first Holm step in the two-primary family.
    z = NormalDist().inv_cdf(1 - alpha) + NormalDist().inv_cdf(0.8)
    for prevalence in (0.2, 0.35):
        for evaluable in (0.337, 0.6, 0.9):
            for paired_success in (0.9, 0.99):
                for discordance in (0.05, 0.1, 0.2):
                    for effect in (0.005, 0.01, 0.02, 0.05):
                        # For paired {-1,0,1} error differences, variance=q-delta².
                        required_evaluable = math.ceil(z*z*(discordance-effect*effect)/(effect*effect))
                        retained = evaluable * paired_success
                        needed = math.ceil(required_evaluable/retained)
                        events_needed = math.ceil(100/(retained*prevalence))
                        rows.append({'event_prevalence':prevalence,'evaluable_fraction':evaluable,
                                     'paired_schema_success':paired_success,'error_discordance':discordance,
                                     'hypothetical_effect':effect,'safety_only_approximate_n':needed,
                                     'n_for_100_expected_paired_events':events_needed,
                                     'joint_design_lower_bound_n':max(needed,events_needed)})
    return {'status':'ANALYTIC_PLANNING_NOT_E5_EVIDENCE','alpha_per_first_holm_step':alpha,
            'target_power':0.8,'final_sample_size':None,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'assumptions':'one independent company per pair; normal approximation to paired bounded error differences; q is discordance not score correlation',
            'limitations':'Safety-only optimistic sensitivity, not joint IUT power or a selected effect. Coverage margins, pairing and utility remain blocked. No S4 automatic admission under the adopted policy; no positive-coverage design is currently feasible.',
            'legacy_1200_1500':'Evaluate each grid row rather than retaining an AUROC-derived N. Historical event/verification rates are planning assumptions, not E5 observations.',
            'unlock_gates':['approved utility/effect/coverage constraints','qualified shared proposal and reference','joint safety-and-coverage power','at least 100 actually paired VERIFIED positive events before primary inference, without outcome-driven recruitment'],
            'rows':rows}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    result=planning()
    if args.write:
        Path(__file__).parents[1].joinpath('power_plan.json').write_text(json.dumps(result,indent=1,sort_keys=True)+'\n')
    else:
        print(json.dumps({'status':result['status'],'planning_rows':len(result['rows']),'final_sample_size':None}))
