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
    # `OPEN` is a legal target from `ACCEPTED` because `reopen_case` accepts an
    # accepted case and puts it back in the open queue. It used to assign
    # `case.status = OPEN` directly, so the table said one thing and the function
    # did another - two definitions of legality in one state machine. The table is
    # now the single authority and `reopen_case` delegates to it.
    RiskCaseStatus.ACCEPTED: {
        RiskCaseStatus.UNDER_REVIEW,
        RiskCaseStatus.CLOSED,
        RiskCaseStatus.OPEN,
    },
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


def add_mitigation_action(
    case: RiskCase, actor_id: str, description: str, owner_id: str, due_date: str
) -> dict:
    if not description.strip() or not owner_id.strip() or not due_date.strip():
        raise ValueError("description, owner and due date are required")
    action = {
        "id": f"action_{len(case.actions) + 1}",
        "description": description,
        "owner_id": owner_id,
        "due_date": due_date,
        "status": "open",
        "created_by": actor_id,
        "created_at": now_iso(),
    }
    case.actions.append(action)
    case.owner_id = owner_id
    case.due_date = due_date
    case.updated_at = action["created_at"]
    return action


def record_resolution_evidence(case: RiskCase, evidence_id: str) -> None:
    if not evidence_id.strip():
        raise ValueError("resolution evidence is required")
    if evidence_id not in case.resolution_evidence:
        case.resolution_evidence.append(evidence_id)
    case.updated_at = now_iso()


def reopen_case(case: RiskCase, actor_id: str, reason: str) -> dict:
    """Reopen a closed-out case, through the state machine.

    This used to assign `case.status = OPEN` directly, bypassing `TRANSITIONS`
    entirely. A case could therefore reach a state its own transition table
    forbade, and any consumer that trusted `TRANSITIONS` to describe reachability
    was wrong. Delegating makes the table the single authority; `ACCEPTED -> OPEN`
    is now declared there rather than performed behind its back.
    """
    if case.status not in {RiskCaseStatus.RESOLVED, RiskCaseStatus.ACCEPTED}:
        raise ValueError("only accepted or resolved cases can be reopened")
    if not reason.strip():
        raise ValueError("reopen reason is required")
    previous, _ = transition_case(case, RiskCaseStatus.OPEN)
    case.monitoring_state = "reopened"
    event = {"kind": "case_reopened", "actor_id": actor_id, "from": previous, "reason": reason, "timestamp": case.updated_at}
    case.comments.append(event)
    return event
