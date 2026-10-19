from __future__ import annotations

from typing import Any

from ..enterprise.decision_bundle import (
    DecisionBundle,
    verify_decision_bundle,
)

DecisionCertificate = DecisionBundle


def verify_decision_certificate(
    value: DecisionBundle | dict[str, Any], policy=None
) -> bool:
    try:
        certificate = value if isinstance(value, DecisionBundle) else DecisionBundle(**value)
    except (TypeError, ValueError):
        return False
    try:
        if (certificate.certificate_version != "decision-certificate-v0.4"
                or not certificate.certificate_hash):
            return False
        return verify_decision_bundle(certificate, policy)
    except (TypeError, ValueError, AttributeError):
        return False
