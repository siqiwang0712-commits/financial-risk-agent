from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from .sec_bulk import CONCEPT_ALIASES, INSTANT_FIELDS

FIELD_STATEMENTS: dict[str, set[str]] = {
    "revenue": {"IS"},
    "net_income": {"IS"},
    "gross_profit": {"IS"},
    "operating_income": {"IS"},
    "interest_expense": {"IS"},
    "operating_cash_flow": {"CF"},
    "capital_expenditure": {"CF"},
}


def _rows(archive: zipfile.ZipFile, member: str) -> Iterator[dict[str, str]]:
    with archive.open(member) as raw, io.TextIOWrapper(
        raw, encoding="utf-8-sig", errors="replace", newline=""
    ) as text:
        yield from csv.DictReader(text, delimiter="\t")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pre_num_reference_rows(
    paths: Iterable[Path], accessions: set[str]
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]]]:
    """Read only presentation and numeric rows needed by the frozen observations.

    This is deliberately separate from ``load_statement_archives`` so reference
    construction does not reuse the evaluated fact-selection function.
    """
    presentations: list[dict[str, str]] = []
    numbers: list[dict[str, str]] = []
    sources: list[dict[str, Any]] = []
    remaining = set(accessions)
    for path in sorted(paths):
        with zipfile.ZipFile(path) as archive:
            names = {name.lower(): name for name in archive.namelist()}
            missing = {"pre.txt", "num.txt"} - names.keys()
            if missing:
                raise ValueError(f"{path.name} lacks reference members {sorted(missing)}")
            archive_pre = [row for row in _rows(archive, names["pre.txt"]) if row.get("adsh") in remaining]
            found = {row["adsh"] for row in archive_pre}
            if found:
                presentations.extend(archive_pre)
                numbers.extend(row for row in _rows(archive, names["num.txt"]) if row.get("adsh") in found)
                remaining -= found
        sources.append(
            {
                "archive_name": path.name,
                "sha256": _file_sha256(path),
                "source_type": "SEC_FSDS_PRE_NUM_REFERENCE",
            }
        )
    return presentations, numbers, sources


def _line(row: dict[str, str]) -> int:
    try:
        return int(row.get("line", ""))
    except ValueError:
        return 2**31 - 1


def construct_pre_num_reference(
    observations: list[dict[str, Any]],
    presentations: list[dict[str, str]],
    numbers: list[dict[str, str]],
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Construct an auditable machine reference via SEC presentation reconciliation.

    The output is *not* human-adjudicated extraction gold.  ``review_status`` is
    therefore ``reference_constructed`` and downstream gold metrics must exclude it.
    """
    pre_by_adsh: dict[str, list[dict[str, str]]] = {}
    num_by_adsh: dict[str, list[dict[str, str]]] = {}
    for row in presentations:
        pre_by_adsh.setdefault(row.get("adsh", ""), []).append(row)
    for row in numbers:
        num_by_adsh.setdefault(row.get("adsh", ""), []).append(row)

    output: list[dict[str, Any]] = []
    for observation in observations:
        adsh = str(observation["accession"])
        period = str(observation["period_end"]).replace("-", "")
        for field, aliases in CONCEPT_ALIASES.items():
            expected = FIELD_STATEMENTS.get(field, {"BS"})
            candidates = [
                row for row in pre_by_adsh.get(adsh, [])
                if row.get("tag") in aliases and row.get("stmt") in expected
            ]
            candidates.sort(key=lambda row: (aliases.index(row["tag"]), _line(row), row.get("report", "")))
            base = {
                "observation_id": observation["observation_id"],
                "field": field,
                "gold_value": None,
                "gold_unit": None,
                "gold_fiscal_year": observation["fiscal_year"],
                "gold_source": "SEC_FSDS_PRE_NUM_RECONCILIATION",
                "review_status": "reference_constructed",
                "predicted_value": observation.get("facts", {}).get(field),
                "predicted_unit": "USD" if observation.get("facts", {}).get(field) is not None else None,
                "predicted_fiscal_year": observation["fiscal_year"],
                "accession": adsh,
                "period_end": observation["period_end"],
            }
            if not candidates:
                output.append({**base, "reference_status": "MISSING_PRESENTATION", "validation_status": "MANUAL_REVIEW_REQUIRED"})
                continue
            selected_pre = candidates[0]
            qtrs = {"0", ""} if field in INSTANT_FIELDS else {"4", "", "0"}
            matches = [
                row for row in num_by_adsh.get(adsh, [])
                if row.get("tag") == selected_pre.get("tag")
                and row.get("version") == selected_pre.get("version")
                and row.get("ddate") == period
                and row.get("qtrs") in qtrs
                and row.get("uom") == "USD"
                and not (row.get("coreg") or "").strip()
                and not (row.get("segments") or "").strip()
            ]
            values: set[float] = set()
            for row in matches:
                try:
                    values.add(float(row["value"]))
                except (KeyError, TypeError, ValueError):
                    pass
            locator = {
                "pre": {key: selected_pre.get(key) for key in ("report", "line", "stmt", "tag", "version", "plabel", "negating")},
                "num_match_count": len(matches),
            }
            if len(values) != 1:
                status = "MISSING_NUMBER" if not values else "AMBIGUOUS_NUMBER"
                output.append({**base, "reference_status": status, "validation_status": "MANUAL_REVIEW_REQUIRED", "evidence_locator": locator})
                continue
            value = next(iter(values))
            reference = {
                **base,
                "gold_value": value,
                "gold_unit": "USD",
                "reference_status": "RECONCILED_UNAMBIGUOUS",
                "evidence_locator": locator,
                "validation_status": "MACHINE_AGREEMENT" if base["predicted_value"] == value else "MANUAL_REVIEW_REQUIRED",
            }
            predicted_concept = (observation.get("fact_provenance", {}).get(field) or {}).get("concept")
            reference["construct_comparison"] = {
                "predicted_concept": predicted_concept,
                "reference_concept": selected_pre.get("tag"),
                "exact_concept_match": predicted_concept == selected_pre.get("tag"),
                "equivalent_value": base["predicted_value"] == value,
            }
            if base["predicted_value"] != value:
                reference["mismatch_reason"] = "CONSTRUCT_OR_TAXONOMY_SCOPE_REQUIRES_MANUAL_ADJUDICATION"
            reference["evidence_hash"] = hashlib.sha256(
                json.dumps(reference, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            output.append(reference)

    reconciled = [row for row in output if row["reference_status"] == "RECONCILED_UNAMBIGUOUS"]
    comparable = [row for row in reconciled if row["predicted_value"] is not None]
    matches = sum(row["predicted_value"] == row["gold_value"] for row in comparable)
    status_counts = Counter(row["reference_status"] for row in output)
    validation_counts = Counter(row["validation_status"] for row in output)
    report = {
        "status": "MACHINE_REFERENCE_CONSTRUCTED" if reconciled else "NOT_AVAILABLE",
        "independent_human_gold_status": "NOT_ADJUDICATED",
        "observation_count": len(observations),
        "field_rows": len(output),
        "reconciled_fields": len(reconciled),
        "comparable_fields": len(comparable),
        "agreement_count": matches,
        "agreement_rate": matches / len(comparable) if comparable else None,
        "metric_name": "machine_reconciliation_agreement",
        "verified_reference_fields": 0,
        "machine_agreement_fields": validation_counts["MACHINE_AGREEMENT"],
        "manual_review_required_fields": validation_counts["MANUAL_REVIEW_REQUIRED"],
        "reference_status_counts": dict(sorted(status_counts.items())),
        "validation_status_counts": dict(sorted(validation_counts.items())),
        "reference_hash": hashlib.sha256(
            json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "source_hashes": [source["sha256"] for source in sources],
        "warning": "Presentation-to-number reconciliation is a machine reference, not independent human-adjudicated gold.",
    }
    return output, report
