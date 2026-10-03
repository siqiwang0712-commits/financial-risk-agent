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
    if frontend.get("version") != expected or lock.get("version") != expected:
        raise SystemExit("frontend version drift")
    if (lock.get("packages") or {}).get("", {}).get("version") != expected:
        raise SystemExit("frontend lock root version drift")
    for relative in ("backend/Dockerfile", "frontend/Dockerfile"):
        if f"ARG OCI_VERSION={expected}" not in (ROOT / relative).read_text():
            raise SystemExit(f"container version drift: {relative}")


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
        manifest["hashes"]["fitted_artifact_hash"]: True,
    }
    for relative in ("README.md", "README.zh-CN.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in list(expected)[:5]:
            if token not in text:
                raise SystemExit(f"headline drift: {token} absent from {relative}")
    notes = (ROOT / "RELEASE_NOTES_v0.4.1.md").read_text(encoding="utf-8")
    for token in expected:
        if token not in notes:
            raise SystemExit(f"release-note headline drift: {token}")
    if not re.search(r"E5 remains.*DRAFT_NOT_FROZEN", notes, re.DOTALL):
        raise SystemExit("release notes do not preserve the E5 boundary")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ci",
        action="store_true",
        help="skip slow duplicate historical recomputation; never skips v0.4.1 artifacts",
    )
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    verify_versions()
    verify_headlines()
    run("StrongTabularReference draft contract", [sys.executable, "-m", "research.strong_tabular_reference.contract"])
    run("fitted artifact and replay", [sys.executable, "-m", "research.strong_tabular_reference.verify_artifact"])
    backend_env = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    run("v0.4.1 runtime identities", [sys.executable, "scripts/generate_v041_runtime_identities.py", "--check"], env=backend_env)
    run("E5 stage-aware preflight", [sys.executable, "scripts/e5_preflight.py", "--check"])
    run("authoritative E5 contract", [sys.executable, "-m", "research.e5.validate_study_contract"])
    run("E5 remains NOT_FROZEN", [sys.executable, "research/e5/protocol/verify_freeze_chain.py", "--report-only"])
    run("frozen E4 public artifacts", [sys.executable, "scripts/verify_e4_public_artifacts.py"])
    if not args.ci:
        run(
            "E4-S integrity",
            [sys.executable, "research/e4_statistical_audit/verify_audit.py", "--quick", "--out", str(RUNTIME / "e4s.json")],
        )
        run("E4-R integrity", [sys.executable, "research/e4r_automated_robustness/verify_e4r.py"])
    run("Markdown links", [sys.executable, "scripts/check_markdown_links.py"])
    print("v0.4.1 checked-in release artifacts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
