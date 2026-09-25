"""E4-S: POST-E4 statistical audit runner.

Produces, under ``research/e4_statistical_audit/``:

* ``paired_auc_inference.json``  — the P1 estimand under every inference method
* ``bootstrap_diagnostics.json`` — replicate counts, percentile conventions, BCa inputs
* ``inference_crosscheck.json``  — method-by-method agreement / disagreement verdict
* ``method_calibration.json``    — empirical size and power of each procedure

Nothing in ``research/e4/`` is read except the published summary, and nothing there is
written. ``ORIGINAL_E4`` values are copied verbatim; every other number is labelled
``POST_E4_STATISTICAL_AUDIT`` or ``SURROGATE_RECONSTRUCTION``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

AUDIT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AUDIT_DIR.parents[1]
sys.path.insert(0, str(AUDIT_DIR))

from e4s_stats import (
    cluster_bootstrap,
    delong_paired,
    delta_metric,
    label_permutation_as_implemented,
    marginal_metric,
    score_swap_randomization,
)
from method_calibration import (
    E4_AUROC_B0,
    E4_AUROC_B6,
    E4_N_EVENTS,
    E4_N_NON_EVENTS,
    calibrate,
    generate_paired,
    implied_sd_from_interval,
    match_published_dispersion,
    realised_correlation,
)

PUBLIC_SUMMARY = REPO_ROOT / "research" / "e4" / "public" / "readme_summary.json"
BOOTSTRAP_REPLICATES = 20000
PERMUTATION_REPLICATES = 20000
SEED = 20260925


def load_original() -> dict:
    return json.loads(PUBLIC_SUMMARY.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def original_block(original: dict) -> dict:
    p1 = next(item for item in original["primary_comparisons"] if item["hypothesis"] == "P1")
    b0 = original["e4a_results"]["B0"]
    b6 = original["e4a_results"]["B6"]
    return {
        "evidence_status": "ORIGINAL_E4",
        "source_artifact": "research/e4/public/readme_summary.json",
        "source_artifact_sha256": sha256_file(PUBLIC_SUMMARY),
        "p1": {
            "challenger": p1["challenger"],
            "reference": p1["reference"],
            "n_pairs": p1["n_pairs"],
            "events": p1["events"],
            "observed_delta_auroc": p1["observed_delta"],
            "bootstrap_ci_low": p1["ci_low"],
            "bootstrap_ci_high": p1["ci_high"],
            "bootstrap_replicates": p1["valid_replicates"],
            "permutation_p_value": p1["p_value"],
            "permutation_replicates": p1["valid_permutations"],
            "permutation_null_ci_low": p1["null_ci_low"],
            "permutation_null_ci_high": p1["null_ci_high"],
            "holm_adjusted_p": p1["holm_adjusted_p"],
            "metric": p1["metric"],
        },
        "marginals": {
            "B0": {"auroc": b0["auroc"], "pr_auc": b0["pr_auc"], "n": b0["n"], "events": b0["events"],
                   "ci": original["e4a_intervals"]["B0"]["auroc"]},
            "B6": {"auroc": b6["auroc"], "pr_auc": b6["pr_auc"], "n": b6["n"], "events": b6["events"],
                   "ci": original["e4a_intervals"]["B6"]["auroc"]},
        },
        "claim_gate": original["claim_gate"]["P1"],
    }


def reproduce_published_numbers(original: dict) -> dict:
    """Internal-consistency checks that need no raw data."""
    p1 = next(item for item in original["primary_comparisons"] if item["hypothesis"] == "P1")
    checks = {}

    floor = 1.0 / (p1["valid_permutations"] + 1)
    checks["permutation_p_value_at_floor"] = {
        "published_p": p1["p_value"],
        "floor": floor,
        "equal": abs(p1["p_value"] - floor) < 1e-12,
        "interpretation": (
            "The published permutation p-value equals the minimum attainable value for "
            "2000 permutations, i.e. no permutation replicate reached the observed effect. "
            "The p-value is therefore a censored lower bound, not a resolved quantity."
        ),
    }
    checks["holm_consistency"] = {
        "published_p1": p1["p_value"],
        "published_holm": p1["holm_adjusted_p"],
        "expected_holm_if_P1_rank1_of_3": 3.0 * p1["p_value"],
        "consistent": abs(p1["holm_adjusted_p"] - min(1.0, 3.0 * p1["p_value"])) < 1e-9,
        "note": "P1 is the smallest of the three primary p-values, so Holm multiplies it by 3.",
    }
    bootstrap_sd = implied_sd_from_interval(p1["ci_low"], p1["ci_high"])
    permutation_sd = implied_sd_from_interval(p1["null_ci_low"], p1["null_ci_high"])
    b0_ci = original["e4a_intervals"]["B0"]["auroc"]
    b6_ci = original["e4a_intervals"]["B6"]["auroc"]
    checks["dispersion"] = {
        "paired_bootstrap_implied_sd": bootstrap_sd,
        "label_permutation_null_implied_sd": permutation_sd,
        "ratio_permutation_over_bootstrap": permutation_sd / bootstrap_sd,
        "marginal_B0_implied_sd": implied_sd_from_interval(b0_ci["ci_low"], b0_ci["ci_high"]),
        "marginal_B6_implied_sd": implied_sd_from_interval(b6_ci["ci_low"], b6_ci["ci_high"]),
        "observation": (
            "The label-permutation null is NARROWER than the paired bootstrap distribution "
            "of the same statistic. A permutation null that is narrower than the sampling "
            "distribution of the observed effect is not automatically conservative."
        ),
    }
    checks["metric_identities"] = {
        "delta_equals_b6_minus_b0": abs(
            (original["e4a_results"]["B6"]["auroc"] - original["e4a_results"]["B0"]["auroc"])
            - p1["observed_delta"]
        ),
        "identical_within_1e_12": abs(
            (original["e4a_results"]["B6"]["auroc"] - original["e4a_results"]["B0"]["auroc"])
            - p1["observed_delta"]
        ) < 1e-12,
        "verified_n_equals_paired_n": original["outcomes"]["verified_n"] == p1["n_pairs"],
        "events_equals_verified_events": original["outcomes"]["events"] == p1["events"],
        "one_observation_per_company": original["e4a_results"]["B0"]["company_count"] == original["e4a_results"]["B0"]["n"],
    }
    return checks


def surrogate_block(original: dict) -> dict:
    """Reconstruct paired data matched to E4's published sufficient statistics."""
    p1 = next(item for item in original["primary_comparisons"] if item["hypothesis"] == "P1")
    target_bootstrap_sd = implied_sd_from_interval(p1["ci_low"], p1["ci_high"])
    target_permutation_sd = implied_sd_from_interval(p1["null_ci_low"], p1["null_ci_high"])

    matching = match_published_dispersion(
        target_bootstrap_sd,
        target_permutation_sd,
        grid=[round(0.80 + 0.01 * i, 2) for i in range(18)],
        n_replicates=24,
        bootstrap_samples=200,
        permutation_samples=200,
        seed=SEED,
    )
    correlation = matching["best"]["correlation"]

    rows = generate_paired(
        E4_N_EVENTS, E4_N_NON_EVENTS, E4_AUROC_B0, E4_AUROC_B6, correlation,
        __import__("random").Random(SEED + 7), exact=True,
    )

    bootstrap = cluster_bootstrap(rows, "auroc", samples=BOOTSTRAP_REPLICATES, seed=SEED, with_bca=True)
    bootstrap_pr = cluster_bootstrap(rows, "pr_auc", samples=BOOTSTRAP_REPLICATES, seed=SEED + 1, with_bca=True)
    delong = delong_paired(rows, "auroc")
    permutation = label_permutation_as_implemented(rows, "auroc", samples=PERMUTATION_REPLICATES, seed=SEED)
    swap = score_swap_randomization(rows, "auroc", samples=PERMUTATION_REPLICATES, seed=SEED + 2)

    def pack(result) -> dict:
        return {
            "observed": result.observed,
            "valid_replicates": result.valid_replicates,
            "invalid_replicates": result.invalid_replicates,
            "cluster_count": result.cluster_count,
            "percentile_nearest_rank": list(result.percentile_nearest_rank),
            "percentile_linear": list(result.percentile_linear),
            "bca": list(result.bca) if result.bca else None,
            "standard_error": result.standard_error,
            "bias": result.bias,
        }

    return {
        "evidence_status": "SURROGATE_RECONSTRUCTION",
        "purpose": (
            "E4's frozen per-observation predictions are not published, so P1 cannot be "
            "recomputed from raw data. This block reconstructs a paired sample whose AUROCs "
            "and dispersion match E4's published sufficient statistics, in order to quantify "
            "how far the inference methods disagree at E4's design point. It is NOT an E4 "
            "re-analysis and must not be quoted as E4's DeLong result."
        ),
        "matched_dispersion": {
            "target_bootstrap_sd": target_bootstrap_sd,
            "target_permutation_null_sd": target_permutation_sd,
            "selected_input_correlation": correlation,
            "achieved_bootstrap_sd": matching["best"]["bootstrap_sd"],
            "achieved_permutation_null_sd": matching["best"]["permutation_null_sd"],
            "realised_score_correlation": realised_correlation(rows),
            "identification_note": (
                "The paired bootstrap SD and the label-permutation null SD are two "
                "independent functions of the score correlation, so the correlation is "
                "identified rather than chosen. The residual gap between achieved and "
                "target dispersion bounds the surrogate's fidelity."
            ),
        },
        "design": {
            "n_events": E4_N_EVENTS,
            "n_non_events": E4_N_NON_EVENTS,
            "auc_reference": E4_AUROC_B0,
            "auc_challenger": E4_AUROC_B6,
        },
        "recomputed_observed": {
            "auc_reference": marginal_metric(rows, "reference", "auroc"),
            "auc_challenger": marginal_metric(rows, "challenger", "auroc"),
            "delta_auroc": delta_metric(rows, "auroc"),
            "delta_pr_auc": delta_metric(rows, "pr_auc"),
        },
        "auroc_bootstrap": pack(bootstrap),
        "pr_auc_bootstrap": pack(bootstrap_pr),
        "delong": delong,
        "label_permutation_as_implemented": permutation,
        "score_swap_randomization": swap,
    }


def crosscheck_block(surrogate: dict, original: dict) -> dict:
    p1 = next(item for item in original["primary_comparisons"] if item["hypothesis"] == "P1")
    bootstrap = surrogate["auroc_bootstrap"]
    delong = surrogate["delong"]
    permutation = surrogate["label_permutation_as_implemented"]
    swap = surrogate["score_swap_randomization"]

    def verdict(ci_low, ci_high, p_value) -> str:
        """Interval-based verdict for methods that report an effect interval."""
        positive_ci = ci_low is not None and ci_low > 0
        significant = p_value is not None and p_value < 0.05
        if positive_ci and significant:
            return "SUPPORTS_POSITIVE_DELTA"
        if not positive_ci and not significant:
            return "DOES_NOT_SUPPORT_POSITIVE_DELTA"
        return "INCONCLUSIVE_OR_CONFLICTING"

    def verdict_p_only(p_value, delta) -> str:
        """Randomization tests report a p-value against a null distribution, not an
        effect interval, so their verdict must be read from the p-value alone."""
        if p_value is None:
            return "INCONCLUSIVE_OR_CONFLICTING"
        if p_value < 0.05:
            return "SUPPORTS_POSITIVE_DELTA" if (delta or 0.0) > 0 else "SUPPORTS_NEGATIVE_DELTA"
        return "DOES_NOT_SUPPORT_POSITIVE_DELTA"

    methods = [
        {
            "method": "e4_published_label_permutation",
            "evidence_status": "ORIGINAL_E4",
            "null_hypothesis": "H0_independence (outcome independent of both scores)",
            "tests_stated_hypothesis": False,
            "delta": p1["observed_delta"],
            "ci": [p1["ci_low"], p1["ci_high"]],
            "p_value": p1["p_value"],
            "verdict": "NOT_A_TEST_OF_AUC_EQUALITY",
            "note": "p equals the attainable floor 1/(B+1); the value is censored.",
        },
        {
            "method": "label_permutation_as_implemented",
            "evidence_status": "SURROGATE_RECONSTRUCTION",
            "null_hypothesis": "H0_independence (outcome independent of both scores)",
            "tests_stated_hypothesis": False,
            "delta": permutation.get("observed_delta"),
            "ci": None,
            "p_value": permutation.get("p_value"),
            "verdict": "NOT_A_TEST_OF_AUC_EQUALITY",
            "note": "Reproduced at 20000 replicates; same design as the frozen implementation.",
        },
        {
            "method": "score_swap_randomization",
            "evidence_status": "SURROGATE_RECONSTRUCTION",
            "null_hypothesis": "H0_exch (two score vectors exchangeable; implies equal AUROC)",
            "tests_stated_hypothesis": True,
            "delta": swap.get("observed_delta"),
            "ci": list(swap["null_ci_linear"]) if swap.get("null_ci_linear") else None,
            "p_value": swap.get("p_value"),
            "verdict": verdict_p_only(swap.get("p_value"), swap.get("observed_delta")),
            "note": "Valid but conservative permutation design for the equality hypothesis.",
        },
        {
            "method": "delong_paired",
            "evidence_status": "SURROGATE_RECONSTRUCTION",
            "null_hypothesis": "H0_equality (AUROC challenger = AUROC reference)",
            "tests_stated_hypothesis": True,
            "delta": delong.get("observed_delta"),
            "ci": [delong.get("z_ci_low"), delong.get("z_ci_high")],
            "p_value": delong.get("p_value"),
            "verdict": verdict(delong.get("z_ci_low"), delong.get("z_ci_high"), delong.get("p_value")),
            "note": "Standard asymptotic test for two correlated ROC AUCs.",
        },
        {
            "method": "cluster_bootstrap_percentile",
            "evidence_status": "SURROGATE_RECONSTRUCTION",
            "null_hypothesis": "H0_equality (interval-based)",
            "tests_stated_hypothesis": True,
            "delta": bootstrap["observed"],
            "ci": bootstrap["percentile_linear"],
            "p_value": None,
            "verdict": verdict(bootstrap["percentile_linear"][0], bootstrap["percentile_linear"][1], 0.0),
            "note": "Company-cluster percentile bootstrap; 20000 replicates.",
        },
        {
            "method": "cluster_bootstrap_bca",
            "evidence_status": "SURROGATE_RECONSTRUCTION",
            "null_hypothesis": "H0_equality (interval-based)",
            "tests_stated_hypothesis": True,
            "delta": bootstrap["observed"],
            "ci": bootstrap["bca"],
            "p_value": None,
            "verdict": verdict(bootstrap["bca"][0] if bootstrap["bca"] else None,
                               bootstrap["bca"][1] if bootstrap["bca"] else None, 0.0),
            "note": "Bias-corrected and accelerated with a delete-one-cluster jackknife.",
        },
    ]

    equality_methods = [m for m in methods if m["tests_stated_hypothesis"]]
    verdicts = {m["verdict"] for m in equality_methods}
    direction = {
        m["method"]: (m["delta"] is not None and m["delta"] > 0) for m in equality_methods
    }
    all_positive = all(direction.values())
    if len(verdicts) == 1 and all_positive:
        summary = "CONSISTENT_SUPPORT"
    elif all_positive:
        summary = "DIRECTION_CONSISTENT_STRENGTH_DIFFERS"
    else:
        summary = "METHOD_SENSITIVE"

    return {
        "evidence_status": "POST_E4_STATISTICAL_AUDIT",
        "headline": summary,
        "direction_consistent_across_methods": all_positive,
        "verdicts": sorted(verdicts),
        "methods": methods,
        "scope_warning": (
            "The equality-test rows are computed on the SURROGATE_RECONSTRUCTION. They "
            "quantify method behaviour at E4's design point; they are not E4's own "
            "DeLong/BCa results, which are NOT_INDEPENDENTLY_REPRODUCIBLE because the "
            "frozen per-observation predictions are not published."
        ),
    }


CALIBRATION_REPLICATES = int(__import__("os").environ.get("E4S_CALIBRATION_REPLICATES", "200"))
CALIBRATION_PERMUTATIONS = int(__import__("os").environ.get("E4S_CALIBRATION_PERMUTATIONS", "1000"))


def calibration_block() -> dict:
    null_size = calibrate(
        n_replicates=CALIBRATION_REPLICATES,
        auc_reference=E4_AUROC_B0,
        auc_challenger=E4_AUROC_B0,  # H0_equality with an informative common AUC
        correlation=0.92,
        permutation_samples=CALIBRATION_PERMUTATIONS,
        swap_samples=CALIBRATION_PERMUTATIONS,
        seed=SEED + 11,
    )
    null_size_uninformative = calibrate(
        n_replicates=CALIBRATION_REPLICATES,
        auc_reference=0.5,
        auc_challenger=0.5,
        correlation=0.92,
        permutation_samples=CALIBRATION_PERMUTATIONS,
        swap_samples=CALIBRATION_PERMUTATIONS,
        seed=SEED + 12,
    )
    power = calibrate(
        n_replicates=CALIBRATION_REPLICATES,
        auc_reference=E4_AUROC_B0,
        auc_challenger=E4_AUROC_B6,
        correlation=0.92,
        permutation_samples=CALIBRATION_PERMUTATIONS,
        swap_samples=CALIBRATION_PERMUTATIONS,
        seed=SEED + 13,
    )
    return {
        "evidence_status": "POST_E4_STATISTICAL_AUDIT",
        "purpose": (
            "Empirical size of each procedure under H0_equality. A test whose rejection "
            "rate under H0_equality differs materially from the nominal alpha does not "
            "control the error rate for the hypothesis E4 states."
        ),
        "monte_carlo_precision": {
            "replicates": CALIBRATION_REPLICATES,
            "permutation_samples_per_replicate": CALIBRATION_PERMUTATIONS,
            "note": (
                "The Monte Carlo standard error of a rejection rate near 0.05 with 200 "
                "replicates is about 0.015, so sizes are resolved to roughly +/-0.03 at "
                "95% confidence. This is sufficient to separate nominal calibration from "
                "the materially miscalibrated regime, but not to resolve small deviations."
            ),
        },
        "scenarios": {
            "H0_equality_informative_scores": null_size,
            "H0_independence_scores_at_0_5": null_size_uninformative,
            "alternative_E4_effect": power,
        },
    }


def main() -> int:
    original = load_original()
    reproduction = reproduce_published_numbers(original)
    surrogate = surrogate_block(original)
    crosscheck = crosscheck_block(surrogate, original)
    calibration = calibration_block()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    paired = {
        "audit": "E4-S POST-E4 statistical audit",
        "evidence_labels": ["ORIGINAL_E4", "POST_E4_STATISTICAL_AUDIT", "SURROGATE_RECONSTRUCTION",
                            "NOT_INDEPENDENTLY_REPRODUCIBLE"],
        "original_e4": original_block(original),
        "internal_consistency": reproduction,
        "surrogate": surrogate,
        "reproducibility_blocker": {
            "status": "NOT_INDEPENDENTLY_REPRODUCIBLE",
            "missing_artifacts": [
                "research/e4/_artifacts/predictions.json (frozen per-observation predictions)",
                "research/e4/_artifacts/outcomes.json (frozen labels)",
                "research/e4/_artifacts/features.json",
                "research/e4/_cache/previous_270.json (270-CIK exclusion set, hash-pinned only)",
            ],
            "published_hashes_without_content": {
                "previous_270_sha256": "d73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603",
                "predictions_json_sha256": "6ad033b0149183775e9d37f1011dafb20c255f85105984f5c0ce1b31ec47448d",
                "outcomes_json_sha256": "be82dab0f41af191b9b729187a135ff3533bdde5326d716dade431ae33465f68",
            },
            "consequence": (
                "E4's P1 delta, bootstrap interval and permutation p-value can be read from the "
                "published summary but cannot be recomputed or attacked from published data. "
                "The E4 post-hoc audit's claim of independent integrity verification was "
                "performed with access to the local artifacts and is not reproducible by an "
                "external party from the repository alone."
            ),
        },
    }

    (AUDIT_DIR / "paired_auc_inference.json").write_text(
        json.dumps(paired, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    bootstrap_diag = {
        "audit": "E4-S bootstrap diagnostics",
        "original_e4_published": {
            "replicates": next(i for i in original["primary_comparisons"] if i["hypothesis"] == "P1")["valid_replicates"],
            "percentile_convention": "nearest rank: index = floor((n-1) * p), clamped (E4 _percentile)",
            "interval": [
                next(i for i in original["primary_comparisons"] if i["hypothesis"] == "P1")["ci_low"],
                next(i for i in original["primary_comparisons"] if i["hypothesis"] == "P1")["ci_high"],
            ],
            "implied_sd": implied_sd_from_interval(
                next(i for i in original["primary_comparisons"] if i["hypothesis"] == "P1")["ci_low"],
                next(i for i in original["primary_comparisons"] if i["hypothesis"] == "P1")["ci_high"],
            ),
        },
        "audit_reproduction": {
            "replicates_requested": BOOTSTRAP_REPLICATES,
            "auroc": surrogate["auroc_bootstrap"],
            "pr_auc": surrogate["pr_auc_bootstrap"],
            "percentile_conventions_reported": ["nearest_rank (E4-compatible)", "linear (standard)"],
            "bca_note": (
                "BCa uses a delete-one-cluster jackknife for the acceleration constant, which "
                "is the correct resampling unit for company-clustered observations."
            ),
        },
        "monte_carlo_error": {
            "note": (
                "With B replicates the Monte Carlo standard error of a 2.5% percentile is "
                "approximately sqrt(p(1-p)/B) / density. At B=20000 this is roughly an order "
                "of magnitude smaller than at E4's B=5000, so E4's interval endpoints carry "
                "more simulation noise than the audit's."
            ),
            "e4_replicates": 5000,
            "audit_replicates": BOOTSTRAP_REPLICATES,
        },
    }
    (AUDIT_DIR / "bootstrap_diagnostics.json").write_text(
        json.dumps(bootstrap_diag, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    (AUDIT_DIR / "inference_crosscheck.json").write_text(
        json.dumps(crosscheck, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (AUDIT_DIR / "method_calibration.json").write_text(
        json.dumps(calibration, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "headline": crosscheck["headline"],
        "size_H0_equality_informative": {
            k: v["empirical_rejection_rate"]
            for k, v in calibration["scenarios"]["H0_equality_informative_scores"]["methods"].items()
        },
        "size_H0_independence": {
            k: v["empirical_rejection_rate"]
            for k, v in calibration["scenarios"]["H0_independence_scores_at_0_5"]["methods"].items()
        },
        "power_alt": {
            k: v["empirical_rejection_rate"]
            for k, v in calibration["scenarios"]["alternative_E4_effect"]["methods"].items()
        },
        "surrogate_delong_p": surrogate["delong"].get("p_value"),
        "surrogate_bca": surrogate["auroc_bootstrap"]["bca"],
        "selected_input_correlation": surrogate["matched_dispersion"]["selected_input_correlation"],
        "realised_score_correlation": surrogate["matched_dispersion"]["realised_score_correlation"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
