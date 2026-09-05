from __future__ import annotations

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
    for item in extracted:
        candidates.setdefault((item.fiscal_year, item.line_item), []).append(item)
        if item.fiscal_year == fiscal_year:
            sources.setdefault(item.line_item, []).append(
                Evidence(
                    item.document,
                    item.page,
                    item.source_text,
                    item.fiscal_year,
                    item.confidence,
                    False,
                    "located",
                )
            )
    prior_year = max(
        (year for year, _ in candidates if year < fiscal_year), default=None
    )
    for (candidate_year, key), items in candidates.items():
        if candidate_year not in {fiscal_year, prior_year}:
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
            target[key] = usable.pop()
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
        "review_required": True,
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
