from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from ..enterprise.decision import canonical_hash
from .domain import (
    DistributionValidity,
    DistributionValidityState,
    FinancialFeatureVector,
    ReportingObservabilityVector,
)


@dataclass(frozen=True)
class ReferenceProfile:
    name: str
    version: str
    scope: str = "UNSPECIFIED"
    source_cohort_identity: str | None = None
    source_commit: str | None = None
    artifact_hash: str | None = None
    feature_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    allowed_sectors: tuple[str, ...] = ()
    required_features: tuple[str, ...] = ()
    minimum_reporting_availability: float | None = None
    maximum_outside_fraction: float = 0.1


def load_reference_profile(path: Path) -> ReferenceProfile:
    """Load and integrity-check a frozen development/validation reference artifact."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded_hash = payload.pop("artifact_hash", None)
    if not isinstance(recorded_hash, str) or canonical_hash(payload) != recorded_hash:
        raise ValueError("reference profile artifact hash verification failed")
    if payload.get("scope") not in {
        "DEVELOPMENT_REFERENCE_ONLY",
        "VALIDATED_EXTERNAL",
    }:
        raise ValueError("reference profile scope is missing or unsupported")
    bounds = {
        name: (float(values[0]), float(values[1]))
        for name, values in payload.get("feature_bounds", {}).items()
    }
    return ReferenceProfile(
        name=payload["name"],
        version=payload["version"],
        scope=payload["scope"],
        source_cohort_identity=payload.get("source_cohort_identity"),
        source_commit=payload.get("source_commit"),
        artifact_hash=recorded_hash,
        feature_bounds=bounds,
        allowed_sectors=tuple(payload.get("allowed_sectors", ())),
        required_features=tuple(payload.get("required_features", ())),
        minimum_reporting_availability=payload.get(
            "minimum_reporting_availability"
        ),
        maximum_outside_fraction=float(
            payload.get("maximum_outside_fraction", 0.1)
        ),
    )


def separate_financial_and_reporting_features(
    values: dict[str, object], expected_features: set[str]
) -> tuple[FinancialFeatureVector, ReportingObservabilityVector]:
    """Split values from availability so missingness cannot raise risk severity."""

    financial = {
        key: (
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )
        for key, value in values.items()
    }
    observability = {
        key: values.get(key) is not None for key in sorted(expected_features | set(values))
    }
    return FinancialFeatureVector(financial), ReportingObservabilityVector(observability)


def assess_distribution_validity(
    financial: FinancialFeatureVector,
    observability: ReportingObservabilityVector,
    sector: str | None,
    reference: ReferenceProfile | None,
) -> DistributionValidity:
    availability = observability.availability_rate
    if reference is None:
        return DistributionValidity(
            DistributionValidityState.UNKNOWN,
            None,
            None,
            None,
            0,
            0,
            availability,
            ("No frozen development or validation reference profile was supplied.",),
        )
    diagnostics: list[str] = []
    evaluated = 0
    outside = 0
    for name, (lower, upper) in sorted(reference.feature_bounds.items()):
        value = financial.values.get(name)
        if value is None:
            continue
        evaluated += 1
        if not math.isfinite(value) or value < lower or value > upper:
            outside += 1
            diagnostics.append(f"{name} lies outside the frozen reference bounds")
    missing_required = sorted(
        name
        for name in reference.required_features
        if financial.values.get(name) is None
    )
    if missing_required:
        diagnostics.append(
            f"{len(missing_required)} required reference feature(s) are unavailable"
        )
    sector_outside = bool(
        reference.allowed_sectors
        and (sector or "").casefold()
        not in {value.casefold() for value in reference.allowed_sectors}
    )
    if sector_outside:
        diagnostics.append("sector is outside the frozen reference population")
    availability_outside = bool(
        reference.minimum_reporting_availability is not None
        and availability is not None
        and availability < reference.minimum_reporting_availability
    )
    if availability_outside:
        diagnostics.append("reporting availability is below the reference floor")
    outside_fraction = outside / evaluated if evaluated else 0.0
    if sector_outside or outside_fraction > reference.maximum_outside_fraction:
        state = DistributionValidityState.OUTSIDE_REFERENCE
    elif availability_outside or outside or missing_required:
        state = DistributionValidityState.WARNING
    elif not evaluated and reference.feature_bounds:
        state = DistributionValidityState.UNKNOWN
        diagnostics.append("No reference feature could be evaluated.")
    else:
        state = DistributionValidityState.IN_REFERENCE
    return DistributionValidity(
        state,
        reference.name,
        reference.version,
        reference.scope,
        evaluated,
        outside,
        availability,
        tuple(diagnostics),
    )
