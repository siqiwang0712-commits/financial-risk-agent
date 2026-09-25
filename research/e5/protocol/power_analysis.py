"""Simulation-based prospective power analysis for E5.

Design intent
-------------
E5's primary question is whether structured Agent reasoning adds predictive value *on
top of* the strong deterministic temporal baseline B6. The relevant comparison is
therefore a paired one on a common evaluable cohort, and its power is governed by four
quantities that are all *observable before outcome unlock* except the effect size:

* ``selected_cohort``      — companies entering the Agent cohort
* ``verified_rate``        — P(evaluable outcome | selected), raised by the E5 blinded
                             adjudication layer relative to E4's 0.337
* ``event_prevalence``     — P(event | evaluable)
* ``schema_success_rate``  — P(valid Agent output | evaluable), gated at >= 0.99
* ``score_correlation``    — correlation between the Agent/hybrid score and B6

E4 supplies planning values for the first four; the effect size must be a
*minimum meaningful difference* chosen a priori, never an E4 post-hoc optimum.

Method
------
Monte Carlo. For each design point, paired scores are generated with the exact
construction used by the E4-S audit (``generate_paired``), the paired DeLong test is
applied, and the rejection rate is recorded. DeLong is the prespecified primary test
because the E4-S audit showed the label-permutation design E4 used does not test the
AUROC-equality null.
"""

from __future__ import annotations

import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

AUDIT_DIR = Path(__file__).resolve().parents[2] / "e4_statistical_audit"
sys.path.insert(0, str(AUDIT_DIR))

from e4s_stats import delong_paired, normal_cdf  # noqa: E402
from method_calibration import generate_paired  # noqa: E402

# Planning inputs. Every one of these is either an E4 *operational* rate (allowed for
# planning) or an a-priori design choice. None is an E4 test-set optimum.
PLANNING = {
    "e4_verified_rate": 0.337,
    "e4_event_prevalence": 0.3486646884272997,
    "e4_a2_schema_success": 0.9,
    "e4_observed_b6_auroc": 0.7079581253332041,
    "e4_b6_vs_b0_delta": 0.03030582077254884,
}

DEFAULT_SELECTED_GRID = (600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2400, 3000, 3600)
DEFAULT_DELTA_GRID = (0.02, 0.03, 0.04, 0.05, 0.06, 0.08)
DEFAULT_CORRELATION_GRID = (0.85, 0.90, 0.95)


@dataclass(frozen=True)
class PowerInputs:
    selected_cohort: int
    verified_rate: float
    event_prevalence: float
    schema_success_rate: float
    auc_reference: float
    delta_auroc: float
    score_correlation: float
    alpha: float = 0.05


def expected_counts(inputs: PowerInputs) -> dict[str, float]:
    verified = inputs.selected_cohort * inputs.verified_rate
    evaluable = verified * inputs.schema_success_rate
    events = evaluable * inputs.event_prevalence
    return {
        "selected": float(inputs.selected_cohort),
        "expected_evaluable": evaluable,
        "expected_events": events,
        "expected_non_events": evaluable - events,
        "expected_verified": verified,
    }


def analytic_variance_auc(auc: float, n_events: int, n_non_events: int) -> float:
    """Hanley–McNeil variance of an AUROC estimate.

    ``Var(AUC) = [A(1-A) + (n1-1)(Q1 - A^2) + (n0-1)(Q2 - A^2)] / (n1 n0)``
    with ``Q1 = A / (2 - A)`` and ``Q2 = 2 A^2 / (1 + A)``.
    """
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    numerator = (
        auc * (1.0 - auc)
        + (n_events - 1) * (q1 - auc * auc)
        + (n_non_events - 1) * (q2 - auc * auc)
    )
    return numerator / (n_events * n_non_events)


def analytic_power(
    n_evaluable: int,
    delta_auroc: float,
    correlation: float,
    auc_reference: float = PLANNING["e4_observed_b6_auroc"],
    event_prevalence: float = PLANNING["e4_event_prevalence"],
    alpha: float = 0.05,
) -> dict[str, float] | None:
    """Normal-approximation power for the paired DeLong test.

    ``Var(dAUC) = Var(A1) + Var(A2) - 2 rho sqrt(Var(A1) Var(A2))``. The challenger's
    variance is evaluated at ``auc_reference + delta``.
    """
    n_events = int(round(n_evaluable * event_prevalence))
    n_non_events = n_evaluable - n_events
    if n_events < 2 or n_non_events < 2:
        return None
    var_reference = analytic_variance_auc(auc_reference, n_events, n_non_events)
    var_challenger = analytic_variance_auc(auc_reference + delta_auroc, n_events, n_non_events)
    var_delta = var_reference + var_challenger - 2.0 * correlation * math.sqrt(var_reference * var_challenger)
    if var_delta <= 0:
        return None
    standard_error = math.sqrt(var_delta)
    z_alpha = 1.959963984540054
    z = delta_auroc / standard_error
    power = normal_cdf(z - z_alpha) + normal_cdf(-z - z_alpha)
    return {
        "n_events": float(n_events),
        "n_non_events": float(n_non_events),
        "standard_error_delta": standard_error,
        "z": z,
        "power": power,
    }


def analytic_power_table(
    selected_grid=DEFAULT_SELECTED_GRID,
    delta_grid=DEFAULT_DELTA_GRID,
    correlation_grid=DEFAULT_CORRELATION_GRID,
    verified_rate: float = 0.60,
    event_prevalence: float = PLANNING["e4_event_prevalence"],
    schema_success_rate: float = 0.99,
    auc_reference: float = PLANNING["e4_observed_b6_auroc"],
    alpha: float = 0.05,
) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = {}
    for correlation in correlation_grid:
        for delta in delta_grid:
            key = f"delta={delta:.2f}|rho={correlation:.2f}"
            row: dict[str, float] = {}
            for selected in selected_grid:
                n_evaluable = int(round(selected * verified_rate * schema_success_rate))
                result = analytic_power(n_evaluable, delta, correlation, auc_reference, event_prevalence, alpha)
                row[f"selected={selected}"] = result["power"] if result else float("nan")
            table[key] = row
    return table


def simulate_power(inputs: PowerInputs, replicates: int = 300, seed: int = 20260925) -> dict:
    counts = expected_counts(inputs)
    n_evaluable = max(2, int(round(counts["expected_evaluable"])))
    n_events = max(1, int(round(n_evaluable * inputs.event_prevalence)))
    n_non_events = max(1, n_evaluable - n_events)
    if n_events + n_non_events < 4:
        return {**asdict(inputs), "replicates": replicates, "power": None, "reason": "cohort too small"}

    rejections = 0
    usable = 0
    for replicate in range(replicates):
        rows = generate_paired(
            n_events,
            n_non_events,
            inputs.auc_reference,
            inputs.auc_reference + inputs.delta_auroc,
            inputs.score_correlation,
            random.Random(seed * 1000003 + replicate),
        )
        result = delong_paired(rows)
        if result.get("p_value") is None:
            continue
        usable += 1
        rejections += int(result["p_value"] < inputs.alpha)
    power = rejections / usable if usable else None
    return {
        **asdict(inputs),
        "replicates": replicates,
        "usable_replicates": usable,
        "n_events_simulated": n_events,
        "n_non_events_simulated": n_non_events,
        "expected_counts": counts,
        "power": power,
    }


def power_curve(
    selected_grid=DEFAULT_SELECTED_GRID,
    delta_grid=DEFAULT_DELTA_GRID,
    correlation_grid=DEFAULT_CORRELATION_GRID,
    verified_rate: float = 0.60,
    event_prevalence: float = PLANNING["e4_event_prevalence"],
    schema_success_rate: float = 0.99,
    auc_reference: float = PLANNING["e4_observed_b6_auroc"],
    alpha: float = 0.05,
    replicates: int = 300,
    seed: int = 20260925,
) -> dict:
    points = []
    for correlation in correlation_grid:
        for delta in delta_grid:
            for selected in selected_grid:
                inputs = PowerInputs(
                    selected_cohort=selected,
                    verified_rate=verified_rate,
                    event_prevalence=event_prevalence,
                    schema_success_rate=schema_success_rate,
                    auc_reference=auc_reference,
                    delta_auroc=delta,
                    score_correlation=correlation,
                    alpha=alpha,
                )
                points.append(simulate_power(inputs, replicates=replicates, seed=seed + selected + int(delta * 1000)))
    return {"points": points}


def recommend(
    curve: dict,
    target_power: float = 0.80,
    delta_grid=DEFAULT_DELTA_GRID,
    correlation_grid=DEFAULT_CORRELATION_GRID,
) -> dict:
    points = curve["points"]
    table: dict[str, dict[str, int | None]] = {}
    for correlation in correlation_grid:
        for delta in delta_grid:
            key = f"delta={delta:.2f}|rho={correlation:.2f}"
            eligible = [
                p
                for p in points
                if abs(p["delta_auroc"] - delta) < 1e-9 and abs(p["score_correlation"] - correlation) < 1e-9
            ]
            eligible.sort(key=lambda p: p["selected_cohort"])
            selected = None
            for point in eligible:
                if point["power"] is not None and point["power"] >= target_power:
                    selected = point["selected_cohort"]
                    break
            table[key] = {
                "minimum_selected_cohort": selected,
                "maximum_power_observed": max((p["power"] or 0.0) for p in eligible) if eligible else None,
            }
    worst_case = max(
        (row["minimum_selected_cohort"] for row in table.values() if row["minimum_selected_cohort"] is not None),
        default=None,
    )
    return {"target_power": target_power, "table": table, "worst_case_selected_cohort": worst_case}


def attrition_sensitivity(
    selected_cohort: int,
    delta_auroc: float,
    correlation: float,
    verified_rates=(0.337, 0.45, 0.55, 0.65, 0.75),
    schema_success_rates=(0.90, 0.95, 0.99),
    event_prevalence: float = PLANNING["e4_event_prevalence"],
    auc_reference: float = PLANNING["e4_observed_b6_auroc"],
    replicates: int = 300,
    seed: int = 20260925,
) -> list[dict]:
    output = []
    for verified_rate in verified_rates:
        for schema in schema_success_rates:
            inputs = PowerInputs(
                selected_cohort=selected_cohort,
                verified_rate=verified_rate,
                event_prevalence=event_prevalence,
                schema_success_rate=schema,
                auc_reference=auc_reference,
                delta_auroc=delta_auroc,
                score_correlation=correlation,
            )
            output.append(simulate_power(inputs, replicates=replicates, seed=seed + int(verified_rate * 1000) + int(schema * 1000)))
    return output


def main() -> int:
    output_dir = Path(__file__).resolve().parent
    curve = power_curve()
    recommendation = recommend(curve)
    sensitivity = attrition_sensitivity(
        selected_cohort=1500,
        delta_auroc=0.04,
        correlation=0.90,
    )
    analytic = analytic_power_table()
    # Holm over three primary tests makes the smallest p-value's effective threshold
    # alpha/3 at worst. The conservative Bonferroni-equivalent table below is the
    # multiplicity-adjusted requirement; the Monte Carlo curve above is unadjusted.
    analytic_multiplicity = {
        alpha_used: analytic_power_table(alpha=alpha_used)
        for alpha_used in (0.05, 0.05 / 3.0)
    }
    payload = {
        "status": "DRAFT_NOT_FROZEN",
        "planning_inputs": PLANNING,
        "assumptions": {
            "verified_rate": 0.60,
            "event_prevalence": PLANNING["e4_event_prevalence"],
            "schema_success_rate": 0.99,
            "auc_reference": PLANNING["e4_observed_b6_auroc"],
            "alpha": 0.05,
            "primary_test": "paired DeLong on the evaluable cohort",
            "note": (
                "The verified rate of 0.60 assumes the E5 blinded adjudication layer "
                "converts most REQUIRES_HUMAN_REVIEW cases, versus E4's 0.337 "
                "deterministic-only coverage. This is a design assumption, not an E4 "
                "observation, and must be re-estimated on the outcome-blind adjudication "
                "pilot before freeze."
            ),
        },
        "power_curve": curve,
        "recommendation": recommendation,
        "attrition_sensitivity": sensitivity,
        "analytic_cross_check_power": analytic,
        "analytic_power_multiplicity_adjusted": analytic_multiplicity,
        "caveats": [
            "Planning values are operational rates, not test-set optima.",
            "Power is computed for a paired DeLong test; if the frozen primary test differs, this must be recomputed before freeze.",
            "The analytic cross-check uses the Hanley-McNeil variance with a normal approximation; it should track the Monte Carlo curve closely, and a large divergence indicates a generator or test error rather than a substantive finding.",
        ],
    }
    (output_dir / "power_analysis.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "worst_case_selected_cohort": recommendation["worst_case_selected_cohort"],
        "example_rows": {k: v for k, v in list(recommendation["table"].items())[:6]},
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
