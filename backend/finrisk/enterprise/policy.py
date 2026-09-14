from __future__ import annotations

from .domain import PolicyVersion

RISK_DIRECTIONS = frozenset({"high", "low"})
_LIMIT_KEYS = ("warning", "critical")


def normalize_direction(value: object) -> str:
    """Validate a KRI's `risk_direction`, defaulting to `"high"`.

    Only `"high"` and `"low"` are meaningful. The comparison used to be
    `value >= critical if direction == "high" else value <= critical`, so any
    other string -- `"HIGH"`, `"higher_is_worse"`, a typo -- silently took the
    `<=` branch and a *breached* limit was reported as `within_appetite`. For a
    risk limit that is the wrong direction to fail in, so an unrecognised value
    is rejected instead.
    """
    if value is None:
        return "high"
    if not isinstance(value, str) or value.strip().lower() not in RISK_DIRECTIONS:
        raise ValueError(
            f"risk_direction must be one of {sorted(RISK_DIRECTIONS)}, got {value!r}"
        )
    return value.strip().lower()


def validate_thresholds(thresholds: object) -> None:
    """Reject a policy that `evaluate_kri` could not evaluate.

    `PolicyCreate.thresholds` accepted any mapping, so `{"debt": "abc"}` and
    `{"debt": {"warning": "abc"}}` were stored happily and then raised
    `TypeError` inside `evaluate_kri` -- an HTTP 500 on a request that should
    have been refused as invalid input. Called at policy-creation time so a
    malformed policy can never be persisted.

    `ValueError` (not `TypeError`) is deliberate: this runs inside a Pydantic
    `field_validator`, which only converts `ValueError`/`AssertionError` into a
    validation error. A `TypeError` would escape as a 500 instead of a 422.
    """
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object keyed by KRI name")  # noqa: TRY004
    for name, limits in thresholds.items():
        if not isinstance(limits, dict):
            raise ValueError(f"{name}: limits must be an object")  # noqa: TRY004
        normalize_direction(limits.get("risk_direction"))
        for bound in _LIMIT_KEYS:
            value = limits.get(bound)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name}.{bound} must be a number or null")  # noqa: TRY004


def evaluate_kri(policy: PolicyVersion, metrics: dict[str, float | None]) -> list[dict]:
    results = []
    for name, limits in policy.thresholds.items():
        value = metrics.get(name)
        warning = limits.get("warning")
        critical = limits.get("critical")
        direction = normalize_direction(limits.get("risk_direction"))
        high_is_worse = direction == "high"
        critical_hit = (
            value is not None
            and critical is not None
            and (value >= critical if high_is_worse else value <= critical)
        )
        warning_hit = (
            value is not None
            and warning is not None
            and (value >= warning if high_is_worse else value <= warning)
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
