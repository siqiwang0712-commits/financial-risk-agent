from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Protocol

from .domain import Evidence

# Version of the matching algorithm below. It is co-located with the code it
# describes so a change to the algorithm and the recorded version stay in sync.
# `orchestrator.component_versions` must reference this constant, never a copy.
VERIFIER_VERSION = "exact-page-quote:v1"

# "This number can be traced to a source location." `located` qualifies.
PROVENANCE_COVERED_STATUSES = frozenset({"located", "verified"})
# "This number may support a material conclusion." Only `verified` qualifies.
PROOF_COVERED_STATUSES = frozenset({"verified"})


class HasVerificationStatus(Protocol):
    verification_status: str


def coverage_ratio(
    refs: Iterable[HasVerificationStatus], allowed: frozenset[str]
) -> float:
    """Fraction of references whose status is in `allowed`; 0.0 when empty."""
    items = list(refs)
    if not items:
        return 0.0
    return sum(item.verification_status in allowed for item in items) / len(items)


class EvidenceVerifier:
    def verify(self, evidence: Evidence, page_texts: dict[int, str]) -> Evidence:
        source = " ".join(evidence.source_text.split())
        page = " ".join(page_texts.get(evidence.page, "").split())
        exact = bool(source) and source.casefold() in page.casefold()
        return replace(
            evidence,
            confidence=evidence.confidence if exact else min(evidence.confidence, 0.25),
            verified=exact,
            verification_status="verified" if exact else "unverified",
        )
