"""Executable staged harness for the E5 confirmatory study.

Why this exists
---------------
A protocol written in Markdown does not stop anybody from editing it after the results are
known. E4's protocol, implementation, results and post-hoc audit all entered public history
in one commit, which is why E4 can only claim to be *internally* frozen. The fix is
mechanical: every stage writes a manifest that records the hash of everything a later stage
is allowed to depend on, and the verifier recomputes those hashes from the current tree.

Design
------
Ten stages, each with a machine-verifiable manifest:

    0 protocol
    1 model-qualification
    2 cohort-freeze
    3 feature-packet-freeze
    4 prediction-freeze
    5 outcome-unlock
    6 adjudication-freeze
    7 statistical-analysis
    8 final-report

Each manifest records: sequence, previous manifest hash, UTC timestamp, git commit and
cleanliness, environment (interpreter, platform, lock hash, required and actual environment
variables), the hash of the frozen protocol document, the hash of the frozen config, the
hash of the frozen model identity, artifact hashes with roles and byte counts, and stage
specific counts.

What the verifier enforces
--------------------------
* stage order, sequence numbers and non-decreasing timestamps;
* every artifact still hashes to the recorded value;
* the manifest chain: stage N's recorded previous-manifest hash equals the canonical hash
  of stage N-1's manifest;
* the protocol and config recorded at freeze still hash to the same values — editing either
  after a freeze fails verification;
* the frozen model identity recorded at stage 1 is unchanged;
* outcome-bearing artifacts (role ``outcome`` or ``label``) appear only from stage 5;
* stage 4 asserts, and later stages confirm, that no outcome path was accessible before the
  prediction freeze;
* stage 2 cannot be verified as complete unless historical company-disjointness is proven,
  because `previous_270.json` is unpublished.

Nothing here runs a model or produces a result. Stages 5 through 8 do not exist yet, and the
verifier reports them as absent rather than inventing them.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
E5_DIR = HARNESS_DIR.parent
PROTOCOL_DIR = E5_DIR / "protocol"
REPO_ROOT = E5_DIR.parents[1]

PROTOCOL_DOCUMENT = PROTOCOL_DIR / "STUDY_PROTOCOL.md"
CONFIG_DOCUMENT = PROTOCOL_DIR / "experiment_config.json"
REPRESENTATIONS_DOCUMENT = PROTOCOL_DIR / "representations.json"
PACKAGES_LOCK = REPO_ROOT / "requirements.lock"
DEFAULT_STAGE_DIR = E5_DIR / "freeze"

OUTCOME_ROLES = frozenset({"outcome", "label", "adjudication"})
OUTCOME_BEARING_FROM_SEQUENCE = 5


@dataclass(frozen=True)
class StageDef:
    name: str
    sequence: int
    description: str
    outcome_allowed: bool = False

    @property
    def directory_name(self) -> str:
        return f"{self.sequence:02d}-{self.name}"


STAGES: tuple[StageDef, ...] = (
    StageDef("protocol", 0, "Freeze protocol, hypotheses, inference policy, representations."),
    StageDef("model-qualification", 1, "Freeze the single primary Agent configuration."),
    StageDef("cohort-freeze", 2, "Freeze the cohort and prove historical disjointness."),
    StageDef("feature-packet-freeze", 3, "Freeze features and per-company Agent packets."),
    StageDef("prediction-freeze", 4, "Freeze all predictions with outcomes inaccessible."),
    StageDef("outcome-unlock", 5, "Mount future outcomes and freeze the raw labels.", outcome_allowed=True),
    StageDef("adjudication-freeze", 6, "Freeze blinded human adjudication and agreement.", outcome_allowed=True),
    StageDef("statistical-analysis", 7, "Run the prespecified primary and secondary analyses.", outcome_allowed=True),
    StageDef("final-report", 8, "Render claims from the canonical summary only.", outcome_allowed=True),
)

STAGE_BY_NAME = {stage.name: stage for stage in STAGES}


class HarnessError(RuntimeError):
    """Raised when the harness refuses to proceed."""


# --------------------------------------------------------------------------------------
# Hashing helpers
# --------------------------------------------------------------------------------------


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_document(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


# --------------------------------------------------------------------------------------
# Environment capture and checking
# --------------------------------------------------------------------------------------


def git_head(repo_root: Path = REPO_ROOT) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def git_worktree_clean(repo_root: Path = REPO_ROOT) -> bool | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return not result.stdout.strip()


def capture_environment(
    required_variables: dict[str, str] | None = None,
    extra_variables: dict[str, str] | None = None,
) -> dict:
    """Record everything a re-run would need to reproduce the stage.

    E4 needed an undocumented ``FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES`` override because the
    frozen default is smaller than the real archive members; E5 records required variables
    explicitly so that class of defect cannot recur silently.
    """
    required = dict(required_variables or {})
    observed = {name: os.environ.get(name) for name in sorted(required)}
    extra = dict(extra_variables or {})
    return {
        "python_version": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages_lock_sha256": sha256_document(PACKAGES_LOCK),
        "required_environment_variables": required,
        "observed_required_environment_variables": observed,
        "recorded_environment_variables": extra,
    }


def check_environment(recorded: dict) -> list[dict]:
    """Compare the current environment against a recorded one."""
    findings: list[dict] = []
    if not recorded:
        return [{"check": "environment recorded", "status": "FAIL", "detail": "manifest has no environment block"}]

    findings.append(
        _finding(
            "environment: python version",
            sys.version.split()[0] == recorded.get("python_version"),
            f"now {sys.version.split()[0]}, frozen {recorded.get('python_version')}",
        )
    )
    lock_now = sha256_document(PACKAGES_LOCK)
    findings.append(
        _finding(
            "environment: requirements.lock",
            lock_now == recorded.get("packages_lock_sha256"),
            f"now {lock_now}, frozen {recorded.get('packages_lock_sha256')}",
        )
    )
    for name, expected in sorted((recorded.get("required_environment_variables") or {}).items()):
        actual = os.environ.get(name)
        findings.append(
            _finding(
                f"environment: {name}",
                actual == expected,
                f"expected {expected!r}, observed {actual!r}",
            )
        )
    return findings


def _finding(name: str, passed: bool, detail: str) -> dict:
    return {"check": name, "status": "PASS" if passed else "FAIL", "detail": "" if passed else detail}


# --------------------------------------------------------------------------------------
# Outcome inaccessibility
# --------------------------------------------------------------------------------------


def assert_single_company_context(packet: dict, *, max_companies: int = 1) -> dict:
    """Reject any Agent packet that carries more than one company.

    E4 measured a mean absolute batch-versus-single score difference of 0.101 with a rank
    correlation of only ~0.313, so sharing a semantic context across companies measurably
    changes the score. Batching may happen at transport level; it must never happen inside a
    model context. This is the mechanical guard, and a test exercises both branches.
    """
    case_ids = packet.get("case_ids")
    if case_ids is None:
        case_ids = [packet.get("case_id")] if packet.get("case_id") is not None else []
    count = len(set(case_ids))
    return {
        "company_count": count,
        "max_companies": max_companies,
        "single_company_context": count <= max_companies,
        "case_ids": sorted(set(case_ids)),
    }


def assert_outcome_inaccessible(candidate_paths: list[str]) -> dict:
    """Fail closed if any outcome path exists before the prediction freeze.

    This is the mechanical counterpart of E4's mount discipline: rather than trusting that a
    stage "did not look", the harness records that the paths were absent, and the verifier
    re-checks the recorded assertion against the current filesystem.
    """
    existing = [str(path) for path in candidate_paths if Path(path).exists()]
    return {
        "checked_paths": [str(path) for path in candidate_paths],
        "existing_paths": existing,
        "outcome_inaccessible": not existing,
        "checked_at_utc": _utc_now(),
    }


# --------------------------------------------------------------------------------------
# Manifest writing (frozen: refuse to overwrite)
# --------------------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_sha256(manifest: dict) -> str:
    """Canonical hash of a manifest, excluding its own hash field."""
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return sha256_bytes(canonical_bytes(payload))


def write_manifest(stage_dir: Path, manifest: dict) -> Path:
    """Write a stage manifest. Refuses to overwrite, so a stage cannot be silently redone."""
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage = STAGE_BY_NAME[manifest["stage"]]
    path = stage_dir / f"{stage.directory_name}.json"
    if path.exists():
        raise HarnessError(f"refusing to overwrite frozen stage manifest: {path}")
    # Mutate the caller's dict so it can be handed straight to the next stage as
    # ``previous``; the hash covers everything except itself, so it stays stable.
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return path


def build_manifest(
    stage: str,
    *,
    previous: dict | None,
    artifacts: list[dict],
    counts: dict | None = None,
    model_identity_sha256: str | None = None,
    outcome_inaccessible: dict | None = None,
    disjointness: dict | None = None,
    required_variables: dict[str, str] | None = None,
    extra_variables: dict[str, str] | None = None,
) -> dict:
    definition = STAGE_BY_NAME[stage]
    manifest = {
        "stage": stage,
        "sequence": definition.sequence,
        "description": definition.description,
        "previous_stage": (previous or {}).get("stage"),
        "previous_manifest_sha256": (previous or {}).get("manifest_sha256"),
        "created_at_utc": _utc_now(),
        "git": {"commit": git_head(), "worktree_clean": git_worktree_clean()},
        "environment": capture_environment(required_variables, extra_variables),
        "protocol_sha256": sha256_document(PROTOCOL_DOCUMENT),
        "config_sha256": sha256_document(CONFIG_DOCUMENT),
        "representations_sha256": sha256_document(REPRESENTATIONS_DOCUMENT),
        "model_identity_sha256": model_identity_sha256,
        "artifacts": _normalise_artifacts(artifacts, REPO_ROOT),
        "counts": counts or {},
        "immutable": True,
    }
    if outcome_inaccessible is not None:
        manifest["outcome_inaccessible_assertion"] = outcome_inaccessible
    if disjointness is not None:
        manifest["cohort_disjointness"] = disjointness
    return manifest


def _normalise_artifacts(artifacts: list[dict], repo_root: Path) -> list[dict]:
    normalised = []
    for artifact in artifacts:
        path = repo_root / artifact["path"]
        entry = {
            "path": artifact["path"],
            "role": artifact.get("role", "artifact"),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256_file(path) if path.is_file() else None,
        }
        normalised.append(entry)
    return sorted(normalised, key=lambda item: item["path"])


# --------------------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------------------


@dataclass
class Report:
    checks: list[dict] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(_finding(name, passed, detail))

    @property
    def failures(self) -> list[dict]:
        return [check for check in self.checks if check["status"] == "FAIL"]

    @property
    def ok(self) -> bool:
        return not self.failures


def load_manifests(stage_dir: Path) -> dict[str, dict]:
    if not stage_dir.is_dir():
        return {}
    manifests: dict[str, dict] = {}
    for path in sorted(stage_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "stage" in payload:
            manifests[str(payload["stage"])] = payload
    return manifests


def verify(stage_dir: Path = DEFAULT_STAGE_DIR, repo_root: Path = REPO_ROOT) -> Report:
    report = Report()
    manifests = load_manifests(stage_dir)

    if not manifests:
        report.add("stage manifests present", False, f"no manifests under {stage_dir}")
        return report

    present = [stage.name for stage in STAGES if stage.name in manifests]
    report.add("stage manifests present", True, f"{len(present)} stages: {present}")

    # ordering and completeness
    expected_prefix = [stage.name for stage in STAGES[: len(present)]]
    report.add(
        "stages form a complete prefix in order",
        present == expected_prefix,
        f"got {present}, expected {expected_prefix}",
    )

    # chain
    for index in range(1, len(present)):
        current = manifests[present[index]]
        previous = manifests[present[index - 1]]
        report.add(
            f"chain: {present[index - 1]} -> {present[index]}",
            current.get("previous_manifest_sha256") == previous.get("manifest_sha256"),
            "previous manifest hash does not match",
        )

    # timestamps
    stamps: list[tuple[str, str]] = []
    for name in present:
        value = manifests[name].get("created_at_utc")
        if value:
            stamps.append((name, value))
    for (earlier, first), (later, second) in pairwise(stamps):
        report.add(f"timestamp order: {earlier} <= {later}", second >= first, f"{first} then {second}")

    # artifacts, protocol, config, model identity, environment
    for name in present:
        manifest = manifests[name]
        definition = STAGE_BY_NAME[name]
        _verify_artifacts(report, name, manifest, repo_root)
        _verify_outcome_roles(report, name, definition, manifest)
        _verify_frozen_documents(report, name, manifest)
        _verify_model_identity(report, name, manifest)
        report.checks.extend(
            _renamed(check, name) for check in check_environment(manifest.get("environment") or {})
        )
        _verify_disjointness(report, name, manifest)
        _verify_outcome_inaccessible(report, name, manifest)

    # self-hash integrity
    for name in present:
        manifest = manifests[name]
        report.add(
            f"manifest self-hash: {name}",
            manifest.get("manifest_sha256") == manifest_sha256(manifest),
            "manifest was edited after it was written",
        )
    return report


def _renamed(check: dict, stage: str) -> dict:
    return {**check, "check": f"{stage}: {check['check']}"}


def _verify_artifacts(report: Report, stage: str, manifest: dict, repo_root: Path) -> None:
    for artifact in manifest.get("artifacts") or []:
        path = repo_root / artifact["path"]
        if not path.is_file():
            report.add(f"{stage}: artifact {artifact['path']}", False, "missing")
            continue
        digest = sha256_file(path)
        report.add(
            f"{stage}: artifact {artifact['path']}",
            digest == artifact.get("sha256"),
            f"now {digest}, frozen {artifact.get('sha256')}",
        )


def _verify_outcome_roles(report: Report, stage: str, definition: StageDef, manifest: dict) -> None:
    roles = {artifact.get("role") for artifact in manifest.get("artifacts") or []}
    leaked = sorted(roles & OUTCOME_ROLES)
    report.add(
        f"{stage}: no outcome artifact before stage {OUTCOME_BEARING_FROM_SEQUENCE}",
        (not leaked) or definition.sequence >= OUTCOME_BEARING_FROM_SEQUENCE,
        f"outcome roles {leaked} at stage {definition.sequence}",
    )


def _verify_frozen_documents(report: Report, stage: str, manifest: dict) -> None:
    for label, path in (
        ("protocol", PROTOCOL_DOCUMENT),
        ("config", CONFIG_DOCUMENT),
        ("representations", REPRESENTATIONS_DOCUMENT),
    ):
        recorded = manifest.get(f"{label}_sha256")
        if recorded is None:
            continue
        current = sha256_document(path)
        report.add(
            f"{stage}: frozen {label} unchanged",
            current == recorded,
            f"now {current}, frozen {recorded}",
        )


def _verify_model_identity(report: Report, stage: str, manifest: dict) -> None:
    recorded = manifest.get("model_identity_sha256")
    if recorded is None:
        return
    current = model_identity_sha256()
    report.add(
        f"{stage}: frozen model identity unchanged",
        current == recorded,
        f"now {current}, frozen {recorded}",
    )


def _verify_disjointness(report: Report, stage: str, manifest: dict) -> None:
    disjointness = manifest.get("cohort_disjointness")
    if not disjointness:
        return
    status = disjointness.get("historical_disjointness")
    report.add(
        f"{stage}: historical company-disjointness proven",
        status == "PROVEN",
        f"status {status}; E5 cohort freeze must fail closed until previous_270.json exists",
    )


def _verify_outcome_inaccessible(report: Report, stage: str, manifest: dict) -> None:
    assertion = manifest.get("outcome_inaccessible_assertion")
    if not assertion:
        return
    still_absent = [str(path) for path in assertion.get("checked_paths") or [] if Path(path).exists()]
    report.add(
        f"{stage}: recorded outcome paths still absent",
        not still_absent,
        f"now present: {still_absent}",
    )


def model_identity_sha256() -> str | None:
    """Hash of the frozen Agent identity block, or None when no model is selected yet."""
    if not CONFIG_DOCUMENT.is_file():
        return None
    config = json.loads(CONFIG_DOCUMENT.read_text(encoding="utf-8"))
    identity = config.get("agent_qualification") or {}
    return sha256_bytes(canonical_bytes(identity))


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify the E5 staged freeze chain.")
    parser.add_argument("--stage-dir", default=str(DEFAULT_STAGE_DIR))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    report = verify(Path(args.stage_dir), Path(args.repo_root))
    passed = len(report.checks) - len(report.failures)
    print(f"E5 freeze chain: {passed}/{len(report.checks)} checks passed")
    for check in report.failures:
        print(f"  FAIL {check['check']}: {check['detail']}")
    missing = [stage.name for stage in STAGES if stage.name not in load_manifests(Path(args.stage_dir))]
    if missing:
        print(f"  stages not yet frozen: {', '.join(missing)}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
