"""Trusted loading and replay for the fitted historical reference artifact."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

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


def load_trusted_artifact(
    manifest_path: Path = MANIFEST,
) -> tuple[dict[str, Any], Any, Any]:
    """Verify every serialized hash before loading repository-generated joblib files."""

    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    if root != ARTIFACTS.resolve():
        raise ArtifactIntegrityError("only the checked-in StrongTabularReference artifact root is trusted")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("artifact") != "StrongTabularReference-v1":
        raise ArtifactIntegrityError("unexpected artifact identity")
    if manifest.get("status") != "FITTED_HISTORICAL_NOT_E5_FROZEN":
        raise ArtifactIntegrityError("artifact is not an approved fitted historical reference")
    hashes = manifest.get("hashes") or {}
    preprocessor_path = _trusted_path(manifest["preprocessing"]["serialized_artifact"], root)
    model_path = _trusted_path(manifest["model"]["serialized_artifact"], root)
    if sha256_file(preprocessor_path) != hashes.get("fitted_preprocessor_sha256"):
        raise ArtifactIntegrityError("preprocessor hash mismatch")
    if sha256_file(model_path) != hashes.get("fitted_model_sha256"):
        raise ArtifactIntegrityError("model hash mismatch")
    # joblib/pickle is code-executing serialization. Deserialization occurs only after the
    # fixed trusted root and exact hashes above have been verified.
    with preprocessor_path.open("rb") as handle:
        preprocessor = pickle.load(handle)
    with model_path.open("rb") as handle:
        model = pickle.load(handle)
    return manifest, preprocessor, model


def predict_scores(matrix: list[list[float]], manifest_path: Path = MANIFEST) -> list[float]:
    manifest, preprocessor, model = load_trusted_artifact(manifest_path)
    expected = len(manifest["feature_contract"]["ordered_feature_names"])
    array = np.asarray(matrix, dtype=float)
    if array.ndim != 2 or array.shape[1] != expected:
        raise ArtifactIntegrityError("input feature ordering/width does not match the manifest")
    transformed = preprocessor.transform(array)
    return [float(value) for value in model.predict_proba(transformed)[:, 1]]
