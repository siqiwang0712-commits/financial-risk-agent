"""Verify the checked-in v0.4.1 release artifacts without retraining models."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "v041-verification"


def run(label: str, command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"== {label} ==", flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def verify_versions() -> None:
    import finrisk

    expected = "0.4.1"
    if finrisk.__version__ != expected:
        raise SystemExit("Python runtime version drift")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    frontend = _json("frontend/package.json")
    lock = _json("frontend/package-lock.json")
    if f'version = "{expected}"' not in pyproject:
        raise SystemExit("pyproject version drift")
    if 'license = "Apache-2.0"' not in pyproject or 'requires-python = ">=3.11,<3.13"' not in pyproject:
        raise SystemExit("Python package license/interpreter metadata drift")
    if frontend.get("version") != expected or lock.get("version") != expected:
        raise SystemExit("frontend version drift")
    if frontend.get("license") != "Apache-2.0":
        raise SystemExit("frontend license metadata drift")
    if (lock.get("packages") or {}).get("", {}).get("version") != expected:
        raise SystemExit("frontend lock root version drift")
    for relative in ("backend/Dockerfile", "frontend/Dockerfile"):
        dockerfile = (ROOT / relative).read_text()
        if f"ARG OCI_VERSION={expected}" not in dockerfile:
            raise SystemExit(f"container version drift: {relative}")
        if 'org.opencontainers.image.licenses="Apache-2.0"' not in dockerfile:
            raise SystemExit(f"container license drift: {relative}")
    if "Apache License" not in (ROOT / "LICENSE").read_text(encoding="utf-8")[:200]:
        raise SystemExit("LICENSE does not contain the declared Apache license")


def verify_headlines() -> None:
    results = _json(
        "research/strong_tabular_reference/artifacts/canonical_results.json"
    )
    manifest = _json(
        "research/strong_tabular_reference/artifacts/artifact_manifest.json"
    )
    expected = {
        "0.881789": results["development_oof"]["auroc"],
        "0.828968": results["development_oof"]["pr_auc"],
        "0.872060": results["observability_blocks"]["V"]["auroc"],
        "0.835933": results["observability_blocks"]["O"]["auroc"],
        "0.676736": results["observability_blocks"]["CC"]["auroc"],
    }
    for relative in ("README.md", "README.zh-CN.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in expected:
            if token not in text:
                raise SystemExit(f"headline drift: {token} absent from {relative}")
    notes = (ROOT / "RELEASE_NOTES_v0.4.1.md").read_text(encoding="utf-8")
    release_tokens = {
        *expected,
        str(results["development_oof"]["n"]),
        str(results["development_oof"]["events"]),
        "440",
        "154",
        "10",
        str(results["development_oof"]["brier_descriptive_uncalibrated"]),
        results["selected_feature_block"],
        results["selected_model_family"],
        results["empirical_reference_sha256"],
        manifest["hashes"]["fitted_artifact_hash"],
        "UNCALIBRATED",
        "RETROSPECTIVE_DEVELOPMENT",
    }
    for token in release_tokens:
        if token not in notes:
            raise SystemExit(f"release-note headline drift: {token}")
    if not re.search(r"E5 remains.*DRAFT_NOT_FROZEN", notes, re.DOTALL):
        raise SystemExit("release notes do not preserve the E5 boundary")
    active_status = "\n".join(
        (ROOT / relative).read_text(encoding="utf-8")
        for relative in ("PROJECT_STATUS.md", "RELEASE_NOTES_v0.4.1.md")
    )
    for stale in ("713 passed", "14 skipped", "90.52%"):
        if stale in active_status:
            raise SystemExit(f"stale release-verification headline: {stale}")


def verify_artifacts(runtime_identity_script: str = "scripts/generate_v041_runtime_identities.py") -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    verify_versions()
    run("StrongTabularReference draft contract", [sys.executable, "-m", "research.strong_tabular_reference.contract"])
    run("fitted artifact and replay", [sys.executable, "-m", "research.strong_tabular_reference.verify_artifact"])
    # Headline prose is checked only after the canonical result has been independently
    # rebuilt from its hash-bound OOF, selection, reference and selective artifacts.
    verify_headlines()
    backend_env = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    run("runtime identities", [sys.executable, "-m", runtime_identity_script.removesuffix(".py").replace("/", "."), "--check"], env=backend_env)
    run("E5 stage-aware preflight", [sys.executable, "scripts/e5_preflight.py", "--check"])
    run("authoritative E5 contract", [sys.executable, "-m", "research.e5.validate_study_contract"])
    run("E5 remains NOT_FROZEN", [sys.executable, "research/e5/protocol/verify_freeze_chain.py", "--report-only"])
    run("frozen E4 public artifacts", [sys.executable, "scripts/verify_e4_public_artifacts.py"])
    run(
        "E4-S integrity",
        [sys.executable, "research/e4_statistical_audit/verify_audit.py", "--quick", "--out", str(RUNTIME / "e4s.json")],
    )
    run("E4-R integrity", [sys.executable, "research/e4r_automated_robustness/verify_e4r.py"])
    run("Markdown links", [sys.executable, "scripts/check_markdown_links.py"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci", action="store_true", help="CI-compatible output; all historical checks still run")
    parser.parse_args()
    verify_artifacts()
    print("v0.4.1 checked-in release artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
