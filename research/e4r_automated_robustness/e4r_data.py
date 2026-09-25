"""Source-adapter and integrity gate for the E4-R automated robustness study.

E4-R consumes exactly one published input: the E4-S replication packet in
``research/e4_statistical_audit/replication/``. Nothing here writes to, rewrites or
repairs that packet. The gate either passes or the study stops.

The gate performs, in order:

1. SHA-256 verification of every file listed in the replication ``manifest.json``;
2. SHA-256 verification of the frozen E4 artifact manifest (proving E4-R did not mutate E4);
3. an optional invocation of the existing E4-S verifier (``verify_audit.py --quick``);
4. reconstruction of B0/B6 from the packet's own metrics using the *frozen* scoring
   functions, checked against the published scores to 1e-9.

Step 4 is what lets the temporal ablation in :mod:`e4r_ablation` be trustworthy: it proves
the formula used for the ablations is the formula that produced the published B6 scores.

Evidence status emitted by this module is ``POST_HOC_AUTOMATED_ROBUSTNESS``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
E4S_DIR = REPO_ROOT / "research" / "e4_statistical_audit"
REPLICATION_DIR = E4S_DIR / "replication"

# `backend` holds the frozen scoring library; `E4S_DIR` holds the audit's independent
# statistical primitives, which E4-R reuses rather than re-implementing.
for _path in (str(REPO_ROOT / "backend"), str(E4S_DIR), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from finrisk.numeric_benchmark import (
    ratio_risk_score,
    temporal_risk_score,
)

STATUS = "POST_HOC_AUTOMATED_ROBUSTNESS"

# B6's temporal terms, confirmed programmatically from the frozen implementation rather
# than assumed. See `discover_b6_definition`.
B0_INPUTS = ("current_ratio", "debt_to_assets", "net_margin", "cfo_to_net_income", "fcf_margin")
B6_TEMPORAL_INPUTS = (
    "revenue_growth",
    "operating_cash_flow_growth",
    "total_debt_growth",
    "cash_growth",
)


class IntegrityError(RuntimeError):
    """Raised when the source packet cannot be trusted. E4-R must stop."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=1, sort_keys=True) + "\n"


def sha256_json(value: object) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


# --------------------------------------------------------------------------------------
# B6 definition discovery
# --------------------------------------------------------------------------------------


def _read_rules(function) -> list[dict]:
    """Extract ``(metric_name, comparator, threshold)`` triples from a frozen function.

    Both ``ratio_risk_score`` and ``temporal_risk_score`` drive a ``for name, test in (...)``
    loop over ``(metric, predicate)`` pairs. CPython stores those as code constants; on
    3.13 the nested tuples are flattened, so a metric name is the string immediately
    followed by the lambda's code object. Reading them out of the code object means the
    ablation cannot drift away from the frozen implementation it is supposed to mirror.
    """
    import dis

    constants = list(function.__code__.co_consts)
    rules: list[dict] = []
    for index, item in enumerate(constants):
        if not isinstance(item, str) or index + 1 >= len(constants):
            continue
        following = constants[index + 1]
        if not hasattr(following, "co_consts") or not hasattr(following, "co_code"):
            continue
        numbers = [
            value
            for value in following.co_consts
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        operators = [
            instruction.argrepr
            for instruction in dis.get_instructions(following)
            if "COMPARE" in instruction.opname
        ]
        rules.append(
            {
                "metric": item,
                "comparator": operators[0] if operators else None,
                "threshold": numbers[0] if numbers else None,
            }
        )
    return rules


def discover_b6_definition() -> dict:
    """Read B0/B6's inputs and thresholds out of the frozen code instead of assuming them."""
    base_rules = _read_rules(ratio_risk_score)
    temporal_rules = _read_rules(temporal_risk_score)
    base_names = tuple(rule["metric"] for rule in base_rules)
    temporal_names = tuple(rule["metric"] for rule in temporal_rules)
    return {
        "source": "backend/finrisk/numeric_benchmark.py",
        "b0_function": "ratio_risk_score",
        "b6_function": "temporal_risk_score",
        "b0_rules_from_code": base_rules,
        "b6_temporal_rules_from_code": temporal_rules,
        "b0_inputs_from_code": list(base_names),
        "b6_temporal_inputs_from_code": list(temporal_names),
        "b0_inputs_match_expected": list(base_names) == list(B0_INPUTS),
        "b6_temporal_inputs_match_expected": list(temporal_names) == list(B6_TEMPORAL_INPUTS),
        "b6_thresholds_from_code": {
            rule["metric"]: {"comparator": rule["comparator"], "threshold": rule["threshold"]}
            for rule in temporal_rules
        },
        "formula": "B6 = min(1, 0.75 * B0 + 0.25 * adverse/observed); B0 = mean of the "
        "static binary checks actually observed",
    }


# --------------------------------------------------------------------------------------
# Integrity gate
# --------------------------------------------------------------------------------------


@dataclass
class IntegrityReport:
    status: str = "PENDING"
    replication_files: list[dict] = field(default_factory=list)
    e4_frozen_files: list[dict] = field(default_factory=list)
    external_verifier: dict | None = None
    b0_reconstruction_max_abs_error: float | None = None
    b6_reconstruction_max_abs_error: float | None = None
    b0_reconstruction_mismatches: int | None = None
    b6_reconstruction_mismatches: int | None = None
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = {
            "status": self.status,
            "evidence_status": STATUS,
            "replication_manifest": "research/e4_statistical_audit/replication/manifest.json",
            "replication_files": self.replication_files,
            "e4_frozen_artifact_manifest": "research/e4_statistical_audit/e4_frozen_artifact_manifest.json",
            "e4_frozen_files": self.e4_frozen_files,
            "external_verifier": self.external_verifier,
            "b0_reconstruction": {
                "max_abs_error": self.b0_reconstruction_max_abs_error,
                "mismatches": self.b0_reconstruction_mismatches,
            },
            "b6_reconstruction": {
                "max_abs_error": self.b6_reconstruction_max_abs_error,
                "mismatches": self.b6_reconstruction_mismatches,
            },
            "failures": self.failures,
        }
        return payload


def _verify_manifest(manifest_path: Path, base: Path, label: str) -> tuple[list[dict], list[str]]:
    if not manifest_path.is_file():
        return [], [f"{label}: manifest missing at {manifest_path}"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if isinstance(entries, dict):
        entries = [{"path": key, "sha256": value} for key, value in entries.items()]
    results: list[dict] = []
    failures: list[str] = []
    for entry in entries:
        path = base / entry["path"]
        if not path.is_file():
            results.append({"path": entry["path"], "status": "MISSING"})
            failures.append(f"{label}: {entry['path']} is missing")
            continue
        observed = sha256_file(path)
        ok = observed == entry["sha256"]
        results.append(
            {
                "path": entry["path"],
                "status": "PASS" if ok else "FAIL",
                "sha256": observed,
                "expected_sha256": entry["sha256"],
                "bytes": path.stat().st_size,
            }
        )
        if not ok:
            failures.append(
                f"{label}: {entry['path']} hash mismatch (observed {observed[:12]}, expected {entry['sha256'][:12]})"
            )
    return results, failures


def run_external_verifier(scratch_out: Path, quick: bool = True) -> dict:
    """Invoke the existing E4-S verifier as a subprocess.

    The verifier's default output path is a *committed* E4-S artifact, so it is always
    redirected to a scratch location. That location sits outside the repository: the E4-R
    manifest already records the verifier's exit code and check counts, and a second copy
    rewritten on every run inside a directory whose bytes are hashed would only mislead.
    """
    command = [sys.executable, str(E4S_DIR / "verify_audit.py")]
    if quick:
        command.append("--quick")
    command += ["--out", str(scratch_out)]
    completed = __import__("subprocess").run(command, capture_output=True, text=True, cwd=str(REPO_ROOT))
    payload: dict = {
        "command": "verify_audit.py --quick --out <scratch>",
        "exit_code": completed.returncode,
    }
    if scratch_out.is_file():
        result = json.loads(scratch_out.read_text(encoding="utf-8"))
        checks = result.get("checks", [])
        payload["checks"] = len(checks)
        payload["passed"] = sum(1 for item in checks if item.get("status") == "PASS")
        payload["status"] = result.get("status")
        payload["failed_checks"] = [item["check"] for item in checks if item.get("status") != "PASS"]
    payload["stderr_tail"] = completed.stderr.strip().splitlines()[-5:]
    return payload


def verify_sources(run_external: bool = True, scratch_dir: Path | None = None) -> IntegrityReport:
    report = IntegrityReport()
    replication, failures = _verify_manifest(REPLICATION_DIR / "manifest.json", REPO_ROOT, "replication")
    report.replication_files = replication
    report.failures.extend(failures)

    e4_frozen, failures = _verify_manifest(
        E4S_DIR / "e4_frozen_artifact_manifest.json", REPO_ROOT, "e4-frozen"
    )
    report.e4_frozen_files = e4_frozen
    report.failures.extend(failures)

    if run_external:
        scratch_root = Path(scratch_dir) if scratch_dir else Path(tempfile.gettempdir())
        scratch_root.mkdir(parents=True, exist_ok=True)
        scratch = scratch_root / "e4r_e4s_verification_result.json"
        external = run_external_verifier(scratch)
        report.external_verifier = external
        if external.get("exit_code") != 0:
            report.failures.append(
                f"external E4-S verifier exited {external.get('exit_code')}: {external.get('failed_checks')}"
            )

    report.status = "PASS" if not report.failures else "FAIL"
    return report


# --------------------------------------------------------------------------------------
# Packet loading
# --------------------------------------------------------------------------------------


@dataclass
class Dataset:
    """The 675-observation analysis cohort, with everything E4-R needs pre-joined."""

    observation_ids: list[str]
    labels: dict[str, int]
    sector: dict[str, str]
    sic: dict[str, int]
    cik: dict[str, str]
    masked_company_id: dict[str, str]
    metrics: dict[str, dict[str, float | None]]
    current: dict[str, dict[str, float | None]]
    previous: dict[str, dict[str, float | None]]
    published_scores: dict[str, dict[str, float]]  # model_id -> observation_id -> score
    b0_recomputed: dict[str, float]
    b6_recomputed: dict[str, float]
    information_cutoff: dict[str, str]
    period_end: dict[str, str]
    previous_period: dict[str, str]
    outcome_available_at: dict[str, str]
    outcome_window_end: dict[str, str]
    provenance: dict[str, dict]
    metric_fields: list[str]

    @property
    def n(self) -> int:
        return len(self.observation_ids)

    @property
    def events(self) -> int:
        return sum(self.labels.values())

    def matrix(self, fields: list[str]) -> list[list[float]]:
        """Feature matrix with NaN for missing, in observation order."""
        return [
            [_as_float(self.metrics[oid].get(name)) for name in fields]
            for oid in self.observation_ids
        ]


def _as_float(value: object) -> float:
    if value is None or isinstance(value, bool):
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def load_packet() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    cohort = json.loads((REPLICATION_DIR / "cohort.json").read_text(encoding="utf-8"))
    with gzip.open(REPLICATION_DIR / "features.json.gz", "rt", encoding="utf-8") as handle:
        features = json.loads(handle.read())
    outcomes = json.loads((REPLICATION_DIR / "outcomes.json").read_text(encoding="utf-8"))
    analysis = json.loads((REPLICATION_DIR / "analysis.json").read_text(encoding="utf-8"))
    return cohort, features, outcomes, analysis


def build_dataset() -> Dataset:
    cohort, features, outcomes, analysis = load_packet()
    cohort_by_id = {row["observation_id"]: row for row in cohort}
    features_by_id = {row["observation_id"]: row for row in features}
    labels: dict[str, int] = {}
    outcome_meta: dict[str, dict] = {}
    for row in outcomes:
        if row.get("label_status") == "VERIFIED" and row.get("financial_deterioration_12m") in (0, 1):
            labels[row["observation_id"]] = int(row["financial_deterioration_12m"])
            outcome_meta[row["observation_id"]] = row
    observation_ids = sorted(labels)

    published: dict[str, dict[str, float]] = {}
    for row in analysis:
        published.setdefault(row["model_id"], {})[row["observation_id"]] = float(row["score"])

    b0_recomputed: dict[str, float] = {}
    b6_recomputed: dict[str, float] = {}
    for oid in observation_ids:
        metric_payload = features_by_id[oid]["metrics"]
        base = ratio_risk_score(metric_payload)
        temporal = temporal_risk_score(metric_payload)
        b0_recomputed[oid] = float("nan") if base is None else float(base)
        b6_recomputed[oid] = float("nan") if temporal is None else float(temporal)

    metric_fields = sorted({name for row in features for name in row["metrics"]})
    return Dataset(
        observation_ids=observation_ids,
        labels=labels,
        sector={oid: cohort_by_id[oid]["sector"] for oid in observation_ids},
        sic={oid: int(cohort_by_id[oid]["sic"]) for oid in observation_ids},
        cik={oid: str(cohort_by_id[oid]["cik"]) for oid in observation_ids},
        masked_company_id={oid: cohort_by_id[oid]["masked_company_id"] for oid in observation_ids},
        metrics={oid: features_by_id[oid]["metrics"] for oid in observation_ids},
        current={oid: features_by_id[oid]["current"] for oid in observation_ids},
        previous={oid: features_by_id[oid]["previous"] for oid in observation_ids},
        published_scores=published,
        b0_recomputed=b0_recomputed,
        b6_recomputed=b6_recomputed,
        information_cutoff={oid: features_by_id[oid]["information_cutoff"] for oid in observation_ids},
        period_end={oid: features_by_id[oid]["period_end"] for oid in observation_ids},
        previous_period={oid: str(cohort_by_id[oid]["previous_period"]) for oid in observation_ids},
        outcome_available_at={oid: str(outcome_meta[oid].get("outcome_available_at") or "") for oid in observation_ids},
        outcome_window_end={oid: features_by_id[oid]["outcome_window_end"] for oid in observation_ids},
        provenance={oid: features_by_id[oid].get("provenance", {}) for oid in observation_ids},
        metric_fields=metric_fields,
    )


def check_reconstruction(dataset: Dataset, tolerance: float = 1e-9) -> dict:
    """Confirm the recomputed B0/B6 equal the published scores (published are rounded)."""
    max_b0 = 0.0
    max_b6 = 0.0
    bad_b0 = 0
    bad_b6 = 0
    for oid in dataset.observation_ids:
        for model, recomputed, counter in (
            ("B0", dataset.b0_recomputed[oid], "b0"),
            ("B6", dataset.b6_recomputed[oid], "b6"),
        ):
            published = dataset.published_scores[model][oid]
            gap = abs(recomputed - published)
            if counter == "b0":
                max_b0 = max(max_b0, gap)
                bad_b0 += gap > tolerance
            else:
                max_b6 = max(max_b6, gap)
                bad_b6 += gap > tolerance
    return {
        "tolerance": tolerance,
        "b0_max_abs_error": max_b0,
        "b6_max_abs_error": max_b6,
        "b0_mismatches": bad_b0,
        "b6_mismatches": bad_b6,
        "observations": dataset.n,
        "published_score_rounding": "published scores carry 10 decimal places; tolerance 1e-9",
    }
