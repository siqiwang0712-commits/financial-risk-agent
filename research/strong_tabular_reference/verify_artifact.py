"""Independently verify the fitted historical reference without retraining."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import numpy as np
import sklearn
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from research.selective_evaluation import evaluate_decisions, risk_coverage_curve

from .artifact import ARTIFACTS, MANIFEST, predict_scores, sha256_file
from .contract import (
    APPROVED_MODEL_FAMILIES,
    artifact_sha256,
    block_features,
    load_config,
    load_schema,
    validate_candidate_parameters,
)
from .development_data import (
    canonical_manifest_sha256,
    validate_development_data_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPLICATION = ROOT / "research/e4_statistical_audit/replication"
RUN_CONFIG = HERE / "development_run_config.json"


class VerificationError(RuntimeError):
    """Raised when any checked-in artifact or semantic invariant drifts."""


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{path.name} is unreadable") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path.name} must contain an object")
    return value


def _read_gzip(path: Path) -> list[dict]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{path.name} is unreadable") from exc
    if not isinstance(value, list):
        raise VerificationError(f"{path.name} must contain an array")
    return value


def _close(left: object, right: object, *, tolerance: float = 1e-14) -> bool:
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(
        float(left), float(right), rel_tol=0.0, abs_tol=tolerance
    )


def _metrics(rows: list[dict]) -> dict:
    labels = np.asarray([row["label"] for row in rows], dtype=int)
    scores = np.asarray([row["score"] for row in rows], dtype=float)
    if not len(rows) or not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
        raise VerificationError("OOF scores must be finite values in [0, 1]")
    if set(labels.tolist()) != {0, 1}:
        raise VerificationError("OOF labels must contain both binary endpoint classes")
    return {
        "n": len(rows),
        "events": int(labels.sum()),
        "non_events": int(len(labels) - labels.sum()),
        "auroc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
        "brier_descriptive_uncalibrated": float(brier_score_loss(labels, scores)),
    }


def _require_metrics(recorded: dict, observed: dict, label: str) -> None:
    for key in ("n", "events", "non_events"):
        if recorded.get(key) != observed[key]:
            raise VerificationError(f"{label} {key} drift")
    for key in ("auroc", "pr_auc", "brier_descriptive_uncalibrated"):
        if not _close(recorded.get(key), observed[key]):
            raise VerificationError(f"{label} {key} drift")


def _candidate_grid(config: dict, family: str) -> list[dict]:
    candidate = next(item for item in config["candidate_model_families"] if item["family"] == family)
    combinations: list[dict] = [{}]
    for name, values in candidate["search_space"].items():
        combinations = [{**base, name: value} for base in combinations for value in values]
    return [{**candidate["fixed_parameters"], **values} for values in combinations]


def _parameter_winner(records: list[dict]) -> dict:
    eligible = [record for record in records if record.get("status") == "ELIGIBLE"]
    if not eligible:
        raise VerificationError("parameter search has no eligible candidate")
    return min(
        eligible,
        key=lambda record: (
            -float(record["mean_auroc"]),
            -float(record["mean_pr_auc"]),
            json.dumps(record["parameters"], sort_keys=True, separators=(",", ":")),
        ),
    )["parameters"]


def _verify_development_data(
    development: dict, schema: dict, require: Callable[[bool, str], None]
) -> tuple[set[str], set[str]]:
    validate_development_data_manifest(development, schema=schema)
    require(development["status"] == "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT", "development data are approved")
    require(development["integrity"]["canonical_manifest_sha256"] == canonical_manifest_sha256(development), "development manifest hash")

    source_paths = {
        "cohort.json": REPLICATION / "cohort.json",
        "features.json.gz": REPLICATION / "features.json.gz",
        "outcomes.json": REPLICATION / "outcomes.json",
        "input_inventory.json": REPLICATION / "input_inventory.json",
        "feature_report.json": REPLICATION / "feature_report.json",
        "outcome_report.json": REPLICATION / "outcome_report.json",
        "feature_schema.json": HERE / "feature_schema.json",
        "experiment_config.json": HERE / "experiment_config.json",
        "development_run_config.json": RUN_CONFIG,
        "approve_development_data.py": HERE / "approve_development_data.py",
        "run_development.py": HERE / "run_development.py",
        "label_schema.json": ROOT / "research/label_schema.json",
        "development_companies_675.json": ARTIFACTS / "development_companies_675.json",
        "e5_exclusion_companies_2000.json": ARTIFACTS / "e5_exclusion_companies_2000.json",
    }
    recorded_hashes = development["provenance"]["source_artifact_hashes"]
    require(set(recorded_hashes) == set(source_paths), "development source hash inventory")
    for name, path in source_paths.items():
        require(sha256_file(path) == recorded_hashes[name], f"development source hash: {name}")

    cohort = json.loads((REPLICATION / "cohort.json").read_text(encoding="utf-8"))
    outcomes = json.loads((REPLICATION / "outcomes.json").read_text(encoding="utf-8"))
    features = _read_gzip(REPLICATION / "features.json.gz")
    if not all(isinstance(value, list) for value in (cohort, outcomes, features)):
        raise VerificationError("replication sources must contain arrays")
    require(len(cohort) == len(outcomes) == len(features) == 2000, "2000-row source population")
    cohort_by_id = {row["observation_id"]: row for row in cohort}
    outcome_by_id = {row["observation_id"]: row for row in outcomes}
    feature_by_id = {row["observation_id"]: row for row in features}
    require(len(cohort_by_id) == len(outcome_by_id) == len(feature_by_id) == 2000, "unique source observations")

    admitted = _read(ARTIFACTS / "development_companies_675.json")
    admitted_rows = admitted["rows"]
    require(len(admitted_rows) == admitted["observation_count"] == admitted["company_count"] == 675, "675 development observations and companies")
    require(sum(row["outcome"] for row in admitted_rows) == admitted["events"] == 235, "235 development events")
    require(admitted["non_events"] == 440, "440 development non-events")
    admitted_ids = [row["observation_id"] for row in admitted_rows]
    admitted_ciks = [row["cik"] for row in admitted_rows]
    require(len(set(admitted_ids)) == len(set(admitted_ciks)) == 675, "one admitted observation per company")
    expected_verified = {
        row["observation_id"]
        for row in outcomes
        if row.get("label_status") == "VERIFIED" and row.get("financial_deterioration_12m") in {0, 1}
    }
    require(set(admitted_ids) == expected_verified, "admitted rows are exactly the verified labels")

    for admitted_row in admitted_rows:
        observation_id = admitted_row["observation_id"]
        cohort_row = cohort_by_id[observation_id]
        feature_row = feature_by_id[observation_id]
        outcome_row = outcome_by_id[observation_id]
        require(admitted_row["cik"] == cohort_row["cik"] == feature_row["cik"], "admitted CIK binds source rows")
        require(admitted_row["accession"] == cohort_row["accession"] == feature_row["accession"], "admitted accession binds source rows")
        require(admitted_row["outcome"] == outcome_row["financial_deterioration_12m"], "admitted label binds frozen outcome")
        cutoff = datetime.fromisoformat(feature_row["information_cutoff"])
        available = datetime.fromisoformat(outcome_row["outcome_available_at"])
        require(available > cutoff, "outcome is available only after prediction cutoff")
        if any(name in feature_row["metrics"] for name in ("label", "target", "financial_deterioration_12m")):
            raise VerificationError("outcome field leaked into feature metrics")
        for provenance in feature_row["provenance"].values():
            if provenance is None:
                continue
            require(provenance["source_row"]["adsh"] == feature_row["accession"], "feature provenance uses selected filing")
            require(provenance["period_end"] <= feature_row["period_end"].replace("-", ""), "feature provenance is not future-period")

    exclusions = _read(ARTIFACTS / "e5_exclusion_companies_2000.json")
    exclusion_rows = exclusions["rows"]
    exclusion_ciks = [row["cik"] for row in exclusion_rows]
    require(len(exclusion_rows) == exclusions["company_count"] == len(set(exclusion_ciks)) == 2000, "2000 unique future-E5 exclusions")
    require(exclusion_rows == sorted(exclusion_rows, key=lambda row: (row["cik"], row["source_observation_id"])), "E5 exclusions are deterministically ordered")
    require(set(admitted_ciks) <= set(exclusion_ciks), "all development companies are excluded from E5")
    require(set(exclusion_ciks) == {row["cik"] for row in cohort}, "E5 exclusion population matches the source cohort")
    return set(admitted_ids), set(admitted_ciks)


def _verify_candidates(
    config: dict, schema: dict, require: Callable[[bool, str], None]
) -> tuple[dict, dict]:
    candidates = _read(ARTIFACTS / "candidate_results.json")["candidates"]
    oof = _read(ARTIFACTS / "oof_predictions.json")["candidates"]
    expected_keys = {
        f"{family}__{block}"
        for family in APPROVED_MODEL_FAMILIES
        for block in ("V", "VO")
    }
    require(len(candidates) == 4, "exactly four eligible family/block candidates")
    require({f'{item["model_family"]}__{item["feature_block"]}' for item in candidates} == expected_keys, "candidate set matches the frozen contract")
    require(set(oof) == expected_keys, "OOF candidate set matches the frozen contract")

    by_key: dict[str, dict] = {}
    for candidate in candidates:
        family = candidate["model_family"]
        block = candidate["feature_block"]
        key = f"{family}__{block}"
        by_key[key] = candidate
        require(family in APPROVED_MODEL_FAMILIES and block in {"V", "VO"}, f"{key} is S0 eligible")
        require(candidate["feature_names"] == list(block_features(schema, block)), f"{key} feature order")
        rows = oof[key]
        ids = [row["observation_id"] for row in rows]
        ciks = [row["cik"] for row in rows]
        require(len(rows) == len(set(ids)) == len(set(ciks)) == 675, f"{key} has one OOF score per company")
        require(all(row["score_semantics"] == "UNCALIBRATED_RANKING_SCORE" for row in rows), f"{key} score semantics")
        _require_metrics(candidate, _metrics(rows), key)
        require(_close(candidate["coverage"], 1.0), f"{key} full coverage")

        row_by_id = {row["observation_id"]: row for row in rows}
        all_ids = set(row_by_id)
        test_ids: list[str] = []
        expected_grid = _candidate_grid(config, family)
        expected_grid_json = {
            json.dumps(parameters, sort_keys=True, separators=(",", ":")) for parameters in expected_grid
        }
        for fold in candidate["outer_folds"]:
            train = fold["train_observation_ids"]
            test = fold["test_observation_ids"]
            require(not (set(train) & set(test)), f"{key} outer fold train/test isolation")
            require(set(train) | set(test) == all_ids, f"{key} outer fold population")
            require({row_by_id[item]["cik"] for item in train}.isdisjoint({row_by_id[item]["cik"] for item in test}), f"{key} outer fold company isolation")
            test_ids.extend(test)
            fold_rows = [row_by_id[item] for item in test]
            _require_metrics(fold["metrics"], _metrics(fold_rows), f"{key} outer fold {fold['fold']}")
            inner = fold["inner_candidates"]
            require(
                {json.dumps(item["parameters"], sort_keys=True, separators=(",", ":")) for item in inner} == expected_grid_json,
                f"{key} inner grid is complete",
            )
            for item in inner:
                validate_candidate_parameters(family, item["parameters"], config)
                if item["status"] == "ELIGIBLE":
                    require(len(item["fold_metrics"]) == config["cross_validation"]["inner_folds"], f"{key} inner fold count")
                    require(_close(item["mean_auroc"], sum(metric["auroc"] for metric in item["fold_metrics"]) / len(item["fold_metrics"])), f"{key} inner mean AUROC")
                    require(_close(item["mean_pr_auc"], sum(metric["pr_auc"] for metric in item["fold_metrics"]) / len(item["fold_metrics"])), f"{key} inner mean PR-AUC")
            require(fold["selected_parameters"] == _parameter_winner(inner), f"{key} inner selection is mechanical")
        require(len(test_ids) == len(set(test_ids)) == 675 and set(test_ids) == all_ids, f"{key} outer folds provide exact OOF coverage")
        require(_close(candidate["mean_outer_fold_auroc"], sum(fold["metrics"]["auroc"] for fold in candidate["outer_folds"]) / len(candidate["outer_folds"])), f"{key} mean outer AUROC")
        require(_close(candidate["mean_outer_fold_pr_auc"], sum(fold["metrics"]["pr_auc"] for fold in candidate["outer_folds"]) / len(candidate["outer_folds"])), f"{key} mean outer PR-AUC")
    return by_key, oof


def _verify_reference(
    schema: dict, require: Callable[[bool, str], None]
) -> tuple[dict, dict[str, dict]]:
    reference = _read(ARTIFACTS / "empirical_development_reference.json")
    features = _read_gzip(REPLICATION / "features.json.gz")
    require(reference["status"] == "EMPIRICAL_DEVELOPMENT_REFERENCE_ONLY", "reference is development-only")
    require(reference["population"] == "ALL_2000_E4S_SOURCE_COHORT_ROWS" and reference["observation_count"] == len(features) == 2000, "reference uses all 2000 source rows")
    require(reference["construction_uses_labels"] is False, "reference is label independent")
    require(reference["source_features_sha256"] == sha256_file(REPLICATION / "features.json.gz"), "reference source identity")
    require(reference["feature_schema_sha256"] == artifact_sha256(schema), "reference schema identity")
    require(reference["construction_config_sha256"] == sha256_file(RUN_CONFIG), "reference construction config")
    require(set(reference["financial_value_profile"]).isdisjoint(reference["reporting_observability_profile"]), "reference dimensions are separate")
    require(reference["reference_sha256"] == artifact_sha256({key: value for key, value in reference.items() if key != "reference_sha256"}), "reference hash")
    for name, stats in reference["financial_value_profile"].items():
        values = np.asarray([float(row["metrics"][name]) for row in features if isinstance(row["metrics"].get(name), (int, float)) and not isinstance(row["metrics"].get(name), bool) and math.isfinite(row["metrics"][name])])
        require(stats["observed_count"] == len(values) and stats["missing_count"] == 2000 - len(values), f"reference counts: {name}")
        require(_close(stats["mean"], float(values.mean())), f"reference mean: {name}")
        require(_close(stats["standard_deviation"], float(values.std())), f"reference standard deviation: {name}")
        for label, value in stats["quantiles"].items():
            require(_close(value, float(np.quantile(values, int(label[1:]) / 100))), f"reference quantile {label}: {name}")
        observed = reference["reporting_observability_profile"][f"observed__{name}"]
        require(observed["observed_count"] == len(values) and _close(observed["observed_prevalence"], len(values) / 2000), f"reference observability: {name}")
    return reference, {row["observation_id"]: row for row in features}


def _row_in_reference(row: dict, reference: dict) -> bool:
    for name, stats in reference["financial_value_profile"].items():
        value = row["metrics"].get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            continue
        if value < stats["quantiles"]["q01"] or value > stats["quantiles"]["q99"]:
            return False
    return True


def verify() -> dict:
    checks: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise VerificationError(message)
        checks.append(message)

    schema = load_schema()
    config = load_config()
    development = _read(HERE / "development_data_manifest.json")
    admitted_ids, _ = _verify_development_data(development, schema, require)

    manifest = _read(MANIFEST)
    require(manifest["status"] == "FITTED_HISTORICAL_NOT_E5_FROZEN", "historical artifact status")
    require(manifest["hashes"]["e5_freeze_identity"] == "TO_BE_FROZEN", "E5 identity remains unfrozen")
    require(manifest["output_contract"]["calibration_status"] == "UNCALIBRATED", "score is uncalibrated")
    require(manifest["output_contract"]["probability_interpretation_allowed"] is False, "probability interpretation is forbidden")
    payload = json.loads(json.dumps(manifest))
    fitted_hash = payload["hashes"].pop("fitted_artifact_hash")
    require(artifact_sha256(payload) == fitted_hash, "fitted artifact manifest hash")
    require(manifest["feature_contract"]["feature_schema_sha256"] == artifact_sha256(schema), "manifest feature schema identity")
    require(manifest["development_data"]["manifest_sha256"] == canonical_manifest_sha256(development), "manifest development-data identity")

    filenames = {
        "candidate_results_sha256": "candidate_results.json",
        "fold_assignments_sha256": "fold_assignments.json",
        "oof_predictions_sha256": "oof_predictions.json",
        "selection_record_sha256": "selection_record.json",
        "observability_diagnostic_sha256": "observability_diagnostic.json",
        "empirical_reference_sha256": "empirical_development_reference.json",
        "selective_evaluation_sha256": "selective_evaluation.json",
        "replay_sample_sha256": "replay_sample.json",
        "runtime_identity_sha256": "runtime_identity.json",
        "verification_report_sha256": "verification_report.json",
        "fitted_preprocessor_sha256": "preprocessor.pkl",
        "fitted_model_sha256": "model.pkl",
    }
    require(set(filenames) <= set(manifest["hashes"]), "manifest file-hash inventory")
    for key, filename in filenames.items():
        require(sha256_file(ARTIFACTS / filename) == manifest["hashes"][key], f"{filename} hash")

    runtime = _read(ARTIFACTS / "runtime_identity.json")
    require(manifest["runtime"] == runtime, "runtime identity is manifest-bound")
    # The fitted artifact records the exact constraints file used for generation. The
    # active root lock was subsequently completed with research-stack pins during release
    # audit, so preserve and verify the original bytes instead of rewriting provenance.
    generation_lock = ARTIFACTS / "generation_requirements.lock"
    generation_lock_bytes = generation_lock.read_bytes()
    require(b"\r\n" not in generation_lock_bytes, "archived generation lock uses portable LF")
    # The original Windows run recorded the working-tree CRLF bytes before the root lock
    # gained an explicit LF attribute. Reconstruct that exact recorded identity while
    # storing the archival copy in portable, reviewable LF form.
    recorded_windows_lock_hash = hashlib.sha256(
        generation_lock_bytes.replace(b"\n", b"\r\n")
    ).hexdigest()
    require(
        runtime["platform"].startswith("Windows-")
        and runtime["requirements_lock_sha256"] == recorded_windows_lock_hash,
        "generation runtime lock identity",
    )
    require(runtime["numpy_version"] == np.__version__ and runtime["scikit_learn_version"] == sklearn.__version__, "replay numeric libraries match the pinned runtime")
    require(sys.version_info[:2] in {(3, 11), (3, 12)}, "replay uses a supported Python minor")
    source_commit = subprocess.run(["git", "cat-file", "-e", f'{runtime["source_commit"]}^{{commit}}'], cwd=ROOT, check=False, capture_output=True)
    require(source_commit.returncode == 0, "recorded source commit exists")

    by_key, oof = _verify_candidates(config, schema, require)
    selection = _read(ARTIFACTS / "selection_record.json")
    require(selection["human_override"] is False, "selection has no human override")
    require(selection["experiment_config_sha256"] == sha256_file(HERE / "experiment_config.json"), "selection config identity")
    require(selection["run_config_sha256"] == sha256_file(RUN_CONFIG), "selection run-config identity")
    require(selection["development_manifest_sha256"] == canonical_manifest_sha256(development), "selection development identity")
    family_rank = {"logistic_regression": 0, "histogram_gradient_boosting": 1}
    block_rank = {"V": 0, "VO": 1}
    ranked = sorted(by_key.values(), key=lambda item: (-item["mean_outer_fold_auroc"], -item["mean_outer_fold_pr_auc"], family_rank[item["model_family"]], block_rank[item["feature_block"]], json.dumps({"model_family": item["model_family"], "feature_block": item["feature_block"]}, sort_keys=True, separators=(",", ":"))))
    expected_ranking = [{"model_family": item["model_family"], "feature_block": item["feature_block"], "mean_outer_fold_auroc": item["mean_outer_fold_auroc"], "mean_outer_fold_pr_auc": item["mean_outer_fold_pr_auc"]} for item in ranked]
    require(selection["selection_ranking"] == expected_ranking, "candidate ranking is mechanically reproduced")
    selected = ranked[0]
    selected_key = f'{selected["model_family"]}__{selected["feature_block"]}'
    require(selection["selected_model_family"] == manifest["model"]["family"] == selected["model_family"], "recorded model is the mechanical winner")
    require(selection["selected_feature_block"] == manifest["feature_contract"]["selected_feature_block"] == selected["feature_block"], "recorded block is the mechanical winner")
    final_grid = selection["final_parameter_search"]
    expected_grid = _candidate_grid(config, selected["model_family"])
    require({json.dumps(item["parameters"], sort_keys=True, separators=(",", ":")) for item in final_grid} == {json.dumps(item, sort_keys=True, separators=(",", ":")) for item in expected_grid}, "final parameter grid is complete")
    require(selection["selected_final_hyperparameters"] == _parameter_winner(final_grid) == manifest["model"]["exact_hyperparameters"], "final parameters are mechanically selected")

    folds = _read(ARTIFACTS / "fold_assignments.json")
    expected_tests = [fold["test_observation_ids"] for fold in selected["outer_folds"]]
    require([fold["test_observation_ids"] for fold in folds["outer_folds"]] == expected_tests, "published fold assignments bind the winner")
    require({item for fold in expected_tests for item in fold} == admitted_ids, "published folds cover the approved observations")

    observability = _read(ARTIFACTS / "observability_diagnostic.json")
    observability_payload = {key: value for key, value in observability.items() if key != "artifact_sha256"}
    require(observability["artifact_sha256"] == artifact_sha256(observability_payload), "observability artifact hash")
    require(set(observability["blocks"]) == set(observability["oof_predictions"]) == {"V", "O", "VO", "CC"}, "all diagnostic blocks exist")
    for block, rows in observability["oof_predictions"].items():
        observed = _metrics(rows)
        expected_n = 154 if block == "CC" else 675
        require(observed["n"] == expected_n, f"{block} diagnostic population")
        _require_metrics(observability["blocks"][block], observed, f"{block} diagnostic")
        require(_close(observability["blocks"][block]["coverage"], expected_n / 675), f"{block} diagnostic coverage")
    require(observability["blocks"]["CC"]["events"] == 10, "CC is retained as a small 10-event sensitivity subset")

    reference, source_features = _verify_reference(schema, require)
    selective = _read(ARTIFACTS / "selective_evaluation.json")
    selective_payload = {key: value for key, value in selective.items() if key != "artifact_sha256"}
    require(selective["artifact_sha256"] == artifact_sha256(selective_payload), "selective-evaluation artifact hash")
    require(selective["config_sha256"] == sha256_file(RUN_CONFIG), "selective policy config identity")
    require(selective["status"] == "RETROSPECTIVE_DEVELOPMENT_DRY_RUN", "S0/S1 dry-run status")
    selected_oof = oof[selected_key]
    labels = [row["label"] for row in selected_oof]
    scores = [row["score"] for row in selected_oof]
    in_reference = [_row_in_reference(source_features[row["observation_id"]], reference) for row in selected_oof]
    run_config = _read(RUN_CONFIG)
    s0 = ["FLAG" if score >= run_config["s0_decision_rule"]["threshold"] else "PASS" for score in scores]
    s1_policy = run_config["s1_selective_policy"]
    s1 = ["FLAG" if score >= s1_policy["authorize_flag_at_or_above"] else "PASS" if score < s1_policy["authorize_pass_below"] else "REVIEW" for score in scores]
    require(selective["s0"] == evaluate_decisions(labels, s0, in_reference=in_reference), "S0 metrics independently reproduced")
    require(selective["s1"] == evaluate_decisions(labels, s1, in_reference=in_reference), "S1 metrics independently reproduced")
    require(selective["risk_coverage_curve"] == risk_coverage_curve(labels, scores), "risk-coverage curve independently reproduced")

    canonical = _read(ARTIFACTS / "canonical_results.json")
    canonical_payload = {key: value for key, value in canonical.items() if key != "result_sha256"}
    require(canonical["result_sha256"] == artifact_sha256(canonical_payload), "canonical result hash")
    expected_development = {key: selected[key] for key in ("n", "events", "auroc", "pr_auc", "brier_descriptive_uncalibrated")}
    require(canonical["development_oof"] == expected_development, "canonical development metrics bind OOF predictions")
    require(canonical["selected_feature_block"] == selected["feature_block"] and canonical["selected_model_family"] == selected["model_family"], "canonical winner identity")
    require(canonical["selected_hyperparameters"] == selection["selected_final_hyperparameters"], "canonical hyperparameters")
    require(canonical["observability_blocks"] == observability["blocks"], "canonical observability metrics")
    require(canonical["selective_evaluation"] == {"s0": selective["s0"], "s1": selective["s1"]}, "canonical S0/S1 metrics")
    require(canonical["empirical_reference_sha256"] == reference["reference_sha256"], "canonical reference identity")
    require(canonical["fitted_artifact_hash"] == fitted_hash, "canonical fitted artifact identity")
    require(canonical["calibration_status"] == "UNCALIBRATED", "canonical calibration boundary")

    replay = _read(ARTIFACTS / "replay_sample.json")
    require(replay["ordered_feature_names"] == manifest["feature_contract"]["ordered_feature_names"], "replay feature order")
    observed_scores = predict_scores(replay["matrix"], ordered_feature_names=replay["ordered_feature_names"])
    tolerance = float(replay["absolute_tolerance"])
    require(len(observed_scores) == len(replay["expected_scores"]), "replay score count")
    require(all(math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance) for left, right in zip(observed_scores, replay["expected_scores"], strict=True)), "pinned-runtime replay")
    return {
        "status": "PASS",
        "checks": len(checks),
        "fitted_artifact_hash": fitted_hash,
        "replay_rows": len(observed_scores),
        "e5_freeze_identity": "TO_BE_FROZEN",
    }


def main() -> int:
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
