from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_state(root: Path) -> dict[str, Any]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=root,
            text=True,
        ).strip()
    )
    return {"commit": commit, "dirty": dirty, "state": "dirty" if dirty else "clean"}


def verify_frozen_experiment(directory: Path, root: Path) -> dict[str, Any]:
    """Verify immutable bytes without regenerating or writing experiment files."""
    manifest_path = directory / "forensic_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest_hash = manifest["manifest_hash"]
    content = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    actual_manifest_hash = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    artifacts = []
    for name, expected in manifest["artifact_hashes"].items():
        path = directory / name
        actual = sha256_bytes(path) if path.is_file() else None
        artifacts.append(
            {"artifact": name, "expected_hash": expected, "actual_hash": actual,
             "verified": actual == expected}
        )
    experiment_manifest = json.loads(
        (directory / "experiment_manifest.json").read_text(encoding="utf-8")
    )
    current = git_state(root)
    verified = actual_manifest_hash == expected_manifest_hash and all(
        item["verified"] for item in artifacts
    )
    return {
        "experiment_id": manifest["experiment_id"],
        "mode": "FROZEN_ARTIFACT_REPLAY",
        "writes_performed": False,
        "artifact_integrity": "VERIFIED" if verified else "FAILED",
        "external_source_reverification": "NOT_RUN",
        "original_generation_commit": experiment_manifest.get("git_commit", "UNAVAILABLE"),
        "current_replay_commit": current["commit"],
        "current_working_tree_state": current["state"],
        "manifest_hash_verified": actual_manifest_hash == expected_manifest_hash,
        "artifacts": artifacts,
    }


def prospective_experiment_metadata(root: Path) -> dict[str, Any]:
    """Dynamic provenance for experiments created after v0.3.1."""
    state = git_state(root)
    return {
        "git_commit": state["commit"],
        "git_dirty": state["dirty"],
        "working_tree_state": state["state"],
    }
