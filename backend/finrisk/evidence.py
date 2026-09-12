from __future__ import annotations

from dataclasses import replace

from .domain import Evidence


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
