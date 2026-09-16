from __future__ import annotations

import math
from pathlib import Path

from ..domain import Evidence
from ..parser import DocumentParser
from ..xbrl import parse_companyfacts, values_by_year


def ingest_pdf(path: Path, document: str, fiscal_year: int) -> dict:
    parser = DocumentParser()
    pages = parser.extract_pages(path)
    if len(pages) > 500:
        raise ValueError("PDF exceeds the 500-page analysis limit")
    extracted = parser.extract_values(pages, document, fiscal_year)
    if not extracted:
        raise ValueError(
            "No reliable financial line items were extracted; manual review is required"
        )
    current, previous, sources, candidates, review_issues = {}, {}, {}, {}, []
    selected_verification: list[bool] = []
    for item in extracted:
        candidates.setdefault((item.fiscal_year, item.line_item), []).append(item)
    prior_year = max(
        (year for year, _ in candidates if year < fiscal_year), default=None
    )
    # The deterministic trend / forensic models require consecutive periods.
    # Retain the actual comparative year in provenance but do not silently treat
    # (for example) FY2022 as FY2024's "previous" input.
    comparable_prior_year = prior_year if prior_year == fiscal_year - 1 else None
    for (candidate_year, key), items in candidates.items():
        if candidate_year not in {fiscal_year, comparable_prior_year}:
            continue
        ranked = sorted(
            items,
            key=lambda item: (
                item.restated,
                item.statement != "unknown",
                item.confidence,
            ),
            reverse=True,
        )
        rank = (
            ranked[0].restated,
            ranked[0].statement != "unknown",
            ranked[0].confidence,
        )
        usable = {
            item.value
            for item in ranked
            if (item.restated, item.statement != "unknown", item.confidence) == rank
            and item.value is not None
        }
        target = current if candidate_year == fiscal_year else previous
        if len(usable) == 1:
            selected_value = usable.pop()
            target[key] = selected_value
            selected = next(item for item in ranked if item.value == selected_value)
            source_page = " ".join(pages.get(selected.page, "").split()).casefold()
            source_row = " ".join(selected.source_text.split()).casefold()
            # Numeric proof requires more than merely locating a page. The row
            # must reconcile exactly to the extracted page, belong to a known
            # statement, carry a finite value, and be the sole top-ranked value
            # for this line item/year. Ambiguous candidates remain `located` and
            # therefore cannot satisfy the proof gate.
            verified = (
                bool(source_row)
                and source_row in source_page
                and selected.statement != "unknown"
                and selected.value is not None
                and math.isfinite(selected.value)
            )
            selected_verification.append(verified)
            # Evidence is recorded for the prior year as well. Every `*_growth` /
            # `*_change` reference resolves `(key, fiscal_year - 1)` against this
            # map, so only building the current year left those refs permanently
            # empty and `complete_refs` always returned [].
            # `value`/`unit` are carried through instead of being dropped, so the
            # evidence carries the amount and currency it was read from.
            sources.setdefault(key, []).append(
                Evidence(
                    selected.document,
                    selected.page,
                    selected.source_text,
                    selected.fiscal_year,
                    selected.confidence,
                    verified,
                    "verified" if verified else "located",
                    value=selected.value,
                    unit=selected.currency,
                )
            )
        elif len(usable) > 1:
            review_issues.append(
                {
                    "line_item": key,
                    "fiscal_year": candidate_year,
                    "reason": "conflicting top-ranked candidates",
                    "values": sorted(usable),
                }
            )
    if not current:
        raise ValueError(
            "No unambiguous values were available for the requested fiscal year"
        )
    extraction = {
        "candidate_count": len(extracted),
        "prior_year": prior_year,
        "previous_year": comparable_prior_year,
        "previous_is_consecutive": comparable_prior_year is not None,
        "review_required": bool(review_issues) or not all(selected_verification),
        "review_issues": review_issues,
        "sections": parser.identify_sections(pages),
    }
    return {
        "pages": pages,
        "current": current,
        "previous": previous or None,
        "source_map": sources,
        "extraction": extraction,
    }


def ingest_xbrl(companyfacts: dict, fiscal_years: list[int] | None = None) -> dict:
    values = parse_companyfacts(companyfacts, fiscal_years)
    return {"values": values, "by_year": values_by_year(values)}
