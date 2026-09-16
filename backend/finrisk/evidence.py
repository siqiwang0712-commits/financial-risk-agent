from __future__ import annotations

import re
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


# Terms too common to distinguish one claim from another.
_CLAIM_STOPWORDS = frozenset({
    "that", "this", "with", "from", "have", "will", "been", "were", "they", "their",
    "which", "there", "these", "those", "into", "over", "such", "also", "than",
    "then", "when", "what", "while", "would", "could", "should", "about", "after",
    "before", "under", "other", "some", "more", "most", "only", "very", "each",
    "because", "however", "therefore", "company", "issuer", "financial",
})


def _claim_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) >= 4 and token not in _CLAIM_STOPWORDS
    }


def claim_is_grounded(claim_text: str, evidence_text: str, page_text: str = "") -> bool:
    """True when a claim's distinctive terms actually appear in the text it cites.

    Only `evidence_text` was ever checked against the page, so a `claim` (3-500
    characters of free text) could assert anything at all: an injected pair of
    matching `risk_category`/`polarity` values was enough to fire a +30
    going-concern rule. This requires genuine lexical overlap between the claim and
    the cited evidence before the claim is admitted.
    """
    terms = _claim_terms(claim_text)
    if not terms:
        return False
    # The page is accepted for API compatibility but deliberately excluded: a
    # nearby, unrelated paragraph cannot ground the cited evidence span.
    haystack = evidence_text.casefold()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms) >= 0.6
