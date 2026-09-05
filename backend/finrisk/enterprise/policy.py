from __future__ import annotations

from .domain import PolicyVersion


def evaluate_kri(policy: PolicyVersion, metrics: dict[str, float | None]) -> list[dict]:
    results = []
    for name, limits in policy.thresholds.items():
        value = metrics.get(name)
        warning = limits.get("warning")
        critical = limits.get("critical")
        direction = limits.get("risk_direction", "high")
        critical_hit = (
            value is not None
            and critical is not None
            and (value >= critical if direction == "high" else value <= critical)
        )
        warning_hit = (
            value is not None
            and warning is not None
            and (value >= warning if direction == "high" else value <= warning)
        )
        status = (
            "missing"
            if value is None
            else "critical"
            if critical_hit
            else "warning"
            if warning_hit
            else "within_appetite"
        )
        results.append(
            {
                "kri": name,
                "value": value,
                "status": status,
                "policy_id": policy.id,
                "policy_version": policy.version,
                "risk_direction": direction,
            }
        )
    return results
