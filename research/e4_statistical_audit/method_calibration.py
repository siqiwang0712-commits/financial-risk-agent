"""Method-calibration study: does each inference procedure test the null it claims?

The question this module answers
--------------------------------
E4's primary inference for P1 is a **label permutation** test. Its reference
distribution is built by shuffling the outcome labels across observations while
keeping each observation's ``(B0 score, B6 score)`` pair intact. The claim attached to
that p-value is ``H0: AUROC(B6) = AUROC(B0)``.

These are not the same null. The module quantifies the gap by simulation:

* ``H0_equality``   — the AUCs are equal but both scores may be informative.
* ``H0_independence`` — the outcome is independent of *both* scores (what label
  shuffling actually samples).

Under ``H0_independence`` both AUCs sit at 0.5; under ``H0_equality`` they sit at any
common value. A test calibrated for ``H0_independence`` therefore has no guaranteed
size for ``H0_equality``. The simulation measures the actual size of each method.

Measured outcome
----------------
At E4's design point the label-shuffling design's size under ``H0_equality`` is **close to
nominal** (0.025 against a nominal 0.05, 200 replicates), and its power at the E4 effect
(0.930) matches DeLong's (0.935). The audit's prior expectation of material
anti-conservatism was **not** supported. The defect is one of logic — the test targets a
different null — rather than of measured error rate at this design point. Both facts are
reported in ``AUDIT_REPORT.md``; neither replaces the other.

The generator is a bivariate normal model, which cannot reproduce E4's published dispersion
pattern (``AUDIT_REPORT.md`` §6), so the calibration result is model-dependent.

Generator
---------
For a fixed label vector with ``n1`` events and ``n0`` non-events, draw a bivariate
normal ``(z0, z1)`` with correlation ``rho`` and set::

    s0 = z0 + delta0 * y
    s1 = z1 + delta1 * y

with ``delta_k = sqrt(2) * Phi^{-1}(AUC_k)``. Conditioning on the fixed label vector
gives ``Var(s_k) = 1``, ``AUROC(s_k) = Phi(delta_k / sqrt(2))`` and
``corr(s0, s1) = rho`` exactly. Setting ``delta0 = delta1`` produces ``H0_equality``
with an arbitrary common AUC, which is precisely the regime the label-permutation test
must handle.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean
from typing import Any

from e4s_stats import (
    PairedObservation,
    cluster_bootstrap,
    delong_paired,
    label_permutation_as_implemented,
    normal_quantile,
    roc_auc,
    score_swap_randomization,
)

E4_N_EVENTS = 235
E4_N_NON_EVENTS = 439
E4_AUROC_B0 = 0.6776523045606553
E4_AUROC_B6 = 0.7079581253332041


def delta_for_auroc(auc: float) -> float:
    """Shift that yields ``AUROC = auc`` in the generator below."""
    return math.sqrt(2.0) * normal_quantile(auc)


def _solve_delta(noise: Sequence[float], labels: Sequence[int], target_auc: float) -> float:
    """Bisect the label shift so the *realised* AUROC equals ``target_auc`` exactly.

    AUROC is monotone increasing in the shift for a fixed noise realisation, so a
    1-D bisection converges deterministically.
    """
    low, high = 0.0, 8.0
    for _ in range(80):
        middle = (low + high) / 2.0
        value = roc_auc(labels, [z + middle * y for z, y in zip(noise, labels, strict=True)])
        if value is None:
            raise ValueError("labels must contain both classes")
        if value < target_auc:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def realised_correlation(rows: Sequence[PairedObservation]) -> float:
    left = [row.reference_score for row in rows]
    right = [row.challenger_score for row in rows]
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator else 0.0


def generate_paired(
    n_events: int,
    n_non_events: int,
    auc_reference: float,
    auc_challenger: float,
    correlation: float,
    rng: random.Random,
    exact: bool = False,
) -> list[PairedObservation]:
    """Generate paired observations with controlled AUCs and correlation.

    ``exact=False`` (nominal mode) draws ``s_k = z_k + delta_k * y`` with
    ``delta_k = sqrt(2) * Phi^{-1}(AUC_k)``. The conditional distributions
    ``s_k | y=1 ~ N(delta_k, 1)`` and ``s_k | y=0 ~ N(0, 1)`` then hold exactly, so the
    *population* AUC is exactly ``AUC_k`` while the realised sample AUC fluctuates. This
    is the correct data-generating process for a size/power study.

    ``exact=True`` additionally bisects ``delta_k`` so the *realised* sample AUC equals
    ``AUC_k``. This is used only for the surrogate reconstruction, which must reproduce
    E4's published point estimates.
    """
    delta_ref = delta_for_auroc(auc_reference)
    delta_chall = delta_for_auroc(auc_challenger)
    labels = [1] * n_events + [0] * n_non_events
    noise_ref: list[float] = []
    noise_chall: list[float] = []
    for _ in labels:
        z0 = rng.gauss(0.0, 1.0)
        z1 = correlation * z0 + math.sqrt(max(0.0, 1.0 - correlation * correlation)) * rng.gauss(0.0, 1.0)
        noise_ref.append(z0)
        noise_chall.append(z1)
    if exact:
        delta_ref = _solve_delta(noise_ref, labels, auc_reference)
        delta_chall = _solve_delta(noise_chall, labels, auc_challenger)
    return [
        PairedObservation(
            cluster_id=f"C{index:06d}",
            label=label,
            reference_score=noise_ref[index] + delta_ref * label,
            challenger_score=noise_chall[index] + delta_chall * label,
        )
        for index, label in enumerate(labels)
    ]


def calibrate_input_correlation(
    target_realised_correlation: float,
    auc_reference: float,
    auc_challenger: float,
    n_events: int,
    n_non_events: int,
    seed: int,
    trials: int = 12,
) -> tuple[float, float]:
    """Find the latent correlation that yields a target *realised* score correlation.

    Adding ``delta * y`` to both scores inflates their correlation relative to the latent
    correlation, so the input and the realised value differ. Returns
    ``(input_correlation, realised_correlation)``.
    """
    low, high = 0.0, 0.999
    best = (low, 0.0)
    for _ in range(40):
        middle = (low + high) / 2.0
        observed = mean(
            realised_correlation(
                generate_paired(n_events, n_non_events, auc_reference, auc_challenger, middle,
                                random.Random(seed + trial), exact=True)
            )
            for trial in range(trials)
        )
        best = (middle, observed)
        if observed < target_realised_correlation:
            low = middle
        else:
            high = middle
    return best


@dataclass
class MethodOutcome:
    reject: bool
    p_value: float | None
    delta: float | None
    extra: dict[str, Any]


def _methods(
    rows: Sequence[PairedObservation],
    permutation_samples: int,
    swap_samples: int,
    seed: int,
) -> dict[str, MethodOutcome]:
    label_perm = label_permutation_as_implemented(rows, "auroc", samples=permutation_samples, seed=seed)
    swap = score_swap_randomization(rows, "auroc", samples=swap_samples, seed=seed + 1)
    delong = delong_paired(rows, "auroc")
    observed = label_perm.get("observed_delta")
    return {
        "label_permutation_as_implemented": MethodOutcome(
            reject=bool(label_perm.get("p_value") is not None and label_perm["p_value"] < 0.05),
            p_value=label_perm.get("p_value"),
            delta=observed,
            extra={"null_hypothesis": "H0_independence: outcome independent of both scores"},
        ),
        "score_swap_randomization": MethodOutcome(
            reject=bool(swap.get("p_value") is not None and swap["p_value"] < 0.05),
            p_value=swap.get("p_value"),
            delta=observed,
            extra={"null_hypothesis": "H0_exch: the two score vectors are exchangeable (implies equal AUROC)"},
        ),
        "delong_paired": MethodOutcome(
            reject=bool(delong.get("p_value") is not None and delong["p_value"] < 0.05),
            p_value=delong.get("p_value"),
            delta=delong.get("observed_delta"),
            extra={"null_hypothesis": "H0_equality: AUROC(challenger) = AUROC(reference)"},
        ),
    }


def calibrate(
    n_replicates: int,
    n_events: int = E4_N_EVENTS,
    n_non_events: int = E4_N_NON_EVENTS,
    auc_reference: float = E4_AUROC_B0,
    auc_challenger: float = E4_AUROC_B6,
    correlation: float = 0.92,
    permutation_samples: int = 2000,
    swap_samples: int = 2000,
    seed: int = 20260925,
) -> dict[str, Any]:
    """Empirical size (and power) of each inference method.

    ``auc_reference == auc_challenger`` exercises ``H0_equality`` and yields empirical
    size. Unequal AUCs yield empirical power.
    """
    tallies = {
        "label_permutation_as_implemented": {"reject": 0, "p_values": []},
        "score_swap_randomization": {"reject": 0, "p_values": []},
        "delong_paired": {"reject": 0, "p_values": []},
    }
    deltas: list[float] = []
    for replicate in range(n_replicates):
        rows = generate_paired(
            n_events,
            n_non_events,
            auc_reference,
            auc_challenger,
            correlation,
            random.Random(seed * 1000003 + replicate),
        )
        outcome = _methods(rows, permutation_samples, swap_samples, seed * 7919 + replicate)
        for name, result in outcome.items():
            if result.p_value is not None:
                tallies[name]["p_values"].append(result.p_value)
                tallies[name]["reject"] += int(result.reject)
        if outcome["delong_paired"].delta is not None:
            deltas.append(outcome["delong_paired"].delta)

    def summarise(entry: dict[str, Any]) -> dict[str, Any]:
        p_values = entry["p_values"]
        return {
            "empirical_rejection_rate": entry["reject"] / len(p_values) if p_values else None,
            "replicates": len(p_values),
            "median_p_value": sorted(p_values)[len(p_values) // 2] if p_values else None,
            "p_value_at_floor_fraction": (
                sum(1 for value in p_values if value <= 1.0 / (permutation_samples + 1) + 1e-12) / len(p_values)
                if p_values
                else None
            ),
        }

    return {
        "design": {
            "n_events": n_events,
            "n_non_events": n_non_events,
            "auc_reference": auc_reference,
            "auc_challenger": auc_challenger,
            "true_delta": auc_challenger - auc_reference,
            "correlation": correlation,
            "replicates": n_replicates,
            "permutation_samples": permutation_samples,
            "swap_samples": swap_samples,
            "null_under_test": "H0_equality" if abs(auc_challenger - auc_reference) < 1e-12 else "alternative",
        },
        "methods": {name: summarise(entry) for name, entry in tallies.items()},
        "observed_delta_mean": mean(deltas) if deltas else None,
        "nominal_alpha": 0.05,
    }


def match_published_dispersion(
    target_bootstrap_sd: float,
    target_permutation_null_sd: float,
    grid: Sequence[float] | None = None,
    n_replicates: int = 24,
    bootstrap_samples: int = 200,
    permutation_samples: int = 200,
    seed: int = 20260925,
) -> dict[str, Any]:
    """Find the score correlation whose simulated dispersion matches E4's published values.

    E4 published a paired bootstrap interval of ``[0.0136488, 0.0480862]`` and a
    label-permutation null interval of ``[-0.0148209, 0.0154510]``. Converting each to an
    implied standard deviation gives two independent constraints that jointly pin the
    correlation between the two score vectors. This is what makes the surrogate
    reconstruction identifiable rather than arbitrary.
    """
    candidates = list(grid) if grid is not None else [round(0.80 + 0.01 * i, 2) for i in range(18)]
    results: list[dict[str, Any]] = []
    for correlation in candidates:
        bootstrap_sds: list[float] = []
        permutation_sds: list[float] = []
        for replicate in range(n_replicates):
            rows = generate_paired(
                E4_N_EVENTS,
                E4_N_NON_EVENTS,
                E4_AUROC_B0,
                E4_AUROC_B6,
                correlation,
                random.Random(seed * 104729 + replicate),
            )
            bootstrap = cluster_bootstrap(rows, "auroc", samples=bootstrap_samples, seed=seed + replicate, with_bca=False)
            if bootstrap.standard_error is not None:
                bootstrap_sds.append(bootstrap.standard_error)
            permutation = label_permutation_as_implemented(rows, "auroc", samples=permutation_samples, seed=seed + replicate)
            if permutation.get("null_standard_deviation") is not None:
                permutation_sds.append(permutation["null_standard_deviation"])
        bootstrap_sd = mean(bootstrap_sds) if bootstrap_sds else None
        permutation_sd = mean(permutation_sds) if permutation_sds else None
        results.append(
            {
                "correlation": correlation,
                "bootstrap_sd": bootstrap_sd,
                "permutation_null_sd": permutation_sd,
                "bootstrap_gap": abs(bootstrap_sd - target_bootstrap_sd) if bootstrap_sd else None,
                "permutation_gap": abs(permutation_sd - target_permutation_null_sd) if permutation_sd else None,
            }
        )
    best = min(
        results,
        key=lambda row: (row["bootstrap_gap"] or 9e9) + (row["permutation_gap"] or 9e9),
    )
    return {
        "target_bootstrap_sd": target_bootstrap_sd,
        "target_permutation_null_sd": target_permutation_null_sd,
        "grid": results,
        "best": best,
    }


def implied_sd_from_interval(low: float, high: float) -> float:
    """Normal-theory SD implied by a 95% interval (width / (2 * 1.959964))."""
    return (high - low) / (2.0 * 1.959963984540054)
