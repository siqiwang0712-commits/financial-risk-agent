from __future__ import annotations

import json
import shutil
from copy import deepcopy

import numpy as np
import pytest
import sklearn

from research.strong_tabular_reference import artifact
from research.strong_tabular_reference.contract import artifact_sha256
from research.strong_tabular_reference.verify_artifact import VerificationError, verify


def test_checked_in_artifact_and_replay_is_runtime_bound() -> None:
    runtime = json.loads(
        (artifact.ARTIFACTS / "runtime_identity.json").read_text(encoding="utf-8")
    )
    if (
        runtime["numpy_version"] != np.__version__
        or runtime["scikit_learn_version"] != sklearn.__version__
    ):
        # Product code supports Python 3.11 and 3.12. The fitted research pickle has a
        # narrower, hash-bound replay environment and must fail closed when its numeric
        # stack differs instead of pretending that reproduction succeeded.
        with pytest.raises(VerificationError, match="pinned runtime"):
            verify()
        return
    report = verify()
    assert report["status"] == "PASS"
    assert report["replay_rows"] == 10


def test_preprocessor_tamper_fails_before_deserialization(tmp_path, monkeypatch) -> None:
    shutil.copytree(artifact.ARTIFACTS, tmp_path / "artifacts")
    root = tmp_path / "artifacts"
    path = root / "preprocessor.pkl"
    path.write_bytes(path.read_bytes() + b"tamper")
    monkeypatch.setattr(artifact, "ARTIFACTS", root)
    with pytest.raises(artifact.ArtifactIntegrityError, match="preprocessor hash mismatch"):
        artifact.load_trusted_artifact(root / "artifact_manifest.json")


def test_model_tamper_fails_before_deserialization(tmp_path, monkeypatch) -> None:
    shutil.copytree(artifact.ARTIFACTS, tmp_path / "artifacts")
    root = tmp_path / "artifacts"
    path = root / "model.pkl"
    path.write_bytes(path.read_bytes() + b"tamper")
    monkeypatch.setattr(artifact, "ARTIFACTS", root)
    with pytest.raises(artifact.ArtifactIntegrityError, match="model hash mismatch"):
        artifact.load_trusted_artifact(root / "artifact_manifest.json")


def test_output_contract_is_score_not_probability() -> None:
    manifest = json.loads(artifact.MANIFEST.read_text(encoding="utf-8"))
    output = manifest["output_contract"]
    assert output["score_semantics"] == "UNCALIBRATED_RANKING_SCORE"
    assert output["probability_interpretation_allowed"] is False


def test_manifest_tamper_fails_before_deserialization(tmp_path, monkeypatch) -> None:
    shutil.copytree(artifact.ARTIFACTS, tmp_path / "artifacts")
    root = tmp_path / "artifacts"
    path = root / "artifact_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["model"]["family"] = "tampered"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(artifact, "ARTIFACTS", root)
    monkeypatch.setattr(
        artifact.pickle,
        "load",
        lambda _handle: pytest.fail("pickle must not load before manifest verification"),
    )
    with pytest.raises(artifact.ArtifactIntegrityError, match="manifest hash mismatch"):
        artifact.load_trusted_artifact(path)


def test_schema_identity_tamper_fails_even_with_recomputed_manifest_hash(
    tmp_path, monkeypatch
) -> None:
    shutil.copytree(artifact.ARTIFACTS, tmp_path / "artifacts")
    root = tmp_path / "artifacts"
    path = root / "artifact_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["feature_contract"]["feature_schema_sha256"] = "0" * 64
    payload = deepcopy(manifest)
    payload["hashes"].pop("fitted_artifact_hash")
    manifest["hashes"]["fitted_artifact_hash"] = artifact_sha256(payload)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(artifact, "ARTIFACTS", root)
    with pytest.raises(artifact.ArtifactIntegrityError, match="feature schema identity"):
        artifact.load_trusted_artifact(path)


@pytest.mark.parametrize("mode", ["reordered", "missing", "unknown"])
def test_replay_rejects_feature_identity_before_deserialization(
    mode: str, monkeypatch
) -> None:
    replay = json.loads((artifact.ARTIFACTS / "replay_sample.json").read_text())
    names = list(replay["ordered_feature_names"])
    matrix = replay["matrix"]
    if mode == "reordered":
        names[0], names[1] = names[1], names[0]
    elif mode == "missing":
        names = names[:-1]
        matrix = [row[:-1] for row in matrix]
    else:
        names[0] = "unknown_feature"
    monkeypatch.setattr(
        artifact.pickle,
        "load",
        lambda _handle: pytest.fail("pickle must not load for a mismatched input contract"),
    )
    with pytest.raises(artifact.ArtifactIntegrityError, match="feature names/order"):
        artifact.predict_scores(matrix, ordered_feature_names=names)
