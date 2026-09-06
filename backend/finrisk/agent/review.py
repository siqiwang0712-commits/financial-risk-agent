from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuredJudgement:
    claim: str
    risk_domain: str
    strength: str
    evidence_path_ids: tuple[str, ...]
    model: str | None = None


@dataclass(frozen=True)
class Challenge:
    code: str
    severity: str
    message: str


def critic(judgements: list[StructuredJudgement], valid_path_ids: set[str], applicability: dict[str, str]) -> list[Challenge]:
    challenges = []
    for item in judgements:
        if not item.evidence_path_ids or not set(item.evidence_path_ids) <= valid_path_ids:
            challenges.append(Challenge("UNSUPPORTED_CLAIM", "blocking", item.claim))
        if item.model and applicability.get(item.model) == "NOT_APPLICABLE":
            challenges.append(Challenge("MODEL_POPULATION_MISMATCH", "blocking", item.model))
        if any(term in item.claim.lower() for term in ("fraud proven", "certain bankruptcy", "guaranteed")):
            challenges.append(Challenge("OVERSTATED_CONCLUSION", "blocking", item.claim))
    return challenges


def deterministic_verifier(
    judgements: list[StructuredJudgement],
    challenges: list[Challenge],
    evidence_paths: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    citation_errors = []
    for item in judgements:
        for path_id in item.evidence_path_ids:
            path = evidence_paths.get(path_id)
            if path is None or path.get("evidence_path_status") not in {"VERIFIED", "LOCATED"}:
                citation_errors.append(path_id)
    blocking = [item for item in challenges if item.severity == "blocking"]
    return {
        "status": "REJECTED" if blocking or citation_errors else "VERIFIED",
        "citation_errors": sorted(set(citation_errors)),
        "challenges": [asdict(item) for item in challenges],
        "checked_claims": len(judgements),
    }


def three_role_review(
    judgements: list[StructuredJudgement],
    evidence_paths: dict[str, dict[str, Any]],
    applicability: dict[str, str] | None = None,
) -> dict[str, Any]:
    valid = {
        key
        for key, value in evidence_paths.items()
        if value.get("evidence_path_status") in {"VERIFIED", "LOCATED"}
    }
    challenges = critic(judgements, valid, applicability or {})
    verification = deterministic_verifier(judgements, challenges, evidence_paths)
    return {
        "analyst": [asdict(item) for item in judgements],
        "critic": [asdict(item) for item in challenges],
        "verifier": verification,
        "recommended_decision": "REVIEW" if verification["status"] == "REJECTED" else "UNCHANGED",
    }
