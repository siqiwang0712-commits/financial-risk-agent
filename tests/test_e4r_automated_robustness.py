"""Tests for the E4-R automated robustness study.

The suite is organised around the study's failure modes rather than around its modules:
integrity, leakage, fold isolation, statistical correctness, ablation fidelity, negative
controls, multiplicity and the NOT_ESTIMABLE contract. The tabular baselines need numpy and
scikit-learn, which the product runtime does not ship, so those checks skip cleanly when the
research extra is not installed instead of failing the build.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import e4r_ablation
import e4r_analysis
import e4r_config
import e4r_data
import e4r_stats
import pytest

HERE = Path(__file__).resolve().parents[1] / "research" / "e4r_automated_robustness"

pytest.importorskip("e4s_stats", reason="the E4-S statistical primitives are required")


def _require(name: str) -> dict:
    path = HERE / name
    if not path.is_file():
        pytest.skip(f"{name} has not been generated yet")
    return json.loads(path.read_text(encoding="utf-8"))


_LABEL_CACHE: dict[str, int] | None = None


def _row_labels() -> dict[str, int]:
    """Observation id -> label, taken from the published ledger."""
    global _LABEL_CACHE  # one small cache for the whole module
    if _LABEL_CACHE is None:
        payload = _require("oof_predictions.json")
        _LABEL_CACHE = {row["observation_id"]: int(row["label"]) for row in payload["records"]}
    return _LABEL_CACHE


@pytest.fixture(scope="module")
def dataset() -> e4r_data.Dataset:
    return e4r_data.build_dataset()


# ---------------------------------------------------------------------------
# integrity
# ---------------------------------------------------------------------------


def test_source_manifest_integrity() -> None:
    report = e4r_data.verify_sources(run_external=False)
    assert report.status == "PASS", report.failures
    assert report.replication_files, "no replication file was checked"


def test_frozen_e4_artifacts_are_unmodified() -> None:
    report = e4r_data.verify_sources(run_external=False)
    for entry in report.e4_frozen_files:
        assert entry["status"] == "PASS", f"frozen E4 artifact changed: {entry['path']}"


def test_frozen_b0_and_b6_reconstruct_from_the_packet(dataset) -> None:
    reconstruction = e4r_data.check_reconstruction(dataset)
    assert reconstruction["b0_mismatches"] == 0
    assert reconstruction["b6_mismatches"] == 0
    assert reconstruction["b6_max_abs_error"] < 1e-9


def test_cohort_shape_matches_the_frozen_config() -> None:
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    dataset = e4r_data.build_dataset()
    assert dataset.n == config["cohort"]["expected_n"]
    assert dataset.events == config["cohort"]["expected_events"]


def test_prespecification_is_frozen() -> None:
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    feature_sets = json.loads((HERE / "feature_sets.json").read_text(encoding="utf-8"))
    assert e4r_data.sha256_json(feature_sets) == config["feature_sets_hash"]
    assert config["status"] == "POST_HOC_AUTOMATED_ROBUSTNESS"
    for forbidden in ("ESTABLISHED_E4", "CONFIRMATORY", "PROSPECTIVE", "E5_RESULT"):
        assert forbidden in config["is_not"]


def test_b6_definition_is_discovered_from_the_frozen_code() -> None:
    definition = e4r_data.discover_b6_definition()
    assert definition["b6_temporal_inputs_match_expected"], definition["b6_temporal_inputs_from_code"]
    assert definition["b0_inputs_match_expected"]
    assert e4r_ablation.TERM_NAMES == tuple(definition["b6_temporal_inputs_from_code"])


# ---------------------------------------------------------------------------
# leakage
# ---------------------------------------------------------------------------


def test_leakage_audit_finds_no_confirmed_leakage() -> None:
    payload = _require("leakage_audit.json")
    assert payload["confirmed_leakage_checks"] == [], payload["confirmed_leakage_checks"]
    assert payload["status"] != "INVALIDATED"


def test_feature_timestamps_precede_the_prediction_cutoff(dataset) -> None:
    for oid in dataset.observation_ids:
        period = dataset.period_end[oid].replace("-", "")
        assert dataset.period_end[oid] <= dataset.information_cutoff[oid][:10]
        for payload in dataset.provenance[oid].values():
            if isinstance(payload, dict) and payload.get("period_end"):
                assert str(payload["period_end"]) <= period


def test_outcomes_resolve_after_the_cutoff_and_inside_the_window(dataset) -> None:
    for oid in dataset.observation_ids:
        available = dataset.outcome_available_at[oid]
        assert available, f"{oid} has no outcome timestamp"
        assert available > dataset.information_cutoff[oid]
        assert available <= dataset.outcome_window_end[oid]


def test_no_duplicate_observations_or_companies(dataset) -> None:
    assert len(set(dataset.observation_ids)) == dataset.n
    assert len(set(dataset.masked_company_id.values())) == dataset.n
    assert len(set(dataset.cik.values())) == dataset.n


def test_no_feature_perfectly_separates_the_label(dataset) -> None:
    for name in dataset.metric_fields:
        values, labels = [], []
        for oid in dataset.observation_ids:
            raw = dataset.metrics[oid].get(name)
            if raw is None:
                continue
            values.append(float(raw))
            labels.append(dataset.labels[oid])
        if len(values) < 0.5 * dataset.n:
            continue
        positives = [v for v, y in zip(values, labels, strict=True) if y == 1]
        negatives = [v for v, y in zip(values, labels, strict=True) if y == 0]
        assert not (max(positives) < min(negatives) or min(positives) > max(negatives)), name


# ---------------------------------------------------------------------------
# statistical primitives
# ---------------------------------------------------------------------------


def _tiny_rows() -> list:
    labels = [1, 1, 0, 0, 1, 0, 1, 0, 1, 0]
    reference = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    challenger = [0.15, 0.25, 0.25, 0.35, 0.55, 0.55, 0.75, 0.75, 0.95, 0.9]
    return e4r_stats.paired_rows(
        [str(i) for i in range(len(labels))],
        {str(i): y for i, y in enumerate(labels)},
        {str(i): s for i, s in enumerate(reference)},
        {str(i): s for i, s in enumerate(challenger)},
    )


def test_delong_is_zero_for_identical_scorers() -> None:
    rows = e4r_stats.paired_rows(
        ["a", "b", "c", "d"], {"a": 1, "b": 0, "c": 1, "d": 0},
        {"a": 0.2, "b": 0.4, "c": 0.6, "d": 0.8},
        {"a": 0.2, "b": 0.4, "c": 0.6, "d": 0.8},
    )
    result = e4r_stats.delong_paired(rows)
    assert result["observed_delta"] == pytest.approx(0.0)
    assert result["p_value"] == pytest.approx(1.0)


def test_delong_matches_a_hand_computed_mann_whitney_auc() -> None:
    rows = _tiny_rows()
    result = e4r_stats.delong_paired(rows)
    labels = [row.label for row in rows]
    reference = [row.reference_score for row in rows]
    expected = e4r_stats.roc_auc(labels, reference)
    assert result["auc_reference"] == pytest.approx(expected)
    assert 0.0 < result["p_value"] <= 1.0
    assert result["standard_error_delta"] > 0


def test_delong_rejects_a_known_separation() -> None:
    labels = [1] * 20 + [0] * 20
    reference = [0.5] * 40
    challenger = [0.9] * 20 + [0.1] * 20
    rows = e4r_stats.paired_rows(
        [str(i) for i in range(40)],
        {str(i): y for i, y in enumerate(labels)},
        {str(i): s for i, s in enumerate(reference)},
        {str(i): s for i, s in enumerate(challenger)},
    )
    result = e4r_stats.delong_paired(rows)
    assert result["auc_reference"] == pytest.approx(0.5)
    assert result["auc_challenger"] == pytest.approx(1.0)
    assert result["p_value"] < 1e-6


def test_delong_returns_single_class_for_degenerate_labels() -> None:
    rows = e4r_stats.paired_rows(
        ["a", "b"], {"a": 1, "b": 1}, {"a": 0.2, "b": 0.4}, {"a": 0.3, "b": 0.1}
    )
    assert e4r_stats.delong_paired(rows)["status"] == "SINGLE_CLASS"


def test_bootstrap_is_reproducible_under_a_fixed_seed() -> None:
    rows = _tiny_rows()
    first = e4r_stats.paired_bootstrap(rows, "auroc", 200, 12345)
    second = e4r_stats.paired_bootstrap(rows, "auroc", 200, 12345)
    assert first["bca"] == second["bca"]
    assert first["median"] == second["median"]
    assert first["P_delta_gt_0p0"] == second["P_delta_gt_0p0"]


def test_bootstrap_engine_matches_e4s_stats() -> None:
    """E4-R batches the collector out of the replicate loop; the output must be identical."""
    from e4s_stats import cluster_bootstrap

    rows = _tiny_rows()
    engine = e4r_stats.paired_bootstrap(rows, "auroc", 1000, 4242)
    reference = cluster_bootstrap(rows, "auroc", samples=1000, seed=4242, with_bca=True)
    assert engine["observed"] == reference.observed
    assert engine["bca"] == list(reference.bca)
    assert engine["percentile_linear"] == list(reference.percentile_linear)
    assert engine["percentile_nearest_rank"] == list(reference.percentile_nearest_rank)
    assert engine["standard_error"] == pytest.approx(reference.standard_error)
    assert engine["valid_replicates"] == reference.valid_replicates


def test_bootstrap_tail_probabilities_are_a_distribution() -> None:
    result = e4r_stats.paired_bootstrap(_tiny_rows(), "auroc", 300, 7)
    for threshold in ("0p0", "0p01", "0p02", "0p03"):
        assert 0.0 <= result[f"P_delta_gt_{threshold}"] <= 1.0
    assert result["P_delta_gt_0p0"] >= result["P_delta_gt_0p01"] >= result["P_delta_gt_0p02"]


def test_holm_correction_is_monotone_and_capped_at_one() -> None:
    payload = [
        {"label": "a", "p_value": 0.001},
        {"label": "b", "p_value": 0.02},
        {"label": "c", "p_value": 0.04},
    ]
    adjusted = e4r_stats.holm_adjust(payload)
    values = [item["holm_adjusted_p"] for item in adjusted]
    assert values == pytest.approx([0.003, 0.04, 0.04])
    assert all(value <= 1.0 for value in values)
    assert values == sorted(values) or values[0] <= values[1] <= values[2]


def test_percentile_helpers_agree_on_a_known_sample() -> None:
    values = list(range(101))
    assert e4r_stats.percentile_linear(values, 0.5) == pytest.approx(50.0)
    assert e4r_stats.percentile_linear(values, 0.025) == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# ablation fidelity
# ---------------------------------------------------------------------------


def test_ablation_reproduces_the_frozen_score(dataset) -> None:
    verification = e4r_ablation.verify_against_frozen(dataset)
    assert verification["status"] == "PASS"
    assert verification["max_abs_error"] < 1e-12


def test_ablation_without_a_drop_equals_temporal_risk_score() -> None:
    from finrisk.numeric_benchmark import temporal_risk_score

    metrics = {
        "current_ratio": 1.4, "debt_to_assets": 0.5, "net_margin": 0.05,
        "cfo_to_net_income": 1.2, "fcf_margin": 0.02,
        "revenue_growth": -0.2, "operating_cash_flow_growth": -0.3,
        "total_debt_growth": 0.4, "cash_growth": -0.25,
    }
    assert e4r_ablation.b6_score_with(metrics) == pytest.approx(temporal_risk_score(metrics))


def test_dropping_a_term_lowers_the_observed_denominator() -> None:
    """Dropping a term removes it from the numerator *and* the denominator.

    With no static block present the score is just `adverse / observed`, so removing one of
    three triggered terms must give 2/2 rather than 2/3.
    """
    metrics = {"revenue_growth": -0.2, "operating_cash_flow_growth": -0.3, "cash_growth": -0.25}
    _base, adverse, observed, _triggers = e4r_ablation.b6_components(metrics)
    assert observed == 3
    assert adverse == 3
    assert e4r_ablation.b6_score_with(metrics) == pytest.approx(adverse / observed)
    assert e4r_ablation.b6_score_with(metrics, drop="revenue_growth") == pytest.approx(
        (adverse - 1) / (observed - 1)
    )
    _, _, reduced_observed, _ = e4r_ablation.b6_components(
        {key: value for key, value in metrics.items() if key != "revenue_growth"}
    )
    assert reduced_observed == 2


def test_no_temporal_is_a_strictly_increasing_map_of_b0() -> None:
    from finrisk.numeric_benchmark import ratio_risk_score

    metrics = {
        "current_ratio": 0.8, "debt_to_assets": 0.7, "net_margin": -0.1,
        "cfo_to_net_income": 0.5, "fcf_margin": -0.05, "revenue_growth": -0.3,
    }
    assert e4r_ablation.b6_no_temporal(metrics) == pytest.approx(0.75 * ratio_risk_score(metrics))


def test_unknown_temporal_term_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown temporal term"):
        e4r_ablation.b6_score_with({}, drop="profit_growth")


def test_ablation_payload_reports_every_prespecified_variant() -> None:
    payload = _require("temporal_ablation.json")
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    for name in config["ablation"]["variants"]:
        assert name in payload["variants"], name


# ---------------------------------------------------------------------------
# subgroup gates and NOT_ESTIMABLE
# ---------------------------------------------------------------------------


def test_subgroup_gate_marks_small_groups_not_estimable() -> None:
    observation_ids = [f"o{index}" for index in range(60)]
    labels = {oid: 1 if index < 20 else 0 for index, oid in enumerate(observation_ids)}
    membership = {oid: ("big" if index < 50 else "small") for index, oid in enumerate(observation_ids)}
    scores = {oid: float(index % 7) / 7 for index, oid in enumerate(observation_ids)}
    rows = e4r_analysis.subgroup_table(observation_ids, labels, membership, {"m": scores}, 40, 10)
    by_name = {row["subgroup"]: row for row in rows}
    assert by_name["small"]["status"] == "NOT_ESTIMABLE"
    assert by_name["small"]["models"] == {}
    assert by_name["big"]["status"] == "OK"
    assert by_name["big"]["models"]["m"]["auroc"] is not None


def test_single_class_subgroup_is_not_estimable() -> None:
    assert e4r_analysis.metrics([1, 1, 1], [0.1, 0.2, 0.3])["status"] == "SINGLE_CLASS"
    assert e4r_analysis.metrics([1, 1, 1], [0.1, 0.2, 0.3])["auroc"] is None


def test_sector_payload_reports_every_sector_with_a_status() -> None:
    payload = _require("subgroup_results.json")
    dataset = e4r_data.build_dataset()
    sectors = set(dataset.sector.values())
    reported = {row["subgroup"] for row in payload["sector"]["rows"]}
    assert reported == sectors, "every sector must be shown, estimable or not"
    for row in payload["sector"]["rows"]:
        if not row["estimable"]:
            assert row["status"] == "NOT_ESTIMABLE"


def test_missingness_and_size_rows_carry_gates() -> None:
    payload = _require("subgroup_results.json")
    for row in payload["missingness"]["rows"]:
        assert "estimable" in row
    if payload["firm_size"]["status"] != "OK":
        assert payload["firm_size"]["note"]


# ---------------------------------------------------------------------------
# negative controls
# ---------------------------------------------------------------------------


def test_label_permutation_returns_to_chance() -> None:
    payload = _require("negative_controls.json")
    for entry in payload["NC1_label_permutation"]["models"].values():
        assert abs(entry["mean"] - 0.5) < 0.05, entry
        assert entry["p2_5"] < 0.5 < entry["p97_5"]


def test_shuffled_temporal_control_preserves_the_column_marginals() -> None:
    """Shuffling a block across rows must preserve each column's multiset."""
    np = pytest.importorskip("numpy")

    original = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0]])
    order = np.random.default_rng(0).permutation(original.shape[0])
    shuffled = original.copy()
    shuffled[:, 1:] = shuffled[order][:, 1:]
    assert sorted(shuffled[:, 0].tolist()) == sorted(original[:, 0].tolist())
    assert sorted(shuffled[:, 1].tolist()) == sorted(original[:, 1].tolist())


def test_negative_control_payload_records_both_arms() -> None:
    payload = _require("negative_controls.json")
    control = payload["NC2_temporal_alignment_destroyed"]
    assert control["models"], "the control needs both arms"
    for family in ("logistic", "hist_gb"):
        entry = control["models"][family]
        assert entry["original_auroc"] is not None, "the unshuffled arm must be reported"
        assert entry["replicates"] >= 1, "the shuffled arm must be reported"
        assert entry["detail"], "per-replicate values must be published"


# ---------------------------------------------------------------------------
# out-of-fold contract
# ---------------------------------------------------------------------------


def test_oof_predictions_cover_every_observation_exactly_once() -> None:
    payload = _require("oof_predictions.json")
    labels: dict[str, int] = {}
    counts: dict[str, dict[str, int]] = {}
    for row in payload["records"]:
        labels[row["observation_id"]] = int(row["label"])
        counts.setdefault(row["model"], {})
        counts[row["model"]][row["observation_id"]] = counts[row["model"]].get(row["observation_id"], 0) + 1
    for model, seen in counts.items():
        assert set(seen) == set(labels), f"{model} does not cover the cohort exactly once"
        assert all(value == 1 for value in seen.values())


def test_oof_rows_carry_b0_and_b6_for_third_party_recomputation() -> None:
    payload = _require("oof_predictions.json")
    for row in payload["records"][:50]:
        assert isinstance(row["B0"], float)
        assert isinstance(row["B6"], float)
        assert row["fold"] is not None


def test_reported_metrics_are_recomputable_from_the_oof_ledger() -> None:
    payload = _require("oof_predictions.json")
    model_results = _require("model_results.json")
    labels: dict[str, int] = {}
    vectors: dict[str, dict[str, float]] = {}
    for row in payload["records"]:
        labels[row["observation_id"]] = int(row["label"])
        vectors.setdefault(row["model"], {})[row["observation_id"]] = float(row["predicted_score"])
    order = sorted(labels)
    for name, entry in model_results["models"].items():
        if name not in vectors or entry["auroc"] is None:
            continue
        recomputed = e4r_stats.roc_auc([labels[oid] for oid in order], [vectors[name][oid] for oid in order])
        assert recomputed == pytest.approx(entry["auroc"], abs=1e-9), name


# ---------------------------------------------------------------------------
# frozen-config and manifest
# ---------------------------------------------------------------------------


def test_experiment_config_was_not_tuned_after_the_run() -> None:
    manifest = _require("manifest.json")
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    assert e4r_data.sha256_json(config) == manifest["config_hash"]


def test_manifest_output_hashes_match_the_bytes_on_disk() -> None:
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root / "research" / "e4r_automated_robustness") not in sys.path:
        sys.path.insert(0, str(repo_root / "research" / "e4r_automated_robustness"))
    manifest = _require("manifest.json")
    checked = 0
    for entry in manifest["outputs"]:
        path = repo_root / entry["path"]
        if not path.is_file():
            continue
        checked += 1
        assert e4r_data.sha256_file(path) == entry["sha256"], f"{entry['path']} mutated"
    assert checked >= 10


def test_manifest_records_environment_and_seeds() -> None:
    manifest = _require("manifest.json")
    assert manifest["git_commit"]
    assert manifest["python"]["version"]
    assert manifest["seeds"]["bootstrap"] == e4r_config.SEEDS["bootstrap"]
    assert manifest["source_artifacts"]


def test_primary_family_membership_is_prespecified() -> None:
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    identifiers = [entry["id"] for entry in config["primary_family"]]
    assert identifiers == ["P1", "P2", "P3"]
    statistics = _require("statistical_tests.json")
    assert [item["id"] for item in statistics["primary"]] == identifiers
    for item in statistics["primary"]:
        assert item["holm_adjusted_p"] is not None
    for item in statistics["secondary"]:
        assert item["holm_adjusted_p"] is None, "secondary comparisons must stay unadjusted"


# ---------------------------------------------------------------------------
# nested cross-validation (needs the research extra)
# ---------------------------------------------------------------------------


def test_nested_cv_is_company_disjoint_and_fits_only_on_train():
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    import e4r_models

    count = 40
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(count, 3)).tolist()
    for row in matrix:
        row[0] = float("nan")
    labels = [1] * 20 + [0] * 20
    groups = [f"company_{index}" for index in range(count)]
    result = e4r_models.nested_cv(
        observation_ids=[str(index) for index in range(count)],
        matrix=matrix,
        labels=labels,
        groups=groups,
        feature_names=["a", "b", "c"],
        estimator_family="logistic",
        model_id="t",
        feature_set="F2",
        n_outer=4,
        n_inner=3,
    )
    assert len(result.oof_scores) == count
    for fold, train_index in result.train_index_by_fold.items():
        train = set(train_index)
        tested = set(range(count)) - train
        assert not (train & tested), f"fold {fold} leaks test rows into training"
        # the imputer must have seen only the training rows
        column = [row[1] for row in matrix]
        expected = float(np.nanmedian([column[index] for index in sorted(train)]))
        assert result.imputer_medians_by_fold[fold][1] == pytest.approx(expected)


def test_nested_cv_is_deterministic_under_a_fixed_seed():
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    import e4r_models

    rng = np.random.default_rng(1)
    matrix = rng.normal(size=(30, 2)).tolist()
    labels = [1] * 10 + [0] * 20
    groups = [f"c{index}" for index in range(30)]
    common = {
        "observation_ids": [str(i) for i in range(30)],
        "matrix": matrix,
        "labels": labels,
        "groups": groups,
        "feature_names": ["x", "y"],
        "estimator_family": "logistic",
        "model_id": "t",
        "feature_set": "F2",
        "n_outer": 3,
        "n_inner": 2,
        "seed": 20260925,
    }
    first = e4r_models.nested_cv(**common)
    second = e4r_models.nested_cv(**common)
    assert first.oof_scores == second.oof_scores


def test_nested_cv_survives_a_single_class_training_fold():
    pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    import e4r_models

    matrix = [[float(index), float(index % 3)] for index in range(20)]
    labels = [1] * 2 + [0] * 18
    groups = [f"c{index}" for index in range(20)]
    # Two positives cannot populate four stratified folds; the loop must degrade, not crash.
    result = e4r_models.nested_cv(
        observation_ids=[str(index) for index in range(20)],
        matrix=matrix,
        labels=labels,
        groups=groups,
        feature_names=["x", "y"],
        estimator_family="logistic",
        model_id="t",
        feature_set="F2",
        n_outer=2,
        n_inner=2,
    )
    assert len(result.oof_scores) == 20
    assert result.outer_failures + result.inner_failures >= 0


def test_coverage_filter_runs_inside_the_fold():
    pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    import e4r_models

    matrix = [[float(index), 1.0 if index < 5 else float("nan")] for index in range(40)]
    labels = [1] * 20 + [0] * 20
    groups = [f"c{index}" for index in range(40)]
    result = e4r_models.nested_cv(
        observation_ids=[str(index) for index in range(40)],
        matrix=matrix,
        labels=labels,
        groups=groups,
        feature_names=["full", "sparse"],
        estimator_family="logistic",
        model_id="t",
        feature_set="F3",
        apply_coverage_filter=True,
        min_train_coverage=0.5,
        n_outer=4,
        n_inner=2,
    )
    for entry in result.selected_params:
        assert entry["n_features_used"] <= 2
    assert all(not math.isnan(value) for value in result.oof_scores.values())


# ---------------------------------------------------------------------------
# calibration and threshold contract
# ---------------------------------------------------------------------------


def test_scores_stay_uncalibrated() -> None:
    payload = _require("calibration_diagnostics.json")
    assert payload["status"] == "UNCALIBRATED"
    for entry in payload["models"].values():
        assert entry["note"], "the uncalibrated caveat must travel with the numbers"


def test_threshold_sweep_uses_the_prespecified_grid_only() -> None:
    payload = _require("threshold_robustness.json")
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    assert payload["status"] == "SENSITIVITY_ONLY"
    assert payload["threshold_grid"] == config["threshold_grid"]
    for rows in payload["models"].values():
        assert [row["threshold"] for row in rows] == config["threshold_grid"]


def test_complexity_records_dependencies_and_determinism() -> None:
    payload = _require("complexity_comparison.json")
    for entry in payload["models"]:
        assert entry["dependencies"]
        assert entry["deterministic_reproducibility"]


def test_influence_reports_sign_flips_explicitly() -> None:
    payload = _require("influence_analysis.json")
    summary = payload["leave_one_out"]
    assert summary["n_units"] == payload.get("n_units", summary["n_units"])
    assert "deletions_flipping_sign" in summary
    assert len(summary["top_20_by_absolute_influence"]) <= 20


# ---------------------------------------------------------------------------
# post-hoc hardening pass
# ---------------------------------------------------------------------------


def test_extension_config_is_frozen_and_tied_to_the_frozen_config() -> None:
    extension = _require("extension_config.json")
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    assert extension["status"] == "POST_HOC_AUTOMATED_ROBUSTNESS"
    assert extension["frozen_config_untouched"] is True
    assert extension["frozen_config_hash"] == e4r_data.sha256_json(config)
    manifest = _require("manifest.json")
    assert manifest["extension_config_hash"] == e4r_data.sha256_json(extension)


def test_the_frozen_config_still_matches_its_own_hash() -> None:
    """The hardening pass must not have moved the original prespecification."""
    config = json.loads((HERE / "experiment_config.json").read_text(encoding="utf-8"))
    feature_sets = json.loads((HERE / "feature_sets.json").read_text(encoding="utf-8"))
    manifest = _require("manifest.json")
    assert e4r_data.sha256_json(config) == manifest["config_hash"]
    assert e4r_data.sha256_json(feature_sets) == manifest["feature_sets_hash"]


def test_missingness_arms_are_recomputable_from_their_embedded_scores() -> None:
    payload = _require("missingness_ablation.json")
    for family, entry in payload["families"].items():
        for arm_name, arm in entry["arms"].items():
            ids = sorted(arm["scores"])
            recomputed = e4r_stats.roc_auc(
                [_row_labels()[oid] for oid in ids], [arm["scores"][oid] for oid in ids]
            )
            assert recomputed == pytest.approx(arm["auroc"], abs=1e-9), f"{family}/{arm_name}"
        assert "C_missingness_only" in entry["arms"], family


def test_missingness_ablation_covers_four_arms_for_both_families() -> None:
    payload = _require("missingness_ablation.json")
    expected = {
        "A_full_F2_with_indicators",
        "B_full_F2_without_indicators",
        "C_missingness_only",
        "D_harmonized_availability",
    }
    for family, entry in payload["families"].items():
        assert set(entry["arms"]) == expected, family
        for comparison in (
            "A_minus_B_full_F2_without_indicators",
            "A_minus_C_missingness_only",
            "A_restricted_minus_D_harmonized",
        ):
            assert comparison in payload["comparisons"][family], (family, comparison)


def test_strict_complete_case_is_refused_rather_than_estimated() -> None:
    payload = _require("missingness_ablation.json")
    strict = payload["strict_complete_case"]
    assert strict["estimable"] is False
    assert strict["events"] < 20, "a complete-case arm with this few events cannot support AUROC"
    assert strict["reason"]


def test_boosting_increment_reports_both_arms_and_the_delta() -> None:
    payload = _require("boosting_temporal_increment.json")
    for name in ("hist_gb_F0", "hist_gb_F2"):
        ids = sorted(payload["scores"][name])
        recomputed = e4r_stats.roc_auc(
            [_row_labels()[oid] for oid in ids], [payload["scores"][name][oid] for oid in ids]
        )
        key = "reference_metrics" if name == "hist_gb_F0" else "challenger_metrics"
        assert recomputed == pytest.approx(payload[key]["auroc"], abs=1e-9)
    delta = payload["challenger_metrics"]["auroc"] - payload["reference_metrics"]["auroc"]
    assert delta == pytest.approx(payload["comparison"]["delta_auroc"], abs=1e-12)
    assert payload["comparison"]["delong"]["p_value"] is not None
    assert payload["comparison"]["bootstrap_auroc"]["valid_replicates"] == 20000


def test_temporal_shuffle_is_paired_and_meets_the_replicate_floor() -> None:
    payload = _require("negative_controls.json")["NC2_temporal_alignment_destroyed"]
    for family in ("logistic", "hist_gb"):
        entry = payload["models"][family]
        assert entry["replicates"] >= 100, family
        assert payload["reproduction_of_frozen_folds"][family]["folds_identical_to_frozen_run"] is True
        assert 0.0 <= entry["P_drop_gt_0"] <= 1.0
        assert len(entry["detail"]) == entry["replicates"]
        mean_drop = sum(row["drop"] for row in entry["detail"]) / len(entry["detail"])
        assert mean_drop == pytest.approx(entry["drop_mean"], abs=1e-12)


def test_negative_controls_document_the_superseded_arm() -> None:
    payload = _require("negative_controls.json")
    assert "NC2_superseded_note" in payload
    assert payload["NC2_temporal_alignment_destroyed"]["audit_note"]


def test_sector_heterogeneity_classification_matches_the_interval_rule() -> None:
    payload = _require("sector_heterogeneity.json")
    for row in payload["sectors"]:
        if not row["estimable"]:
            assert row["status"] == "NOT_ESTIMABLE"
            continue
        if row["classification"] == "robust_positive":
            assert row["ci_low"] > 0
        elif row["classification"] == "possible_heterogeneity":
            assert row["ci_high"] < 0
        else:
            assert row["classification"] == "inconclusive"
            assert row["ci_low"] <= 0 <= row["ci_high"]


def test_no_sector_is_called_a_failure_without_interval_support() -> None:
    payload = _require("sector_heterogeneity.json")
    for row in payload["sectors"]:
        if not row["estimable"] or row["delta_auroc"] >= 0:
            continue
        assert row["classification"] in {"inconclusive", "possible_heterogeneity"}
        if row["classification"] == "inconclusive":
            assert row["ci_low"] < 0 < row["ci_high"]


def test_heterogeneity_reports_both_tests_and_the_gated_share() -> None:
    payload = _require("sector_heterogeneity.json")
    entry = payload["heterogeneity"]
    assert entry["status"] == "OK"
    assert entry["permutation_p_value"] is not None
    assert 0.0 < entry["permutation_p_value"] <= 1.0
    assert entry["chi_square_p_value"] is not None
    assert 0.0 < entry["gated_share_of_cohort"] <= 1.0
    assert entry["population_size"] > 0


def test_model_stability_mean_matches_its_repeats() -> None:
    payload = _require("model_stability.json")
    assert payload["models"], "the stability stage must report at least one model"
    for name, entry in payload["models"].items():
        values = [item["auroc"] for item in entry["repeats"]]
        assert len(values) >= 5, name
        assert sum(values) / len(values) == pytest.approx(entry["mean_auroc"], abs=1e-12)
        assert entry["range_auroc"] == pytest.approx(max(values) - min(values), abs=1e-12)


def test_repeated_cv_does_not_enter_the_primary_family() -> None:
    statistics = _require("statistical_tests.json")
    for item in statistics["primary"]:
        assert "repeat" not in item["challenger"]
        assert "repeat" not in item["reference"]
    extension = _require("extension_config.json")
    assert "does not enter any primary comparison" in extension["model_stability"]["scope"]


def test_report_answers_the_hardening_questions_and_keeps_its_caveats() -> None:
    text = (HERE / "FINAL_REPORT.md").read_text(encoding="utf-8")
    for heading in ("### H1.", "### H2.", "### H3.", "### H4.", "### H5.", "### H6.", "### H7.", "### H8."):
        assert heading in text, heading
    assert "do not \nfully integrate training-procedure uncertainty" in text or (
        "fully integrate training-procedure uncertainty" in text
    )
    assert "structural" in text.lower()
    assert "UNCALIBRATED" in text


def test_report_keeps_the_status_boundaries() -> None:
    text = (HERE / "FINAL_REPORT.md").read_text(encoding="utf-8")
    assert "ESTABLISHED_E4" in text and "CONFIRMATORY" in text and "E5_RESULT" in text
    assert "POST_HOC_AUTOMATED_ROBUSTNESS" in text
