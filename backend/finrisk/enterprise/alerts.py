from __future__ import annotations


def _numeric(source: dict, key: str) -> float | None:
    """Read a numeric field, treating `None` as absent.

    `dict.get(key, default)` only falls back when the key is *absent*, and this
    codebase uses `None` for "missing". `current.get("severity", 0)` therefore
    returned `None` whenever a caller passed `{"severity": None}`, and every
    comparison below raised `TypeError`. Returning `None` here means "not
    comparable", which suppresses the alert -- the same outcome the old defaults
    produced for an absent key, without the crash.
    """
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def detect_alerts(current: dict, previous: dict | None = None) -> list[dict]:
    previous = previous or {}
    alerts: list[dict] = []
    if current.get("limit_breached"):
        alerts.append({"type": "LIMIT_BREACHED", "severity": "critical"})
    if current.get("tension") in {"Tension", "Material Contradiction"}:
        alerts.append({"type": "DISCLOSURE_TENSION", "severity": "high"})
    current_severity = _numeric(current, "severity")
    previous_severity = _numeric(previous, "severity")
    current_confidence = _numeric(current, "confidence")
    previous_confidence = _numeric(previous, "confidence")
    if (
        previous
        and current_severity is not None
        and previous_severity is not None
        and current_severity > previous_severity + 10
    ):
        alerts.append({"type": "RISK_WORSENING", "severity": "high"})
    if (
        previous
        and current_confidence is not None
        and previous_confidence is not None
        and current_confidence < previous_confidence - 0.15
    ):
        # `moderate` is the 5-band vocabulary from `severity.py`; the previous
        # `warning` was a sixth label that matched no other module.
        alerts.append({"type": "CONFIDENCE_DROPPED", "severity": "moderate"})
    if not previous and current_severity is not None and current_severity >= 60:
        alerts.append({"type": "NEW_RISK", "severity": "high"})
    return alerts
