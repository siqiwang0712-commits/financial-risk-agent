from __future__ import annotations

from .domain import RiskCase, RiskCaseStatus, now_iso

TRANSITIONS = {
    RiskCaseStatus.DETECTED: {RiskCaseStatus.OPEN, RiskCaseStatus.CLOSED},
    RiskCaseStatus.OPEN: {RiskCaseStatus.UNDER_REVIEW, RiskCaseStatus.CLOSED},
    RiskCaseStatus.UNDER_REVIEW: {
        RiskCaseStatus.MITIGATING,
        RiskCaseStatus.ACCEPTED,
        RiskCaseStatus.RESOLVED,
    },
    RiskCaseStatus.MITIGATING: {RiskCaseStatus.UNDER_REVIEW, RiskCaseStatus.RESOLVED},
    RiskCaseStatus.ACCEPTED: {RiskCaseStatus.UNDER_REVIEW, RiskCaseStatus.CLOSED},
    RiskCaseStatus.RESOLVED: {RiskCaseStatus.CLOSED, RiskCaseStatus.OPEN},
    RiskCaseStatus.CLOSED: set(),
}


def transition_case(case: RiskCase, target: RiskCaseStatus) -> tuple[str, str]:
    previous = case.status
    if target not in TRANSITIONS[previous]:
        raise ValueError(f"invalid transition: {previous} -> {target}")
    case.status = target
    case.updated_at = now_iso()
    return previous, target


def record_override(
    case: RiskCase, actor_id: str, original: str, override: str, reason: str
) -> dict:
    if not reason.strip():
        raise ValueError("override reason is required")
    event = {
        "kind": "human_override",
        "actor_id": actor_id,
        "original_prediction": original,
        "override": override,
        "reason": reason,
        "timestamp": now_iso(),
    }
    case.comments.append(event)
    case.updated_at = event["timestamp"]
    return event
