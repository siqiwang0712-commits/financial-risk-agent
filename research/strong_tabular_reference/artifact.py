"""Trusted loading and replay for the fitted historical reference artifact."""

from __future__ import annotations

import hashlib
import json
import pickle
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from .contract import artifact_sha256, load_schema
from .development_data import canonical_manifest_sha256

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
MANIFEST = ARTIFACTS / "artifact_manifest.json"


class ArtifactIntegrityError(RuntimeError):
    """Raised before deserialization when an artifact identity is not trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trusted_path(relative: str, root: Path) -> Path:
    candidate = (root / relative).resolve()
    if root.resolve() not in candidate.parents:
        raise ArtifactIntegrityError("artifact path escapes the trusted research directory")
    return candidate


def _verified_manifest(manifest_path: Path) -> tuple[dict[str, Any], Path, Path]:
    """Validate the manifest and every non-executable identity used by the loader."""

    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    if root != ARTIFACTS.resolve() or manifest_path != (root / "artifact_manifest.json"):
        raise ArtifactIntegrityError("only the checked-in StrongTabularReference manifest is trusted")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError("artifact manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("artifact") != "StrongTabularReference-v1":
        raise ArtifactIntegrityError("unexpected artifact identity")
    if manifest.get("status") != "FITTED_HISTORICAL_NOT_E5_FROZEN":
        raise ArtifactIntegrityError("artifact is not an approved fitted historical reference")

    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict):
        raise ArtifactIntegrityError("artifact hashes are missing")
    payload = deepcopy(manifest)
    recorded_fitted_hash = (payload.get("hashes") or {}).pop("fitted_artifact_hash", None)
    if artifact_sha256(payload) != recorded_fitted_hash:
        raise ArtifactIntegrityError("fitted artifact manifest hash mismatch")
    if manifest.get("feature_contract", {}).get("feature_schema_sha256") != artifact_sha256(
        load_schema()
    ):
        raise ArtifactIntegrityError("feature schema identity mismatch")

    development_path = HERE / "development_data_manifest.json"
    try:
        development = json.loads(development_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError("development-data manifest is unreadable") from exc
    if manifest.get("development_data", {}).get("manifest") != "../development_data_manifest.json":
        raise ArtifactIntegrityError("unexpected development-data manifest path")
    if manifest["development_data"].get("manifest_sha256") != canonical_manifest_sha256(
        development
    ):
        raise ArtifactIntegrityError("development-data manifest identity mismatch")

    preprocessor_path = _trusted_path(manifest["preprocessing"]["serialized_artifact"], root)
    model_path = _trusted_path(manifest["model"]["serialized_artifact"], root)
    if sha256_file(preprocessor_path) != hashes.get("fitted_preprocessor_sha256"):
        raise ArtifactIntegrityError("preprocessor hash mismatch")
    if sha256_file(model_path) != hashes.get("fitted_model_sha256"):
        raise ArtifactIntegrityError("model hash mismatch")
    return manifest, preprocessor_path, model_path


def load_trusted_artifact(
    manifest_path: Path = MANIFEST,
) -> tuple[dict[str, Any], Any, Any]:
    """Verify every serialized hash before loading repository-generated joblib files."""

    manifest, preprocessor_path, model_path = _verified_manifest(manifest_path)
    # joblib/pickle is code-executing serialization. Deserialization occurs only after the
    # fixed trusted root and exact hashes above have been verified.
    with preprocessor_path.open("rb") as handle:
        preprocessor = pickle.load(handle)
    with model_path.open("rb") as handle:
        model = pickle.load(handle)
    return manifest, preprocessor, model


def predict_scores(
    matrix: list[list[float]],
    *,
    ordered_feature_names: list[str] | tuple[str, ...],
    manifest_path: Path = MANIFEST,
) -> list[float]:
    """Replay scores only when the caller binds the exact ordered feature contract."""

    manifest, _, _ = _verified_manifest(manifest_path)
    expected_names = tuple(manifest["feature_contract"]["ordered_feature_names"])
    if tuple(ordered_feature_names) != expected_names:
        raise ArtifactIntegrityError("input feature names/order do not match the manifest")
    try:
        array = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ArtifactIntegrityError("input matrix must contain numeric values") from exc
    if array.ndim != 2 or array.shape[1] != len(expected_names):
        raise ArtifactIntegrityError("input feature width does not match the manifest")
    if np.isinf(array).any():
        raise ArtifactIntegrityError("input matrix contains infinite values")
    _, preprocessor, model = load_trusted_artifact(manifest_path)
    transformed = preprocessor.transform(array)
    scores = np.asarray(model.predict_proba(transformed)[:, 1], dtype=float)
    if not np.isfinite(scores).all() or ((scores < 0.0) | (scores > 1.0)).any():
        raise ArtifactIntegrityError("model emitted an invalid uncalibrated score")
    return [float(value) for value in scores]
