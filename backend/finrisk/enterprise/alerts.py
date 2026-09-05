from __future__ import annotations


def detect_alerts(current: dict, previous: dict | None = None) -> list[dict]:
    previous = previous or {}
    alerts: list[dict] = []
    if current.get("limit_breached"):
        alerts.append({"type": "LIMIT_BREACHED", "severity": "critical"})
    if current.get("tension") in {"Tension", "Material Contradiction"}:
        alerts.append({"type": "DISCLOSURE_TENSION", "severity": "high"})
    if previous and current.get("severity", 0) > previous.get("severity", 0) + 10:
        alerts.append({"type": "RISK_WORSENING", "severity": "high"})
    if previous and current.get("confidence", 1) < previous.get("confidence", 1) - 0.15:
        alerts.append({"type": "CONFIDENCE_DROPPED", "severity": "warning"})
    if not previous and current.get("severity", 0) >= 60:
        alerts.append({"type": "NEW_RISK", "severity": "high"})
    return alerts
