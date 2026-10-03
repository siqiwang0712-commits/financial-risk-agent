"""Verify the fitted historical reference without retraining."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .artifact import (
    ARTIFACTS,
    MANIFEST,
    load_trusted_artifact,
    predict_scores,
    sha256_file,
)
from .contract import artifact_sha256, load_config, load_schema
from .development_data import validate_development_data_manifest

HERE = Path(__file__).resolve().parent


class VerificationError(RuntimeError):
    """Raised when any checked-in artifact or semantic invariant drifts."""


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VerificationError(f"{path.name} must contain an object")
    return value


def verify() -> dict:
    checks: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise VerificationError(message)
        checks.append(message)

    schema = load_schema()
    config = load_config()
    development = _read(HERE / "development_data_manifest.json")
    validate_development_data_manifest(development, schema=schema)
    require(
        development["status"] == "APPROVED_FOR_STRONG_REFERENCE_DEVELOPMENT",
        "development data are approved",
    )
    require(development["population"]["observation_count"] == 675, "675 labeled observations")
    require(
        development["population"]["source_population_company_count"] == 2000,
        "2000 source companies are excluded from E5",
    )

    manifest = _read(MANIFEST)
    require(manifest["status"] == "FITTED_HISTORICAL_NOT_E5_FROZEN", "historical artifact status")
    require(manifest["hashes"]["e5_freeze_identity"] == "TO_BE_FROZEN", "E5 identity remains unfrozen")
    require(manifest["output_contract"]["calibration_status"] == "UNCALIBRATED", "score is uncalibrated")
    require(
        manifest["output_contract"]["probability_interpretation_allowed"] is False,
        "probability interpretation is forbidden",
    )
    payload = json.loads(json.dumps(manifest))
    fitted_hash = payload["hashes"].pop("fitted_artifact_hash")
    require(artifact_sha256(payload) == fitted_hash, "fitted artifact hash")
    for key, digest in manifest["hashes"].items():
        if not key.endswith("_sha256") or key == "fitted_artifact_hash":
            continue
        filename = {
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
        }.get(key)
        if filename:
            require(sha256_file(ARTIFACTS / filename) == digest, f"{filename} hash")

    selection = _read(ARTIFACTS / "selection_record.json")
    require(selection["human_override"] is False, "selection has no human override")
    require(selection["selected_feature_block"] in {"V", "VO"}, "selected block is S0 eligible")
    require(selection["selected_model_family"] in {item["family"] for item in config["candidate_model_families"]}, "selected family is approved")
    ranking = selection["selection_ranking"]
    require(ranking[0]["model_family"] == selection["selected_model_family"], "ranking selects recorded family")
    require(ranking[0]["feature_block"] == selection["selected_feature_block"], "ranking selects recorded block")

    folds = _read(ARTIFACTS / "fold_assignments.json")
    identifiers = [identifier for fold in folds["outer_folds"] for identifier in fold["test_observation_ids"]]
    require(len(identifiers) == len(set(identifiers)) == 675, "each observation appears in one outer test fold")

    reference = _read(ARTIFACTS / "empirical_development_reference.json")
    require(reference["construction_uses_labels"] is False, "reference is label independent")
    require(set(reference["financial_value_profile"]).isdisjoint(reference["reporting_observability_profile"]), "reference dimensions are separate")
    require(reference["feature_schema_sha256"] == artifact_sha256(schema), "reference schema identity")
    require(reference["reference_sha256"] == artifact_sha256({key: value for key, value in reference.items() if key != "reference_sha256"}), "reference hash")

    observability = _read(ARTIFACTS / "observability_diagnostic.json")
    require(set(observability["blocks"]) == {"V", "O", "VO", "CC"}, "all diagnostic blocks exist")
    selective = _read(ARTIFACTS / "selective_evaluation.json")
    require(selective["status"] == "RETROSPECTIVE_DEVELOPMENT_DRY_RUN", "S0/S1 dry run status")

    replay = _read(ARTIFACTS / "replay_sample.json")
    load_trusted_artifact()
    observed = predict_scores(replay["matrix"])
    tolerance = float(replay["absolute_tolerance"])
    require(
        all(math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance) for left, right in zip(observed, replay["expected_scores"], strict=True)),
        "pinned-runtime replay",
    )
    return {
        "status": "PASS",
        "checks": len(checks),
        "fitted_artifact_hash": fitted_hash,
        "replay_rows": len(observed),
        "e5_freeze_identity": "TO_BE_FROZEN",
    }


def main() -> int:
    print(json.dumps(verify(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
