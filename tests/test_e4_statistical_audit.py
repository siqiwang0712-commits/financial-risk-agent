"""Tests for the POST-E4 statistical audit (E4-S).

These tests cover three things:

1. the audit's statistical primitives are correct;
2. the audit's central claim — that E4's label-permutation design does not test the
   AUROC-equality null it is attached to — is reproducible;
3. the audit did not mutate any frozen E4 artifact.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import verify_previous_270
from e4s_stats import (
    PairedObservation,
    average_precision,
    cluster_bootstrap,
    delong_paired,
    delta_metric,
    holm_adjust,
    label_permutation_as_implemented,
    marginal_metric,
    midranks,
    normal_cdf,
    normal_quantile,
    paired_observations,
    percentile_linear,
    percentile_nearest_rank,
    roc_auc,
    roc_auc_bruteforce,
    score_swap_randomization,
)
from method_calibration import (
    E4_AUROC_B0,
    E4_AUROC_B6,
    calibrate,
    generate_paired,
    implied_sd_from_interval,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = REPO_ROOT / "research" / "e4_statistical_audit"


# ----------------------------------------------------------------------------------
# Primitives
# ----------------------------------------------------------------------------------


def test_normal_quantile_round_trips() -> None:
    for probability in (0.001, 0.025, 0.25, 0.5, 0.75, 0.975, 0.999):
        assert normal_cdf(normal_quantile(probability)) == pytest.approx(probability, abs=1e-9)


def test_normal_quantile_matches_known_values() -> None:
    # Acklam's rational approximation has a documented absolute error below 1.15e-9.
    assert normal_quantile(0.975) == pytest.approx(1.959963984540054, abs=1e-8)
    assert normal_quantile(0.95) == pytest.approx(1.6448536269514722, abs=1e-8)


def test_midranks_average_ties() -> None:
    assert midranks([1.0, 2.0, 2.0, 3.0]) == [1.0, 2.5, 2.5, 4.0]


def test_roc_auc_matches_bruteforce_with_ties() -> None:
    rng = random.Random(11)
    for _ in range(20):
        labels = [rng.randint(0, 1) for _ in range(60)]
        if len(set(labels)) < 2:
            continue
        scores = [round(rng.random(), 1) for _ in range(60)]
        assert roc_auc(labels, scores) == pytest.approx(roc_auc_bruteforce(labels, scores), abs=1e-12)


def test_roc_auc_returns_none_for_single_class() -> None:
    assert roc_auc([1, 1, 1], [0.1, 0.2, 0.3]) is None


def test_average_precision_is_tie_grouped() -> None:
    # A constant score has no discriminative power; the tie-grouped definition must
    # return prevalence, not 1.0.
    assert average_precision([1, 0, 0, 0], [0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.25)


def test_percentile_conventions_differ_as_documented() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile_nearest_rank(values, 0.5) == 2.0
    assert percentile_linear(values, 0.5) == pytest.approx(2.5)


def test_holm_adjust_matches_step_down() -> None:
    tests = [{"p_value": 0.001}, {"p_value": 0.02}, {"p_value": 0.04}]
    adjusted = holm_adjust(tests)
    assert adjusted[0]["holm_adjusted_p"] == pytest.approx(0.003)
    assert adjusted[1]["holm_adjusted_p"] == pytest.approx(0.04)
    assert adjusted[2]["holm_adjusted_p"] == pytest.approx(0.04)


def test_implied_sd_matches_published_intervals() -> None:
    # E4 published P1 bootstrap CI [0.0136488, 0.0480862] and permutation null CI
    # [-0.0148209, 0.0154510].
    assert implied_sd_from_interval(0.0136488241235031, 0.04808618726460545) == pytest.approx(0.0087852, abs=1e-6)
    assert implied_sd_from_interval(-0.014820917946978096, 0.015450976590898113) == pytest.approx(0.0077226, abs=1e-6)


def test_paired_observations_rejects_duplicate_clusters() -> None:
    rows = [
        {"cluster_id": "A", "label": 1, "reference_score": 0.1, "challenger_score": 0.2},
        {"cluster_id": "A", "label": 0, "reference_score": 0.3, "challenger_score": 0.4},
    ]
    with pytest.raises(ValueError, match="duplicate cluster"):
        paired_observations(rows)


# ----------------------------------------------------------------------------------
# DeLong
# ----------------------------------------------------------------------------------


def test_delong_matches_roc_auc() -> None:
    rows = generate_paired(80, 120, 0.65, 0.72, 0.9, random.Random(3), exact=True)
    result = delong_paired(rows)
    labels = [row.label for row in rows]
    assert result["auc_reference"] == pytest.approx(roc_auc(labels, [r.reference_score for r in rows]), abs=1e-12)
    assert result["auc_challenger"] == pytest.approx(roc_auc(labels, [r.challenger_score for r in rows]), abs=1e-12)


def test_delong_zero_variance_for_identical_scores() -> None:
    rows = generate_paired(60, 90, 0.7, 0.7, 1.0, random.Random(4))
    identical = [PairedObservation(r.cluster_id, r.label, r.reference_score, r.reference_score) for r in rows]
    result = delong_paired(identical)
    assert result["observed_delta"] == pytest.approx(0.0, abs=1e-12)
    assert result["variance_delta"] == pytest.approx(0.0, abs=1e-15)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-12)


def test_delong_detects_a_large_paired_difference() -> None:
    rows = generate_paired(200, 400, 0.55, 0.80, 0.85, random.Random(5), exact=True)
    result = delong_paired(rows)
    assert result["observed_delta"] > 0.2
    assert result["p_value"] < 1e-6


def test_delong_agrees_with_cluster_bootstrap_on_a_clear_signal() -> None:
    rows = generate_paired(200, 400, 0.60, 0.75, 0.9, random.Random(6), exact=True)
    delong = delong_paired(rows)
    bootstrap = cluster_bootstrap(rows, "auroc", samples=1500, seed=7, with_bca=True)
    assert delong["observed_delta"] == pytest.approx(bootstrap.observed, abs=1e-12)
    assert bootstrap.percentile_linear[0] > 0
    assert delong["p_value"] < 0.01


# ----------------------------------------------------------------------------------
# Bootstrap
# ----------------------------------------------------------------------------------


def test_cluster_bootstrap_is_seed_reproducible() -> None:
    rows = generate_paired(100, 200, 0.62, 0.70, 0.9, random.Random(8))
    first = cluster_bootstrap(rows, "auroc", samples=500, seed=99)
    second = cluster_bootstrap(rows, "auroc", samples=500, seed=99)
    assert first.percentile_linear == second.percentile_linear
    assert first.bca == second.bca


def test_bca_interval_brackets_the_observed_delta() -> None:
    rows = generate_paired(235, 439, E4_AUROC_B0, E4_AUROC_B6, 0.92, random.Random(9), exact=True)
    result = cluster_bootstrap(rows, "auroc", samples=2000, seed=10, with_bca=True)
    assert result.bca is not None
    assert result.bca[0] < result.observed < result.bca[1]
    assert result.percentile_linear[0] < result.observed < result.percentile_linear[1]


def test_bootstrap_handles_pr_auc() -> None:
    rows = generate_paired(120, 200, 0.60, 0.72, 0.9, random.Random(12))
    result = cluster_bootstrap(rows, "pr_auc", samples=800, seed=13)
    assert result.metric == "pr_auc"
    assert result.observed is not None
    assert result.valid_replicates > 0


# ----------------------------------------------------------------------------------
# Permutation designs
# ----------------------------------------------------------------------------------


def test_label_permutation_p_value_floor_is_reachable() -> None:
    rows = generate_paired(235, 439, E4_AUROC_B0, E4_AUROC_B6, 0.92, random.Random(14), exact=True)
    result = label_permutation_as_implemented(rows, "auroc", samples=200, seed=15)
    assert result["p_value_floor"] == pytest.approx(1 / 201)
    if result["p_value"] == pytest.approx(result["p_value_floor"]):
        assert result["at_p_value_floor"] is True


def test_label_permutation_does_not_reject_identical_scores() -> None:
    rows = generate_paired(150, 250, 0.7, 0.7, 1.0, random.Random(16))
    identical = [PairedObservation(r.cluster_id, r.label, r.reference_score, r.reference_score) for r in rows]
    result = label_permutation_as_implemented(identical, "auroc", samples=300, seed=17)
    assert result["observed_delta"] == pytest.approx(0.0, abs=1e-12)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-12)


def test_score_swap_randomization_has_zero_delta_for_identical_scores() -> None:
    rows = generate_paired(120, 200, 0.68, 0.68, 1.0, random.Random(18))
    identical = [PairedObservation(r.cluster_id, r.label, r.reference_score, r.reference_score) for r in rows]
    result = score_swap_randomization(identical, "auroc", samples=400, seed=19)
    assert result["observed_delta"] == pytest.approx(0.0, abs=1e-12)
    assert result["p_value"] == pytest.approx(1.0, abs=1e-12)


def test_score_swap_randomization_rejects_a_real_difference() -> None:
    rows = generate_paired(200, 400, 0.58, 0.78, 0.9, random.Random(20), exact=True)
    result = score_swap_randomization(rows, "auroc", samples=1000, seed=21)
    assert result["observed_delta"] > 0.15
    assert result["p_value"] < 0.01


def test_generator_hits_the_requested_aucs_exactly() -> None:
    rows = generate_paired(235, 439, E4_AUROC_B0, E4_AUROC_B6, 0.92, random.Random(22), exact=True)
    labels = [row.label for row in rows]
    assert roc_auc(labels, [r.reference_score for r in rows]) == pytest.approx(E4_AUROC_B0, abs=1e-4)
    assert roc_auc(labels, [r.challenger_score for r in rows]) == pytest.approx(E4_AUROC_B6, abs=1e-4)
    assert delta_metric(rows, "auroc") == pytest.approx(0.0303058, abs=1e-5)


def test_generator_population_auc_is_exact_in_nominal_mode() -> None:
    # In nominal mode the conditional distributions are exactly N(delta, 1) and
    # N(0, 1), so the population AUC is exactly Phi(delta / sqrt(2)) = the request.
    observations = [
        generate_paired(400, 800, 0.65, 0.65, 0.9, random.Random(1000 + i))
        for i in range(40)
    ]
    labels = [row.label for row in observations[0]]
    realised = [roc_auc(labels, [r.reference_score for r in rows]) for rows in observations]
    assert sum(realised) / len(realised) == pytest.approx(0.65, abs=0.02)


# ----------------------------------------------------------------------------------
# The audit's central claim: the implemented permutation test is miscalibrated for
# H0: AUROC(B6) = AUROC(B0)
# ----------------------------------------------------------------------------------


@pytest.mark.slow
def test_label_permutation_null_ignores_the_label_score_association() -> None:
    """The defect, demonstrated.

    A test of ``H0: AUROC(challenger) = AUROC(reference)`` must have a reference
    distribution that reflects the observed association between the labels and the scores.
    The label-shuffling design builds its null by destroying that association, so the null
    can only depend on ``(reference_scores, challenger_scores, n_events)``.

    Two datasets are built from the *same* score vectors and the *same* label multiset, but
    with the labels assigned in opposite orders, so their observed deltas are large and of
    opposite sign. If the null depended on the observed association, the two null
    distributions would differ. They do not.

    The comparison averages over seeds because a single shuffle draws a different
    permutation from each input ordering; only the distribution is comparable.
    """
    base = generate_paired(40, 60, 0.85, 0.55, 0.9, random.Random(31337))
    scores = [(row.reference_score, row.challenger_score) for row in base]
    labels = [row.label for row in base]

    rows_a = [PairedObservation(f"C{i:03d}", labels[i], s0, s1) for i, (s0, s1) in enumerate(scores)]
    rows_b = [
        PairedObservation(f"C{i:03d}", labels[len(labels) - 1 - i], s0, s1)
        for i, (s0, s1) in enumerate(scores)
    ]

    delta_a = delta_metric(rows_a, "auroc")
    delta_b = delta_metric(rows_b, "auroc")
    assert delta_a is not None and delta_b is not None
    assert abs(delta_a - delta_b) > 0.2, (
        f"the two datasets must have genuinely different associations, got {delta_a:.4f} vs {delta_b:.4f}"
    )
    assert delta_a * delta_b < 0, "the two associations should have opposite sign"

    def null_summary(rows: list[PairedObservation]) -> tuple[float, float]:
        means: list[float] = []
        deviations: list[float] = []
        for seed in range(12):
            result = label_permutation_as_implemented(rows, "auroc", samples=400, seed=9000 + seed)
            means.append(result["null_mean"])
            deviations.append(result["null_standard_deviation"])
        return sum(means) / len(means), sum(deviations) / len(deviations)

    mean_a, sd_a = null_summary(rows_a)
    mean_b, sd_b = null_summary(rows_b)
    assert mean_a == pytest.approx(0.0, abs=0.01)
    assert mean_b == pytest.approx(0.0, abs=0.01)
    assert sd_a == pytest.approx(sd_b, rel=0.10), (
        f"the null dispersion must not depend on the observed association: {sd_a:.5f} vs {sd_b:.5f}"
    )


@pytest.mark.slow
def test_implemented_permutation_size_is_not_materially_inflated_under_h0_equality() -> None:
    """A NULL RESULT, recorded deliberately.

    The audit's prior expectation was that the label-shuffling design would be materially
    anti-conservative under ``H0_equality``, because its null is narrower than the paired
    bootstrap distribution at E4's design point. The simulation does not support that
    expectation: the empirical size is close to nominal. The interpretive defect stands —
    the test still does not target the equality null — but it does not, at this design
    point, produce an inflated rejection rate.

    This test asserts the finding, not the expectation.
    """
    outcome = calibrate(
        n_replicates=80,
        auc_reference=E4_AUROC_B0,
        auc_challenger=E4_AUROC_B0,
        correlation=0.92,
        permutation_samples=400,
        swap_samples=400,
        seed=777,
    )
    methods = outcome["methods"]
    implemented = methods["label_permutation_as_implemented"]["empirical_rejection_rate"]
    swap = methods["score_swap_randomization"]["empirical_rejection_rate"]
    delong = methods["delong_paired"]["empirical_rejection_rate"]
    # 80 replicates give a Monte Carlo standard error of about 0.025 near p = 0.05.
    for name, rate in (
        ("label_permutation_as_implemented", implemented),
        ("score_swap_randomization", swap),
        ("delong_paired", delong),
    ):
        assert rate < 0.20, f"{name} size {rate:.3f} is materially inflated"
    assert implemented < 0.20
    assert abs(implemented - 0.05) < 0.10, (
        f"the implemented design is expected to sit near nominal alpha, observed {implemented:.3f}"
    )


@pytest.mark.slow
def test_power_at_the_e4_effect_is_similar_across_the_valid_methods() -> None:
    """At the E4 effect size the three procedures agree, which is why P1 is unaffected."""
    outcome = calibrate(
        n_replicates=80,
        auc_reference=E4_AUROC_B0,
        auc_challenger=E4_AUROC_B6,
        correlation=0.92,
        permutation_samples=400,
        swap_samples=400,
        seed=778,
    )
    methods = outcome["methods"]
    delong = methods["delong_paired"]["empirical_rejection_rate"]
    implemented = methods["label_permutation_as_implemented"]["empirical_rejection_rate"]
    swap = methods["score_swap_randomization"]["empirical_rejection_rate"]
    assert delong > 0.6, f"DeLong power {delong:.3f} is implausibly low at the E4 effect"
    assert abs(delong - implemented) < 0.15
    assert abs(delong - swap) < 0.15


@pytest.mark.slow
def test_implemented_permutation_is_well_calibrated_under_h0_independence() -> None:
    """The label-shuffling design *is* valid for its own null, which is the point.

    Under H0_independence (both scores uninformative) the permutation null coincides
    with the sampling null, so size should be near nominal. This confirms the diagnosis
    is about the null being the wrong one, not about the implementation being buggy.
    """
    outcome = calibrate(
        n_replicates=80,
        auc_reference=0.5,
        auc_challenger=0.5,
        correlation=0.92,
        permutation_samples=400,
        swap_samples=400,
        seed=778,
    )
    implemented = outcome["methods"]["label_permutation_as_implemented"]["empirical_rejection_rate"]
    assert implemented < 0.15


# ----------------------------------------------------------------------------------
# Artifact integrity: the audit must not have touched E4
# ----------------------------------------------------------------------------------


def test_frozen_e4_artifacts_are_byte_identical() -> None:
    manifest = json.loads((AUDIT_DIR / "e4_frozen_artifact_manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = REPO_ROOT / relative
        assert path.is_file(), f"frozen E4 artifact missing: {relative}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"frozen E4 artifact modified: {relative}"


def test_audit_does_not_write_into_the_frozen_e4_directory() -> None:
    manifest = json.loads((AUDIT_DIR / "e4_frozen_artifact_manifest.json").read_text(encoding="utf-8"))
    recorded = set(manifest["files"])
    present = {
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "research" / "e4").rglob("*")
        if p.is_file()
    }
    assert present == recorded, "the audit added or removed files under research/e4"


# ----------------------------------------------------------------------------------
# Published replication artifacts: the audit must be verifiable by a third party
# ----------------------------------------------------------------------------------

REPLICATION_DIR = AUDIT_DIR / "replication"


def _replication_manifest() -> dict:
    return json.loads((REPLICATION_DIR / "manifest.json").read_text(encoding="utf-8"))


def test_replication_artifacts_match_their_published_hashes() -> None:
    """The audit criticised E4 for unpublished rows; its own rows must be published and
    hash-verified."""
    for entry in _replication_manifest()["files"]:
        path = REPO_ROOT / entry["path"]
        assert path.is_file(), f"published replication artifact missing: {entry['path']}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], (
            f"published replication artifact modified: {entry['path']}"
        )


def test_replication_publishes_the_rows_needed_to_recompute_the_inference() -> None:
    analysis = json.loads((REPLICATION_DIR / "analysis.json").read_text(encoding="utf-8"))
    required = {"observation_id", "masked_company_id", "model_id", "score", "label"}
    assert analysis, "analysis.json is empty"
    for row in analysis[:50]:
        assert required <= set(row), f"analysis row is missing fields: {required - set(row)}"
    models = {row["model_id"] for row in analysis}
    assert {"B0", "B6"} <= models


def test_replication_cohort_has_one_observation_per_company() -> None:
    cohort = json.loads((REPLICATION_DIR / "cohort.json").read_text(encoding="utf-8"))
    assert len({row["cik"] for row in cohort}) == len(cohort)
    assert len({row["observation_id"] for row in cohort}) == len(cohort)
    assert len(cohort) == 2000


def test_replication_cohort_is_disjoint_from_the_published_development_corpus() -> None:
    """The frozen cohort algorithm excludes the historical development and public-pilot
    companies; the published cohort must show that exclusion held."""
    cohort = json.loads((REPLICATION_DIR / "cohort.json").read_text(encoding="utf-8"))
    cohort_ciks = {str(row["cik"]).zfill(10) for row in cohort}
    development = json.loads(
        (REPO_ROOT / "research" / "empirical_v1" / "numeric_corpus.json").read_text(encoding="utf-8")
    )
    development_ciks = {str(row["cik"]).zfill(10) for row in development}
    public = json.loads(
        (REPO_ROOT / "research" / "benchmark" / "public_company_observations.json").read_text(encoding="utf-8")
    )
    public_ciks = {
        str(row.get("cik", "")).zfill(10) for row in public.get("examples", []) if row.get("cik")
    }
    assert not (cohort_ciks & development_ciks), "cohort overlaps the historical development corpus"
    assert not (cohort_ciks & public_ciks), "cohort overlaps the public pilot"


def test_replication_rows_reproduce_the_published_real_data_inference() -> None:
    """Recompute the audit's headline real-data statistics from the published rows."""
    analysis = json.loads((REPLICATION_DIR / "analysis.json").read_text(encoding="utf-8"))
    published = json.loads((AUDIT_DIR / "replication_crosscheck.json").read_text(encoding="utf-8"))

    labels = {row["observation_id"]: int(row["label"]) for row in analysis}
    by_model: dict[str, dict[str, float]] = {}
    for row in analysis:
        by_model.setdefault(row["model_id"], {})[row["observation_id"]] = row["score"]
    common = sorted(set(by_model["B0"]) & set(by_model["B6"]))
    rows = [
        PairedObservation(
            cluster_id=observation_id,
            label=labels[observation_id],
            reference_score=by_model["B0"][observation_id],
            challenger_score=by_model["B6"][observation_id],
        )
        for observation_id in common
        if labels[observation_id] in (0, 1)
    ]

    assert len(rows) == published["cohort_provenance"]["n_pairs"]
    assert sum(row.label for row in rows) == published["cohort_provenance"]["events"]
    assert marginal_metric(rows, "reference", "auroc") == pytest.approx(published["marginals"]["B0_auroc"], abs=1e-12)
    assert marginal_metric(rows, "challenger", "auroc") == pytest.approx(published["marginals"]["B6_auroc"], abs=1e-12)
    assert delta_metric(rows, "auroc") == pytest.approx(published["audit_independent_implementation"]["delta_auroc"], abs=1e-12)

    delong = delong_paired(rows)
    expected = published["audit_independent_implementation"]["delong"]
    assert delong["observed_delta"] == pytest.approx(expected["observed_delta"], abs=1e-12)
    assert delong["standard_error_delta"] == pytest.approx(expected["standard_error_delta"], abs=1e-12)
    assert delong["p_value"] == pytest.approx(expected["p_value"], abs=1e-12)
    assert delong["p_value"] < 0.05, "the published real-data inference must reject H0_equality"


def test_verifier_reports_a_pass_on_the_published_artifacts() -> None:
    """The verifier is the artifact a reviewer runs; it must actually pass."""
    # Write the result to a scratch path: a quick run must not overwrite the committed
    # 20000-replicate verification_result.json.
    with tempfile.TemporaryDirectory() as scratch:
        result = subprocess.run(
            [
                sys.executable,
                str(AUDIT_DIR / "verify_audit.py"),
                "--quick",
                "--out",
                str(Path(scratch) / "verification_result.json"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
    assert result.returncode == 0, f"verify_audit.py failed:\n{result.stdout}\n{result.stderr}"
    assert "checks passed" in result.stdout
    assert "FAIL" not in result.stdout


# ----------------------------------------------------------------------------------
# previous_270 recovery tooling
# ----------------------------------------------------------------------------------

def test_pinned_previous_270_hash_matches_the_documented_value() -> None:
    """The blocker is only meaningful if the pinned constant is the one the audit cites.

    The fallback literal is checked against the frozen module's *source text*, so it cannot
    drift even when the full FinRisk dependency stack is not importable.
    """
    pinned = verify_previous_270.PREVIOUS_270_SHA256
    assert pinned == "d73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603"
    source = (REPO_ROOT / "backend" / "finrisk" / "e4_core.py").read_text(encoding="utf-8")
    assert f'PREVIOUS_270_SHA256 = "{pinned}"' in source, (
        "the audit's pinned hash no longer matches finrisk.e4_core"
    )
    report = (AUDIT_DIR / "AUDIT_REPORT.md").read_text(encoding="utf-8")
    assert pinned[:12] in report


def test_previous_270_verifier_rejects_a_wrong_hash(tmp_path: Path) -> None:
    candidate = tmp_path / "previous_270.json"
    candidate.write_text(json.dumps([{"cik": "0000000001"}]), encoding="utf-8")
    result = verify_previous_270.verify_candidate(candidate)
    assert result["status"] == "REJECTED_HASH_MISMATCH"
    assert result["hash_matches"] is False


def test_previous_270_verifier_reports_a_missing_file(tmp_path: Path) -> None:
    result = verify_previous_270.verify_candidate(tmp_path / "absent.json")
    assert result["status"] == "MISSING"


def test_previous_270_verifier_reports_shape_information(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.json"
    rows = [{"cik": f"{i:010d}"} for i in range(270)]
    candidate.write_text(json.dumps(rows), encoding="utf-8")
    result = verify_previous_270.verify_candidate(candidate)
    # The hash cannot match a synthetic file, but the shape diagnostics must still be filled in.
    assert result["count"] == 270
    assert result["cik_count"] == 270
    assert result["unique_ciks"] == 270
    assert result["all_ten_digits"] is True
    assert result["status"] == "REJECTED_HASH_MISMATCH"


def test_cohort_comparison_counts_shared_and_distinct_companies() -> None:
    e4 = [
        {"cik": "0000000001", "observation_id": "E4_OBS_000001"},
        {"cik": "0000000002", "observation_id": "E4_OBS_000002"},
        {"cik": "0000000003", "observation_id": "E4_OBS_000003"},
    ]
    replication = [
        {"cik": "0000000001", "observation_id": "R_OBS_000001"},
        {"cik": "0000000003", "observation_id": "R_OBS_000002"},
        {"cik": "0000000004", "observation_id": "R_OBS_000003"},
    ]
    result = verify_previous_270.compare_cohorts(e4, replication)
    assert result["e4_cohort_size"] == 3
    assert result["replication_cohort_size"] == 3
    assert result["shared"] == 2
    assert result["in_e4_only"] == 1
    assert result["in_replication_only"] == 1
    assert result["symmetric_difference"] == 2
    assert result["index_mapping_examples"][0]["same_index"] is False


def test_committed_verification_result_is_a_full_replicate_run() -> None:
    """Guard against a quick-mode run silently downgrading the committed evidence.

    ``verify_audit.py`` writes its result file by default. The test above points it at a
    scratch path precisely so that running the suite cannot replace the committed
    20,000-replicate result with a 2,000-replicate one; this test pins that property.
    """
    payload = json.loads((AUDIT_DIR / "verification_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["replicates"] == 20000, (
        "the committed verification result must come from a full 20000-replicate run"
    )
    assert not [check for check in payload["checks"] if check["status"] != "PASS"]
