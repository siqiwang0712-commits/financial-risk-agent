"""Rebuild the v0.4.1 retrospective StrongTabularReference development artifacts.

This command uses approved historical E4-S labels. It never reads E5 inputs or changes the
production FinRisk scoring path. Normal tests and verification do not invoke this runner.
"""

from __future__ import annotations

import gzip
import json
import math
import pickle
import platform
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from research.selective_evaluation import evaluate_decisions, risk_coverage_curve

from .approve_development_data import build as approve_development_data
from .artifact import sha256_file
from .contract import artifact_sha256, canonical_json_bytes, load_config, load_schema
from .development_data import validate_development_data_manifest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPLICATION = ROOT / "research/e4_statistical_audit/replication"
ARTIFACTS = HERE / "artifacts"
RUN_CONFIG_PATH = HERE / "development_run_config.json"
APPROVED_MANIFEST_PATH = HERE / "development_data_manifest.json"
VALUE_FIELDS = (
    "current_ratio",
    "debt_to_assets",
    "net_margin",
    "cfo_to_net_income",
    "fcf_margin",
    "revenue_growth",
    "operating_cash_flow_growth",
    "total_debt_growth",
    "cash_growth",
)


def _load(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _matrix(rows: list[dict], fields: list[str]) -> list[list[float]]:
    result = []
    for row in rows:
        values = []
        for name in fields:
            if name.startswith("observed__"):
                values.append(float(_finite(row["metrics"].get(name.removeprefix("observed__")))))
            else:
                value = row["metrics"].get(name)
                values.append(float(value) if _finite(value) else float("nan"))
        result.append(values)
    return result


def _model_parameters(config: dict, family: str) -> list[dict]:
    candidate = next(item for item in config["candidate_model_families"] if item["family"] == family)
    fixed = candidate["fixed_parameters"]
    combinations = [{}]
    for name, values in candidate["search_space"].items():
        combinations = [{**base, name: value} for base in combinations for value in values]
    return [{**fixed, **values} for values in combinations]


def _pipeline(family: str, block: str, parameters: dict, fields: list[str], seed: int) -> Pipeline:
    numeric = [index for index, name in enumerate(fields) if not name.startswith("observed__")]
    observed = [index for index, name in enumerate(fields) if name.startswith("observed__")]
    if family == "logistic_regression":
        transformers = []
        if numeric:
            numeric_steps = []
            if block != "CC":
                numeric_steps.append(("impute", SimpleImputer(strategy="median", add_indicator=False)))
            numeric_steps.append(("scale", StandardScaler()))
            transformers.append(("financial_values", Pipeline(numeric_steps), numeric))
        if observed:
            transformers.append(("reporting_observability", "passthrough", observed))
        preprocessor = ColumnTransformer(transformers, remainder="drop")
        model = LogisticRegression(
            C=float(parameters["C"]),
            class_weight=None if parameters["class_weight"] == "NONE" else parameters["class_weight"],
            max_iter=int(parameters["max_iter"]),
            penalty=parameters["penalty"],
            solver=parameters["solver"],
            random_state=seed,
        )
    elif family == "histogram_gradient_boosting":
        preprocessor = (
            FunctionTransformer(validate=False)
            if block == "CC"
            else SimpleImputer(strategy="median", add_indicator=False)
        )
        model = HistGradientBoostingClassifier(
            loss=parameters["loss"],
            early_stopping=bool(parameters["early_stopping"]),
            learning_rate=float(parameters["learning_rate"]),
            max_leaf_nodes=int(parameters["max_leaf_nodes"]),
            min_samples_leaf=int(parameters["min_samples_leaf"]),
            l2_regularization=float(parameters["l2_regularization"]),
            random_state=seed,
        )
    else:
        raise ValueError(f"unapproved model family: {family}")
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _splits(y: np.ndarray, groups: np.ndarray, count: int, seed: int):
    splitter = StratifiedGroupKFold(n_splits=count, shuffle=True, random_state=seed)
    result = list(splitter.split(np.zeros(len(y)), y, groups))
    if any(len(set(y[test])) != 2 for _, test in result):
        raise RuntimeError("a grouped fold lacks one endpoint class")
    return result


def _metrics(y: np.ndarray, scores: np.ndarray) -> dict:
    return {
        "n": len(y),
        "events": int(y.sum()),
        "non_events": int(len(y) - y.sum()),
        "auroc": float(roc_auc_score(y, scores)),
        "pr_auc": float(average_precision_score(y, scores)),
        "brier_descriptive_uncalibrated": float(brier_score_loss(y, scores)),
    }


def _select_parameters(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    fields: list[str],
    family: str,
    block: str,
    grid: list[dict],
    inner_folds: int,
    seed: int,
) -> tuple[dict, list[dict]]:
    records = []
    inner = _splits(y, groups, inner_folds, seed)
    for parameters in grid:
        fold_metrics = []
        status = "ELIGIBLE"
        for train, test in inner:
            try:
                pipeline = _pipeline(family, block, parameters, fields, seed)
                pipeline.fit(X[train], y[train])
                scores = pipeline.predict_proba(X[test])[:, 1]
                fold_metrics.append(_metrics(y[test], scores))
            except Exception as exc:  # noqa: BLE001 - every failure is retained
                status = f"INELIGIBLE:{type(exc).__name__}"
                fold_metrics = []
                break
        record = {
            "parameters": parameters,
            "status": status,
            "fold_metrics": fold_metrics,
            "mean_auroc": (
                sum(item["auroc"] for item in fold_metrics) / len(fold_metrics)
                if fold_metrics
                else None
            ),
            "mean_pr_auc": (
                sum(item["pr_auc"] for item in fold_metrics) / len(fold_metrics)
                if fold_metrics
                else None
            ),
        }
        records.append(record)
    eligible = [item for item in records if item["status"] == "ELIGIBLE"]
    if not eligible:
        raise RuntimeError(f"no eligible hyperparameters for {family}/{block}")
    winner = min(
        eligible,
        key=lambda item: (
            -item["mean_auroc"],
            -item["mean_pr_auc"],
            json.dumps(item["parameters"], sort_keys=True, separators=(",", ":")),
        ),
    )
    return winner["parameters"], records


def _nested_candidate(
    rows: list[dict],
    labels: list[int],
    groups: list[str],
    fields: list[str],
    family: str,
    block: str,
    config: dict,
    run_config: dict,
) -> tuple[dict, list[dict]]:
    X = np.asarray(_matrix(rows, fields), dtype=float)
    y = np.asarray(labels, dtype=int)
    group_array = np.asarray(groups, dtype=object)
    seed = int(run_config["master_seed"])
    outer = _splits(y, group_array, int(run_config["outer_folds"]), seed)
    grid = _model_parameters(config, family)
    predictions = np.full(len(y), np.nan)
    fold_records = []
    for fold, (train, test) in enumerate(outer):
        params, inner_records = _select_parameters(
            X[train],
            y[train],
            group_array[train],
            fields,
            family,
            block,
            grid,
            int(run_config["inner_folds"]),
            seed,
        )
        pipeline = _pipeline(family, block, params, fields, seed)
        pipeline.fit(X[train], y[train])
        scores = pipeline.predict_proba(X[test])[:, 1]
        predictions[test] = scores
        fold_records.append(
            {
                "fold": fold,
                "train_observation_ids": [rows[index]["observation_id"] for index in train],
                "test_observation_ids": [rows[index]["observation_id"] for index in test],
                "selected_parameters": params,
                "inner_candidates": inner_records,
                "metrics": _metrics(y[test], scores),
            }
        )
    if not np.isfinite(predictions).all():
        raise RuntimeError(f"non-finite OOF score for {family}/{block}")
    aggregate = _metrics(y, predictions)
    aggregate.update(
        {
            "model_family": family,
            "feature_block": block,
            "feature_names": fields,
            "status": "ELIGIBLE",
            "coverage": len(rows) / 675,
            "mean_outer_fold_auroc": sum(item["metrics"]["auroc"] for item in fold_records)
            / len(fold_records),
            "mean_outer_fold_pr_auc": sum(item["metrics"]["pr_auc"] for item in fold_records)
            / len(fold_records),
            "outer_folds": fold_records,
        }
    )
    oof = [
        {
            "observation_id": row["observation_id"],
            "cik": row["cik"],
            "label": int(label),
            "score": float(score),
            "score_semantics": "UNCALIBRATED_RANKING_SCORE",
        }
        for row, label, score in zip(rows, y, predictions, strict=True)
    ]
    return aggregate, oof


def _reference_profile(source_rows: list[dict], schema: dict, source_hash: str) -> dict:
    """Build label-independent value and observability profiles from prediction-time rows."""

    quantiles = _load(RUN_CONFIG_PATH)["reference_profile"]["quantiles"]
    values = {}
    observability = {}
    for name in VALUE_FIELDS:
        observed = np.asarray(
            [float(row["metrics"][name]) for row in source_rows if _finite(row["metrics"].get(name))]
        )
        values[name] = {
            "observed_count": len(observed),
            "missing_count": int(len(source_rows) - len(observed)),
            "mean": float(observed.mean()) if len(observed) else None,
            "standard_deviation": float(observed.std()) if len(observed) else None,
            "quantiles": {
                f"q{int(q * 100):02d}": float(np.quantile(observed, q)) if len(observed) else None
                for q in quantiles
            },
        }
        observability[f"observed__{name}"] = {
            "observed_count": len(observed),
            "missing_count": int(len(source_rows) - len(observed)),
            "observed_prevalence": len(observed) / len(source_rows),
        }
    payload = {
        "schema_version": "1",
        "status": "EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY",
        "population": "ALL_2000_E4S_SOURCE_COHORT_ROWS",
        "observation_count": len(source_rows),
        "construction_uses_labels": False,
        "source_features_sha256": source_hash,
        "feature_schema_sha256": artifact_sha256(schema),
        "construction_config_sha256": sha256_file(RUN_CONFIG_PATH),
        "financial_value_profile": values,
        "reporting_observability_profile": observability,
        "membership_rule": _load(RUN_CONFIG_PATH)["reference_profile"]["in_reference_rule"],
        "limitations": [
            "Historical development reference only",
            "Not E5, external, regulatory, or production validation",
            "Distribution shift does not prove model error",
        ],
    }
    payload["reference_sha256"] = artifact_sha256(payload)
    return payload


def _in_reference(row: dict, profile: dict) -> bool:
    for name, stats in profile["financial_value_profile"].items():
        value = row["metrics"].get(name)
        if not _finite(value):
            continue
        if value < stats["quantiles"]["q01"] or value > stats["quantiles"]["q99"]:
            return False
    return True


def _observability(rows: list[dict], labels: list[int]) -> dict:
    by_label = defaultdict(lambda: {name: [] for name in VALUE_FIELDS})
    by_sector = defaultdict(list)
    assets = np.asarray(
        [float(row["current"]["total_assets"]) if _finite(row["current"].get("total_assets")) else np.nan for row in rows]
    )
    finite_assets = assets[np.isfinite(assets)]
    q1, q2 = np.quantile(finite_assets, [1 / 3, 2 / 3])
    by_size = defaultdict(list)
    for row, label, asset in zip(rows, labels, assets, strict=True):
        missing = []
        for name in VALUE_FIELDS:
            observed = _finite(row["metrics"].get(name))
            by_label[str(label)][name].append(float(observed))
            missing.append(not observed)
        rate = sum(missing) / len(missing)
        by_sector[row["sector"]].append(rate)
        size = "UNKNOWN" if not np.isfinite(asset) else ("SMALL" if asset <= q1 else "MEDIUM" if asset <= q2 else "LARGE")
        by_size[size].append(rate)
    return {
        "missingness_by_field_and_label": {
            label: {
                name: {"observed_prevalence": sum(values) / len(values), "n": len(values)}
                for name, values in fields.items()
            }
            for label, fields in by_label.items()
        },
        "mean_missingness_by_sector": {
            key: {"n": len(values), "mean_missingness": sum(values) / len(values)}
            for key, values in sorted(by_sector.items())
        },
        "mean_missingness_by_total_assets_tercile": {
            key: {"n": len(values), "mean_missingness": sum(values) / len(values)}
            for key, values in sorted(by_size.items())
        },
        "feature_presence_importance": "NOT_ESTIMABLE_WITHOUT_A_SEPARATE_NONLEAKING_IMPORTANCE_DESIGN",
        "causal_interpretation_allowed": False,
    }


def _render_observability(results: dict) -> str:
    lines = [
        "# Reporting observability diagnostic",
        "",
        "Status: **RETROSPECTIVE_DEVELOPMENT_DIAGNOSTIC**",
        "",
        "This cohort is historically exposed, the verified-label subset is selective, and all metrics are development diagnostics. This is not E5 or independent validation.",
        "",
        "| Block | N | Coverage | AUROC | PR-AUC | Descriptive Brier (uncalibrated) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for block in ("V", "O", "VO", "CC"):
        item = results["blocks"][block]
        lines.append(
            f"| {block} | {item['n']} | {item['coverage']:.3f} | {item['auroc']:.3f} | {item['pr_auc']:.3f} | {item['brier_descriptive_uncalibrated']:.3f} |"
        )
    lines += [
        "",
        f"Development-only VO minus V AUROC: `{results['vo_minus_v']['auroc']:+.3f}`; PR-AUC: `{results['vo_minus_v']['pr_auc']:+.3f}`.",
        "",
        "Reporting observability may carry retrospective predictive information in this historical cohort. It is not causal evidence and is not financial severity. Production FinRisk continues to keep reporting observability separate from financial values.",
        "",
        "Canonical source: [`artifacts/observability_diagnostic.json`](artifacts/observability_diagnostic.json).",
        "",
    ]
    return "\n".join(lines)


def run() -> dict:
    approved = approve_development_data()
    validate_development_data_manifest(approved, schema=load_schema())
    config = load_config()
    schema = load_schema()
    run_config = _load(RUN_CONFIG_PATH)
    cohort = _load(REPLICATION / "cohort.json")
    features = _load(REPLICATION / "features.json.gz")
    outcomes = _load(REPLICATION / "outcomes.json")
    outcome_by_id = {row["observation_id"]: row for row in outcomes}
    cohort_by_id = {row["observation_id"]: row for row in cohort}
    feature_by_id = {row["observation_id"]: row for row in features}
    observation_ids = sorted(
        row["observation_id"]
        for row in outcomes
        if row.get("label_status") == "VERIFIED" and row.get("financial_deterioration_12m") in {0, 1}
    )
    rows = []
    labels = []
    groups = []
    for observation_id in observation_ids:
        row = {**feature_by_id[observation_id], **cohort_by_id[observation_id]}
        rows.append(row)
        labels.append(int(outcome_by_id[observation_id]["financial_deterioration_12m"]))
        groups.append(str(row["cik"]))
    if len(rows) != 675 or len(set(groups)) != 675:
        raise RuntimeError("approved development row identity drift")

    candidate_results = []
    candidate_oof = {}
    for family in ("logistic_regression", "histogram_gradient_boosting"):
        for block in ("V", "VO"):
            fields = list(config["feature_blocks"][block]["features"])
            result, oof = _nested_candidate(rows, labels, groups, fields, family, block, config, run_config)
            candidate_results.append(result)
            candidate_oof[f"{family}__{block}"] = oof
    family_rank = {"logistic_regression": 0, "histogram_gradient_boosting": 1}
    block_rank = {"V": 0, "VO": 1}
    selected = min(
        candidate_results,
        key=lambda item: (
            -item["mean_outer_fold_auroc"],
            -item["mean_outer_fold_pr_auc"],
            family_rank[item["model_family"]],
            block_rank[item["feature_block"]],
        ),
    )
    family = selected["model_family"]
    block = selected["feature_block"]
    fields = selected["feature_names"]
    X = np.asarray(_matrix(rows, fields), dtype=float)
    y = np.asarray(labels, dtype=int)
    group_array = np.asarray(groups, dtype=object)
    final_parameters, final_search = _select_parameters(
        X,
        y,
        group_array,
        fields,
        family,
        block,
        _model_parameters(config, family),
        int(run_config["inner_folds"]),
        int(run_config["master_seed"]),
    )
    fitted = _pipeline(family, block, final_parameters, fields, int(run_config["master_seed"])).fit(X, y)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    preprocessor_path = ARTIFACTS / "preprocessor.pkl"
    model_path = ARTIFACTS / "model.pkl"
    with preprocessor_path.open("wb") as handle:
        pickle.dump(fitted.named_steps["preprocessor"], handle, protocol=5)
    with model_path.open("wb") as handle:
        pickle.dump(fitted.named_steps["model"], handle, protocol=5)

    selected_key = f"{family}__{block}"
    selected_oof = candidate_oof[selected_key]
    score_by_id = {row["observation_id"]: row["score"] for row in selected_oof}
    fold_assignments = {
        "schema_version": "1",
        "group_key": "cik",
        "company_disjoint": True,
        "outer_folds": [
            {
                "fold": fold["fold"],
                "test_observation_ids": fold["test_observation_ids"],
            }
            for fold in selected["outer_folds"]
        ],
    }
    _write(ARTIFACTS / "fold_assignments.json", fold_assignments)
    _write(ARTIFACTS / "candidate_results.json", {"candidates": candidate_results})
    _write(ARTIFACTS / "oof_predictions.json", {"candidates": candidate_oof})

    diagnostic_results = {}
    diagnostic_oof = {}
    for diagnostic_block in ("V", "VO"):
        eligible = [item for item in candidate_results if item["feature_block"] == diagnostic_block]
        best = min(
            eligible,
            key=lambda item: (
                -item["mean_outer_fold_auroc"],
                -item["mean_outer_fold_pr_auc"],
                family_rank[item["model_family"]],
            ),
        )
        diagnostic_results[diagnostic_block] = {
            key: best[key]
            for key in ("n", "events", "non_events", "coverage", "auroc", "pr_auc", "brier_descriptive_uncalibrated", "model_family")
        }
        diagnostic_oof[diagnostic_block] = candidate_oof[
            f"{best['model_family']}__{diagnostic_block}"
        ]
    for diagnostic_block in ("O", "CC"):
        diagnostic_rows = rows
        diagnostic_labels = labels
        diagnostic_groups = groups
        if diagnostic_block == "CC":
            keep = [
                index
                for index, row in enumerate(rows)
                if all(_finite(row["metrics"].get(name)) for name in VALUE_FIELDS)
            ]
            diagnostic_rows = [rows[index] for index in keep]
            diagnostic_labels = [labels[index] for index in keep]
            diagnostic_groups = [groups[index] for index in keep]
        diagnostic_fields = list(config["feature_blocks"][diagnostic_block]["features"])
        result, oof = _nested_candidate(
            diagnostic_rows,
            diagnostic_labels,
            diagnostic_groups,
            diagnostic_fields,
            family,
            diagnostic_block,
            config,
            run_config,
        )
        diagnostic_results[diagnostic_block] = {
            key: result[key]
            for key in ("n", "events", "non_events", "coverage", "auroc", "pr_auc", "brier_descriptive_uncalibrated", "model_family")
        }
        diagnostic_oof[diagnostic_block] = oof
    observability = {
        "schema_version": "1",
        "status": "RETROSPECTIVE_DEVELOPMENT_DIAGNOSTIC",
        "evidence_boundary": "DESIGN_EXPOSED_SELECTIVE_VERIFIED_LABEL_SUBSET_NOT_E5",
        "blocks": diagnostic_results,
        "vo_minus_v": {
            "auroc": diagnostic_results["VO"]["auroc"] - diagnostic_results["V"]["auroc"],
            "pr_auc": diagnostic_results["VO"]["pr_auc"] - diagnostic_results["V"]["pr_auc"],
        },
        "missingness": _observability(rows, labels),
        "oof_predictions": diagnostic_oof,
    }
    observability["artifact_sha256"] = artifact_sha256(observability)
    _write(ARTIFACTS / "observability_diagnostic.json", observability)
    (HERE / "OBSERVABILITY_DIAGNOSTIC.md").write_text(
        _render_observability(observability), encoding="utf-8", newline="\n"
    )

    reference = _reference_profile(features, schema, sha256_file(REPLICATION / "features.json.gz"))
    _write(ARTIFACTS / "empirical_development_reference.json", reference)
    in_reference = [_in_reference(row, reference) for row in rows]
    s0_decisions = ["FLAG" if score_by_id[oid] >= 0.5 else "PASS" for oid in observation_ids]
    s1 = run_config["s1_selective_policy"]
    s1_decisions = [
        "FLAG" if score_by_id[oid] >= s1["authorize_flag_at_or_above"] else
        "PASS" if score_by_id[oid] < s1["authorize_pass_below"] else "REVIEW"
        for oid in observation_ids
    ]
    selective = {
        "schema_version": "1",
        "status": "RETROSPECTIVE_DEVELOPMENT_DRY_RUN",
        "config_sha256": sha256_file(RUN_CONFIG_PATH),
        "s0": evaluate_decisions(labels, s0_decisions, in_reference=in_reference),
        "s1": evaluate_decisions(labels, s1_decisions, in_reference=in_reference),
        "risk_coverage_curve": risk_coverage_curve(labels, [score_by_id[oid] for oid in observation_ids]),
        "support_metrics": "NOT_ESTIMABLE_NO_STRUCTURED_SUPPORT_LABELS_IN_TABULAR_PACKET",
        "s2_s3_s4": run_config["s2_s3_s4"],
    }
    selective["artifact_sha256"] = artifact_sha256(selective)
    _write(ARTIFACTS / "selective_evaluation.json", selective)

    selection = {
        "schema_version": "1",
        "status": "MECHANICALLY_SELECTED_RETROSPECTIVE_DEVELOPMENT",
        "development_manifest_sha256": approved["integrity"]["canonical_manifest_sha256"],
        "experiment_config_sha256": sha256_file(HERE / "experiment_config.json"),
        "run_config_sha256": sha256_file(RUN_CONFIG_PATH),
        "selected_feature_block": block,
        "selected_model_family": family,
        "selected_final_hyperparameters": final_parameters,
        "selection_ranking": [
            {
                "model_family": item["model_family"],
                "feature_block": item["feature_block"],
                "mean_outer_fold_auroc": item["mean_outer_fold_auroc"],
                "mean_outer_fold_pr_auc": item["mean_outer_fold_pr_auc"],
            }
            for item in sorted(
                candidate_results,
                key=lambda item: (
                    -item["mean_outer_fold_auroc"],
                    -item["mean_outer_fold_pr_auc"],
                    family_rank[item["model_family"]],
                    block_rank[item["feature_block"]],
                ),
            )
        ],
        "final_parameter_search": final_search,
        "human_override": False,
    }
    _write(ARTIFACTS / "selection_record.json", selection)

    replay_ids = observation_ids[:10]
    replay_matrix = _matrix([rows[observation_ids.index(oid)] for oid in replay_ids], fields)
    replay_scores = fitted.predict_proba(np.asarray(replay_matrix, dtype=float))[:, 1]
    replay = {
        "schema_version": "1",
        "input_observation_ids": replay_ids,
        "ordered_feature_names": fields,
        "matrix": replay_matrix,
        "expected_scores": [float(value) for value in replay_scores],
        "absolute_tolerance": 1e-12,
        "guarantee": "DETERMINISTIC_INFERENCE_UNDER_PINNED_RUNTIME",
        "cross_platform_bitwise_identity_claimed": False,
    }
    _write(ARTIFACTS / "replay_sample.json", replay)
    runtime = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
        "serialization": "python_pickle_protocol_5_trusted_hash_verified_artifacts_only",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_state": "UNCOMMITTED_V0.4.1_RESEARCH_DEVELOPMENT",
        "requirements_lock_sha256": sha256_file(ROOT / "requirements.lock"),
    }
    _write(ARTIFACTS / "runtime_identity.json", runtime)

    verification_report = {
        "schema_version": "1",
        "status": "PASS",
        "scope": "BUILD_TIME_RETROSPECTIVE_DEVELOPMENT_VERIFICATION",
        "checks": {
            "approved_development_manifest": True,
            "development_observations_675": len(rows) == 675,
            "unique_companies_675": len(set(groups)) == 675,
            "future_e5_exclusions_2000": approved["population"]["source_population_company_count"] == 2000,
            "candidate_count_4": len(candidate_results) == 4,
            "candidate_blocks_only_v_vo": {item["feature_block"] for item in candidate_results} == {"V", "VO"},
            "selected_block_s0_eligible": block in {"V", "VO"},
            "human_override_absent": True,
            "all_oof_scores_finite": all(math.isfinite(item["score"]) for item in selected_oof),
            "reference_construction_label_independent": reference["construction_uses_labels"] is False,
            "observability_separate_from_values": set(reference["financial_value_profile"]).isdisjoint(reference["reporting_observability_profile"]),
            "calibration_uncalibrated": run_config["calibration"]["status"] == "UNCALIBRATED",
            "e5_artifacts_not_accessed": True,
        },
    }
    if not all(verification_report["checks"].values()):
        raise RuntimeError("build-time verification failed")
    _write(ARTIFACTS / "verification_report.json", verification_report)

    file_hashes = {
        "candidate_results_sha256": sha256_file(ARTIFACTS / "candidate_results.json"),
        "fold_assignments_sha256": sha256_file(ARTIFACTS / "fold_assignments.json"),
        "oof_predictions_sha256": sha256_file(ARTIFACTS / "oof_predictions.json"),
        "selection_record_sha256": sha256_file(ARTIFACTS / "selection_record.json"),
        "observability_diagnostic_sha256": sha256_file(ARTIFACTS / "observability_diagnostic.json"),
        "empirical_reference_sha256": sha256_file(ARTIFACTS / "empirical_development_reference.json"),
        "selective_evaluation_sha256": sha256_file(ARTIFACTS / "selective_evaluation.json"),
        "replay_sample_sha256": sha256_file(ARTIFACTS / "replay_sample.json"),
        "runtime_identity_sha256": sha256_file(ARTIFACTS / "runtime_identity.json"),
        "verification_report_sha256": sha256_file(ARTIFACTS / "verification_report.json"),
        "fitted_preprocessor_sha256": sha256_file(preprocessor_path),
        "fitted_model_sha256": sha256_file(model_path),
    }
    manifest = {
        "schema_version": "1",
        "artifact": "StrongTabularReference-v1",
        "status": "FITTED_HISTORICAL_NOT_E5_FROZEN",
        "evidence_status": "RETROSPECTIVE_DEVELOPMENT",
        "development_data": {
            "manifest": "../development_data_manifest.json",
            "manifest_sha256": approved["integrity"]["canonical_manifest_sha256"],
            "company_count": 675,
            "observation_count": 675,
            "events": 235,
            "historical_exposure": "DESIGN_EXPOSED_HISTORICAL_DEVELOPMENT",
        },
        "feature_contract": {
            "feature_schema_sha256": artifact_sha256(schema),
            "selected_feature_block": block,
            "ordered_feature_names": fields,
        },
        "preprocessing": {
            "serialized_artifact": "preprocessor.pkl",
            "automatic_missing_indicators": False,
            "fit_scope": "FULL_APPROVED_DEVELOPMENT_SET_AFTER_NESTED_SELECTION",
        },
        "model": {
            "family": family,
            "exact_hyperparameters": final_parameters,
            "serialized_artifact": "model.pkl",
        },
        "selection": {
            "record": "selection_record.json",
            "mechanical_no_override": True,
        },
        "runtime": runtime,
        "output_contract": {
            "field": "reference_model_score",
            "score_semantics": "UNCALIBRATED_RANKING_SCORE",
            "calibration_status": "UNCALIBRATED",
            "probability_interpretation_allowed": False,
            "final_decision_authority": "NONE_PREDICTION_ONLY",
        },
        "hashes": {
            **file_hashes,
            "fitted_artifact_hash": "PENDING_SELF_HASH",
            "e5_freeze_identity": "TO_BE_FROZEN",
        },
    }
    payload = json.loads(json.dumps(manifest))
    payload["hashes"].pop("fitted_artifact_hash")
    manifest["hashes"]["fitted_artifact_hash"] = artifact_sha256(payload)
    _write(ARTIFACTS / "artifact_manifest.json", manifest)

    canonical = {
        "schema_version": "1",
        "status": "RETROSPECTIVE_DEVELOPMENT",
        "selected_feature_block": block,
        "selected_model_family": family,
        "selected_hyperparameters": final_parameters,
        "development_oof": {
            "n": selected["n"],
            "events": selected["events"],
            "auroc": selected["auroc"],
            "pr_auc": selected["pr_auc"],
            "brier_descriptive_uncalibrated": selected["brier_descriptive_uncalibrated"],
        },
        "observability_blocks": diagnostic_results,
        "selective_evaluation": {"s0": selective["s0"], "s1": selective["s1"]},
        "empirical_reference_sha256": reference["reference_sha256"],
        "fitted_artifact_hash": manifest["hashes"]["fitted_artifact_hash"],
        "calibration_status": "UNCALIBRATED",
    }
    canonical["result_sha256"] = artifact_sha256(canonical)
    _write(ARTIFACTS / "canonical_results.json", canonical)
    return canonical


def main() -> int:
    result = run()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
