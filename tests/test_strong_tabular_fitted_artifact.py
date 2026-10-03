from __future__ import annotations

import json
import shutil

import pytest

from research.strong_tabular_reference import artifact
from research.strong_tabular_reference.verify_artifact import verify


def test_checked_in_artifact_and_replay_verify() -> None:
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
