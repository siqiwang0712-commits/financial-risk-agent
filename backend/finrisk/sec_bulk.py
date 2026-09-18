from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import os
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .metrics import calculate_metrics

# Frozen registry identifiers. Values are SEC CIKs, not locally invented IDs.
FROZEN_CIKS = {
    "AAPL": "0000320193", "MSFT": "0000789019", "INTC": "0000050863",
    "F": "0000037996", "GM": "0001467858", "DAL": "0000027904",
    "LUV": "0000092380", "WMT": "0000104169", "TGT": "0000027419",
    "WBA": "0001618921", "PFE": "0000078003", "JNJ": "0000200406",
    "CVX": "0000093410", "OXY": "0000797468", "NEE": "0000753308",
    "AEP": "0000004904", "CAT": "0000018230", "BA": "0000012927",
    "UPS": "0001090727", "FDX": "0001048911", "KO": "0000021344",
    "KHC": "0001637459", "DIS": "0001744489", "NFLX": "0001065280",
    "VZ": "0000732712", "TMUS": "0001283699", "AMT": "0001053507",
    "PLD": "0001045609", "NUE": "0000073309", "FCX": "0000831259",
}


CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditure": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForAdditionsToPropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ),
    "shareholder_equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "accounts_receivable": ("AccountsReceivableNetCurrent", "AccountsNotesAndLoansReceivableNetCurrent"),
    "inventory": ("InventoryNet",),
    "short_term_debt": ("ShortTermBorrowings", "LongTermDebtCurrent", "DebtCurrent"),
    "long_term_debt": ("LongTermDebtNoncurrent",),
    "total_debt": ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "interest_expense": ("InterestExpenseNonOperating", "InterestAndDebtExpense"),
}

INSTANT_FIELDS = {
    "total_assets", "total_liabilities", "current_assets", "current_liabilities", "cash",
    "shareholder_equity", "accounts_receivable", "inventory", "short_term_debt",
    "long_term_debt", "total_debt",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def add_twelve_months(value: datetime) -> datetime:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:  # February 29
        return value.replace(year=value.year + 1, day=28)


# A zip member declares its uncompressed size in the central directory, so the
# extraction budget can be checked *before* `archive.read` allocates. Without it a
# crafted archive (a zip bomb) exhausts memory. These archives are operator-supplied
# rather than API input, so this is defence in depth.
#
# The previous ceiling was 2 GiB, which is not a defence at all: the API container is
# capped at 1 GiB, so a member anywhere near that limit killed the process before the
# check could matter. The default is now a size a single worker can actually hold, and
# it is configurable for operators who legitimately need larger members. Because the
# declaration itself is attacker-controlled, the read is *also* streamed and aborted
# the moment the real decompressed length crosses the budget, so a lying central
# directory cannot force the allocation either.
DEFAULT_MAX_ARCHIVE_MEMBER_BYTES = 256 * 1024 * 1024

# Compression-ratio sanity bound. A member that claims to expand by more than this
# multiple is treated as hostile. Real SEC statement data is repetitive numeric TSV and
# measures around 21:1 (`num.txt`), so the bound leaves roughly 50x of headroom while
# still catching a classic single-member zip bomb. Overridable, never a substitute for
# the byte budget — it is only a second signal on top of it.
DEFAULT_MAX_ARCHIVE_COMPRESSION_RATIO = 1_000

_READ_CHUNK_BYTES = 1 << 20


def max_archive_member_bytes() -> int:
    """Per-member decompression budget, in bytes (`FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES`)."""
    return _positive_int_env(
        "FINRISK_SEC_MAX_ARCHIVE_MEMBER_BYTES", DEFAULT_MAX_ARCHIVE_MEMBER_BYTES
    )


def max_archive_compression_ratio() -> int:
    """Per-member expansion bound (`FINRISK_SEC_MAX_ARCHIVE_COMPRESSION_RATIO`)."""
    return _positive_int_env(
        "FINRISK_SEC_MAX_ARCHIVE_COMPRESSION_RATIO", DEFAULT_MAX_ARCHIVE_COMPRESSION_RATIO
    )


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _checked_member(archive: zipfile.ZipFile, name: str) -> bytes:
    limit = max_archive_member_bytes()
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError(
            f"archive member exceeds the extraction limit: {name} ({info.file_size} bytes)"
        )
    ratio_limit = max_archive_compression_ratio()
    if info.compress_size > 0 and info.file_size > info.compress_size * ratio_limit:
        raise ValueError(f"archive member has an implausible compression ratio: {name}")
    # Stream rather than `archive.read`: the declared size is unverified until the
    # decompressor has actually produced the bytes, so allocation is bounded by the
    # real length instead of by the header.
    chunks: list[bytes] = []
    total = 0
    with archive.open(name) as member:
        while True:
            chunk = member.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError(
                    f"archive member exceeded the extraction limit while reading: {name}"
                )
            chunks.append(chunk)
    return b"".join(chunks)


def _read_tsv(
    archive: zipfile.ZipFile, name: str, predicate: Any | None = None
) -> list[dict[str, str]]:
    raw = _checked_member(archive, name).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    return [row for row in reader if predicate is None or predicate(row)]


def load_statement_archives(
    paths: Iterable[Path], target_ciks: set[str] | None = None
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]]]:
    submissions: list[dict[str, str]] = []
    numbers: list[dict[str, str]] = []
    sources: list[dict[str, Any]] = []
    for path in sorted(paths):
        payload = path.read_bytes()
        archive_hash = sha256_bytes(payload)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = {name.lower(): name for name in archive.namelist()}
            if "sub.txt" not in names or "num.txt" not in names:
                raise ValueError(f"{path.name} is not an SEC Financial Statement Data Set archive")
            archive_submissions = _read_tsv(archive, names["sub.txt"])
            if target_ciks is not None:
                normalized = {cik.lstrip("0") or "0" for cik in target_ciks}
                archive_submissions = [
                    row for row in archive_submissions
                    if (str(row.get("cik", "")).lstrip("0") or "0") in normalized
                ]
            for row in archive_submissions:
                row["__archive_sha256"] = archive_hash
                row["__archive_name"] = path.name
            submissions.extend(archive_submissions)
            relevant_adsh = {row.get("adsh", "") for row in archive_submissions}
            numbers.extend(
                _read_tsv(
                    archive, names["num.txt"],
                    lambda row, accessions=relevant_adsh: row.get("adsh") in accessions,
                )
            )
        sources.append({
            "archive_name": path.name, "sha256": archive_hash, "bytes": len(payload),
            "source_type": "SEC_FINANCIAL_STATEMENT_DATA_SET",
        })
    return submissions, numbers, sources


def load_companyfacts_archive(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payload = path.read_bytes()
    companies: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            if not name.lower().endswith(".json"):
                continue
            raw = _checked_member(archive, name)
            data = json.loads(raw)
            cik = str(data.get("cik", "")).zfill(10)
            companies[cik] = {"data": data, "member": name, "member_sha256": sha256_bytes(raw)}
    return companies, {
        "archive_name": path.name, "sha256": sha256_bytes(payload), "bytes": len(payload),
        "source_type": "SEC_COMPANYFACTS_BULK", "member_count": len(companies),
    }


def _companyfact_candidates(data: dict[str, Any], field: str, fiscal_year: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    gaap = data.get("facts", {}).get("us-gaap", {})
    for priority, concept in enumerate(CONCEPT_ALIASES[field]):
        for unit, values in gaap.get(concept, {}).get("units", {}).items():
            if unit != "USD":
                continue
            for value in values:
                if value.get("form") != "10-K" or value.get("fy") != fiscal_year or value.get("fp") != "FY":
                    continue
                if field in INSTANT_FIELDS and value.get("frame") and not str(value["frame"]).endswith("I"):
                    continue
                out.append({**value, "concept": concept, "priority": priority, "unit": unit})
    return out


def build_companyfacts_corpus(
    plan: list[dict[str, str]], companies: dict[str, dict[str, Any]], source: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    missing: list[str] = []
    for planned in plan:
        cik = FROZEN_CIKS[planned["ticker"]]
        packaged = companies.get(cik)
        if not packaged:
            missing.append(planned["observation_id"])
            continue
        data = packaged["data"]
        fiscal_year = int(planned["fiscal_year"])
        anchor = _companyfact_candidates(data, "revenue", fiscal_year)
        if not anchor:
            anchor = _companyfact_candidates(data, "total_assets", fiscal_year)
        if not anchor:
            missing.append(planned["observation_id"])
            continue
        anchor.sort(key=lambda row: (row.get("filed", ""), row["priority"], row.get("accn", "")))
        filing = anchor[0]
        accession = filing["accn"]
        period = filing["end"]
        facts: dict[str, float | None] = {}
        provenance: dict[str, Any] = {}
        for field in CONCEPT_ALIASES:
            candidates = [row for row in _companyfact_candidates(data, field, fiscal_year) if row.get("accn") == accession and row.get("end") == period]
            candidates.sort(key=lambda row: (row["priority"], row.get("filed", "")))
            selected = candidates[0] if candidates else None
            facts[field] = float(selected["val"]) if selected and selected.get("val") is not None else None
            provenance[field] = None if not selected else {
                "concept": selected["concept"], "period_start": selected.get("start"), "period_end": selected["end"],
                "unit": selected["unit"], "accession": selected["accn"], "filed": selected["filed"],
                "source_row": {
                    "adsh": selected["accn"], "tag": selected["concept"],
                    "ddate": str(selected["end"]).replace("-", ""),
                    "uom": selected["unit"],
                    "coreg": "", "segments": "",
                },
            }
        if (
            facts["total_debt"] is None
            and facts["short_term_debt"] is not None
            and facts["long_term_debt"] is not None
        ):
            facts["total_debt"] = facts["short_term_debt"] + facts["long_term_debt"]
            provenance["total_debt"] = {
                "derived_from": ["short_term_debt", "long_term_debt"],
                "formula": "short_term_debt + long_term_debt",
            }
        filed = filing["filed"]
        available = f"{filed}T23:59:59Z"  # conservative when bulk CompanyFacts omits acceptance time
        base = {
            "observation_id": planned["observation_id"], "ticker": planned["ticker"], "cik": cik,
            "sector": planned["sector"], "fiscal_year": fiscal_year, "period_end": period,
            "filing_date": filed, "accession": accession,
            "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            "source_available_time": available, "information_cutoff": available,
            "outcome_window_end": add_twelve_months(datetime.fromisoformat(available)).isoformat().replace("+00:00", "Z"),
            "split": planned["split"], "annotation_status": "objective_label_pending", "facts": facts,
            "fact_provenance": provenance, "source_hash": packaged["member_sha256"],
            "raw_source_hashes": [source["sha256"], packaged["member_sha256"]], "source_type": "SEC_COMPANYFACTS_BULK",
        }
        observations.append(base)
    observations.sort(key=lambda row: (row["ticker"], row["fiscal_year"]))
    return observations, {"requested": len(plan), "imported": len(observations), "missing_observation_ids": sorted(missing), "sources": [source]}


def _accepted(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 8:
        raise ValueError("submission missing accepted/filing timestamp")
    stamp = digits.ljust(14, "0")[:14]
    parsed = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    return parsed.isoformat().replace("+00:00", "Z")


def _select_fact(rows: list[dict[str, str]], field: str, period: str) -> tuple[float | None, dict[str, Any] | None]:
    aliases = CONCEPT_ALIASES[field]
    candidates = []
    for row in rows:
        # Consolidated facts have neither a co-registrant nor an XBRL dimension.
        # FSDS exposes dimensions in ``segments``; accepting those rows can make
        # input order choose a product/geography value instead of the total.
        if (
            row.get("tag") not in aliases
            or (row.get("coreg") or "").strip()
            or (row.get("segments") or "").strip()
        ):
            continue
        if row.get("uom") != "USD" or row.get("ddate") != period:
            continue
        qtrs = row.get("qtrs", "")
        if field in INSTANT_FIELDS and qtrs not in {"0", ""}:
            continue
        if field not in INSTANT_FIELDS and qtrs not in {"4", "", "0"}:
            continue
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append((aliases.index(row["tag"]), row["tag"], value, row))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _, tag, value, row = candidates[0]
    return value, {
        "concept": tag,
        "period_end": period,
        "unit": "USD",
        "source_row": {
            key: row.get(key)
            for key in ("adsh", "tag", "version", "ddate", "qtrs", "uom", "coreg", "segments")
        },
    }


def build_numeric_corpus(
    plan: list[dict[str, str]], submissions: list[dict[str, str]], numbers: list[dict[str, str]], sources: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    wanted = {(FROZEN_CIKS[row["ticker"]].lstrip("0") or "0", row["fiscal_year"]): row for row in plan}
    by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in submissions:
        cik = str(row.get("cik", "")).lstrip("0") or "0"
        fy = str(row.get("fy", ""))
        if (cik, fy) in wanted and row.get("form") == "10-K":
            by_key[(cik, fy)].append(row)
    nums_by_adsh: dict[str, list[dict[str, str]]] = defaultdict(list)
    relevant_adsh = {row.get("adsh", "") for rows in by_key.values() for row in rows}
    for row in numbers:
        if row.get("adsh") in relevant_adsh:
            nums_by_adsh[row["adsh"]].append(row)

    observations: list[dict[str, Any]] = []
    missing: list[str] = []
    for key, planned in wanted.items():
        filings = by_key.get(key, [])
        if not filings:
            missing.append(planned["observation_id"])
            continue
        filings.sort(key=lambda row: (row.get("filed", ""), row.get("accepted", "")))
        filing = filings[0]  # original filing; later amendments/restatements are not silently substituted
        period = filing.get("period", "")
        adsh = filing.get("adsh", "")
        facts: dict[str, float | None] = {}
        provenance: dict[str, Any] = {}
        for field in CONCEPT_ALIASES:
            facts[field], provenance[field] = _select_fact(nums_by_adsh.get(adsh, []), field, period)
        if (
            facts["total_debt"] is None
            and facts["short_term_debt"] is not None
            and facts["long_term_debt"] is not None
        ):
            facts["total_debt"] = facts["short_term_debt"] + facts["long_term_debt"]
            provenance["total_debt"] = {
                "derived_from": ["short_term_debt", "long_term_debt"],
                "formula": "short_term_debt + long_term_debt",
            }
        accepted = _accepted(filing.get("accepted") or filing.get("filed", ""))
        filed_date = f"{filing['filed'][:4]}-{filing['filed'][4:6]}-{filing['filed'][6:8]}"
        filed_available = f"{filed_date}T23:59:59Z"
        available = max(accepted, filed_available)
        source_url = f"https://www.sec.gov/Archives/edgar/data/{int(key[0])}/{adsh.replace('-', '')}/"
        source_record = {
            "observation_id": planned["observation_id"], "ticker": planned["ticker"],
            "cik": FROZEN_CIKS[planned["ticker"]], "sector": planned["sector"],
            "fiscal_year": int(planned["fiscal_year"]), "period_end": f"{period[:4]}-{period[4:6]}-{period[6:8]}",
            "filing_date": filed_date, "filed_at": filed_available, "accepted_at": accepted,
            "accession": adsh, "source_url": source_url, "source_available_time": available,
            "information_cutoff": available,
            "outcome_window_end": add_twelve_months(datetime.fromisoformat(available)).isoformat().replace("+00:00", "Z"),
            "split": planned["split"], "annotation_status": "objective_label_pending", "facts": facts, "fact_provenance": provenance,
            "raw_source_hashes": [filing["__archive_sha256"]], "source_archive": filing["__archive_name"],
            "source_type": "SEC_FSDS",
        }
        source_record["source_hash"] = filing["__archive_sha256"]
        source_record["observation_hash"] = sha256_bytes(json.dumps(source_record, sort_keys=True).encode())
        observations.append(source_record)
    observations.sort(key=lambda row: (row["ticker"], row["fiscal_year"]))
    return observations, {"requested": len(plan), "imported": len(observations), "missing_observation_ids": sorted(missing), "sources": sources}


def enrich_metrics(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        by_ticker[row["ticker"]].append(row)
    for rows in by_ticker.values():
        rows.sort(key=lambda row: row["fiscal_year"])
        previous = None
        for row in rows:
            metrics = calculate_metrics(row["facts"], row["fiscal_year"], previous)
            row["metrics"] = {name: metric.value for name, metric in metrics.items()}
            previous = row["facts"]
    return observations


def build_annual_outcome_corpus(
    submissions: list[dict[str, str]],
    numbers: list[dict[str, str]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a label-only pool of original annual filings for frozen companies.

    This pool is intentionally independent from the frozen feature plan.  A
    future annual filing may be used as an outcome only after the observation's
    information cutoff; it is never merged into that observation's features.
    """
    inverse_ciks = {cik.lstrip("0") or "0": ticker for ticker, cik in FROZEN_CIKS.items()}
    plan_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for filing in submissions:
        cik = str(filing.get("cik", "")).lstrip("0") or "0"
        fiscal_year = str(filing.get("fy", ""))
        if filing.get("form") != "10-K" or cik not in inverse_ciks or not fiscal_year.isdigit():
            continue
        ticker = inverse_ciks[cik]
        plan_by_key[(ticker, fiscal_year)] = {
            "observation_id": f"{ticker}-{fiscal_year}",
            "ticker": ticker,
            "sector": "OUTCOME_ONLY",
            "fiscal_year": fiscal_year,
            "split": "outcome_only",
        }
    outcomes, _ = build_numeric_corpus(list(plan_by_key.values()), submissions, numbers, sources)
    return outcomes


def build_reported_fcf_periods(
    submissions: list[dict[str, str]], numbers: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Build filing-level FCF outcomes from original 10-Q/10-K SEC rows.

    These records are label-only outcomes. They are never attached to the
    feature observation and are admitted only after its information cutoff.
    """
    inverse_ciks = {cik.lstrip("0") or "0": ticker for ticker, cik in FROZEN_CIKS.items()}
    nums_by_adsh: dict[str, list[dict[str, str]]] = defaultdict(list)
    relevant = {
        row.get("adsh", "")
        for row in submissions
        if row.get("form") in {"10-Q", "10-K"}
        and (str(row.get("cik", "")).lstrip("0") or "0") in inverse_ciks
    }
    for row in numbers:
        if row.get("adsh") in relevant:
            nums_by_adsh[row["adsh"]].append(row)
    records = []
    seen: set[str] = set()
    for filing in sorted(submissions, key=lambda row: (row.get("filed", ""), row.get("accepted", ""))):
        adsh = filing.get("adsh", "")
        cik = str(filing.get("cik", "")).lstrip("0") or "0"
        if adsh in seen or adsh not in relevant or cik not in inverse_ciks:
            continue
        seen.add(adsh)
        period = filing.get("period", "")
        rows = nums_by_adsh.get(adsh, [])
        ocf, ocf_provenance = _select_reported_duration_fact(rows, "operating_cash_flow", period)
        capex, capex_provenance = _select_reported_duration_fact(rows, "capital_expenditure", period)
        accepted = _accepted(filing.get("accepted") or filing.get("filed", ""))
        filed = filing.get("filed", "")
        filed_at = f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}T23:59:59Z"
        records.append({
            "ticker": inverse_ciks[cik], "accession": adsh, "form": filing.get("form"),
            "fiscal_year": int(filing["fy"]) if str(filing.get("fy", "")).isdigit() else None,
            "period_end": f"{period[:4]}-{period[4:6]}-{period[6:8]}",
            "source_available_time": max(accepted, filed_at),
            "source_hash": filing.get("__archive_sha256"),
            "source_archive": filing.get("__archive_name"),
            "operating_cash_flow": ocf, "capital_expenditure": capex,
            "free_cash_flow": ocf - capex if ocf is not None and capex is not None else None,
            "fact_provenance": {"operating_cash_flow": ocf_provenance, "capital_expenditure": capex_provenance},
        })
    return records


def build_reported_fcf_periods_v2(
    submissions: list[dict[str, str]], numbers: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Prospective standalone-period FCF semantics; never used to rewrite E3.

    SEC Q2/Q3 duration facts are frequently year-to-date. This method subtracts
    the preceding YTD value for the same issuer and fiscal year. Q1 and annual
    values remain standalone. Ambiguous sequences are unavailable rather than
    silently treated as quarters.
    """
    records = build_reported_fcf_periods(submissions, numbers)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        fiscal_year = record.get("fiscal_year")
        if fiscal_year is None:
            continue
        grouped[(record["ticker"], str(fiscal_year))].append(record)
    output: list[dict[str, Any]] = []
    for rows in grouped.values():
        rows.sort(key=lambda item: item["period_end"])
        previous_ytd: dict[str, float] = {}
        for row in rows:
            copy = dict(row)
            provenance = row.get("fact_provenance", {})
            qtrs = {
                field: int((provenance.get(field) or {}).get("qtrs", "0"))
                for field in ("operating_cash_flow", "capital_expenditure")
            }
            standalone: dict[str, float | None] = {}
            for field in ("operating_cash_flow", "capital_expenditure"):
                value = row.get(field)
                duration = qtrs[field]
                if value is None:
                    standalone[field] = None
                elif duration in {1, 4}:
                    standalone[field] = float(value)
                elif duration in {2, 3} and field in previous_ytd:
                    standalone[field] = float(value) - previous_ytd[field]
                else:
                    standalone[field] = None
                if value is not None and duration in {1, 2, 3}:
                    previous_ytd[field] = float(value)
            copy.update(standalone)
            ocf, capex = standalone["operating_cash_flow"], standalone["capital_expenditure"]
            copy["free_cash_flow"] = ocf - capex if ocf is not None and capex is not None else None
            copy["methodology_version"] = "standalone-fcf-v2"
            output.append(copy)
    return sorted(output, key=lambda item: (item["ticker"], item["period_end"]))


def _select_reported_duration_fact(
    rows: list[dict[str, str]], field: str, period: str
) -> tuple[float | None, dict[str, Any] | None]:
    aliases = CONCEPT_ALIASES[field]
    candidates = []
    for row in rows:
        if (
            row.get("tag") not in aliases
            or row.get("ddate") != period
            or row.get("uom") != "USD"
            or row.get("qtrs") not in {"1", "2", "3", "4"}
            or (row.get("coreg") or "").strip()
            or (row.get("segments") or "").strip()
        ):
            continue
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        candidates.append((aliases.index(row["tag"]), row["qtrs"], value, row))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], -int(item[1])))
    _, _, value, row = candidates[0]
    return value, {
        "concept": row["tag"], "period_end": period, "unit": "USD", "qtrs": row["qtrs"],
        "source_row": {key: row.get(key) for key in ("adsh", "tag", "version", "ddate", "qtrs", "uom", "coreg", "segments")},
    }


def build_deterioration_labels(
    observations: list[dict[str, Any]],
    reported_periods: list[dict[str, Any]] | None = None,
    annual_outcomes: list[dict[str, Any]] | None = None,
    outcome_data_available_through: str | None = None,
) -> list[dict[str, Any]]:
    """Build the frozen secondary endpoint from future SEC facts, never from a FinRisk score."""
    labels: list[dict[str, Any]] = []
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in annual_outcomes if annual_outcomes is not None else observations:
        by_ticker[row["ticker"]].append(row)
    labelled_ids: set[str] = set()
    feature_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        feature_by_ticker[row["ticker"]].append(row)
    for ticker, current_rows in feature_by_ticker.items():
        outcomes = sorted(by_ticker.get(ticker, []), key=lambda row: row["fiscal_year"])
        for current in current_rows:
            candidates = [row for row in outcomes if row["fiscal_year"] == current["fiscal_year"] + 1]
            if not candidates:
                continue
            future = min(candidates, key=lambda row: row["source_available_time"])
            future_available = datetime.fromisoformat(future["source_available_time"])
            cutoff = datetime.fromisoformat(current["information_cutoff"])
            window_end = datetime.fromisoformat(current["outcome_window_end"])
            if not cutoff < future_available <= window_end:
                continue
            now, nxt = current["facts"], future["facts"]
            reasons: list[dict[str, Any]] = []
            def decline(field: str, threshold: float, base: dict[str, Any] = now, outcome: dict[str, Any] = nxt) -> bool:
                return base.get(field) not in (None, 0) and outcome.get(field) is not None and (outcome[field] - base[field]) / abs(base[field]) <= -threshold
            if decline("revenue", 0.10):
                reasons.append({"code": "REVENUE_DECLINE_10PCT", "value_t": now["revenue"], "value_t1": nxt["revenue"]})
            if now.get("net_income") is not None and nxt.get("net_income") is not None and now["net_income"] > 0 >= nxt["net_income"]:
                reasons.append({"code": "POSITIVE_INCOME_TO_LOSS", "value_t": now["net_income"], "value_t1": nxt["net_income"]})
            turns_negative = (
                now.get("operating_cash_flow") is not None
                and nxt.get("operating_cash_flow") is not None
                and now["operating_cash_flow"] >= 0 > nxt["operating_cash_flow"]
            )
            if decline("operating_cash_flow", 0.25) or turns_negative:
                reasons.append({"code": "OCF_DECLINE_OR_NEGATIVE", "value_t": now.get("operating_cash_flow"), "value_t1": nxt.get("operating_cash_flow")})
            debt_t = now.get("total_debt")
            debt_t1 = nxt.get("total_debt")
            assets_t = now.get("total_assets")
            assets_t1 = nxt.get("total_assets")
            if None not in (debt_t, debt_t1, assets_t, assets_t1) and assets_t and assets_t1 and debt_t1 / assets_t1 - debt_t / assets_t >= 0.10:
                reasons.append({"code": "DEBT_TO_ASSETS_INCREASE_10PP", "value_t": debt_t / assets_t, "value_t1": debt_t1 / assets_t1})
            required = ("revenue", "net_income", "operating_cash_flow", "total_assets", "total_debt")
            available = sum(now.get(field) is not None and nxt.get(field) is not None for field in required)
            future_reports = sorted(
                (
                    report for report in (reported_periods or [])
                    if report["ticker"] == current["ticker"]
                    and cutoff < datetime.fromisoformat(report["source_available_time"]) <= window_end
                ),
                key=lambda report: report["source_available_time"],
            )[:2]
            fcf_values = [report.get("free_cash_flow") for report in future_reports]
            if len(future_reports) == 2 and all(value is not None for value in fcf_values):
                fcf_condition = all(float(value) < 0 for value in fcf_values)
                fcf_condition_status = "VERIFIED_TRUE" if fcf_condition else "VERIFIED_FALSE"
                if fcf_condition:
                    reasons.append({
                        "code": "FCF_NEGATIVE_TWO_SUBSEQUENT_PERIODS",
                        "values": fcf_values,
                        "accessions": [report["accession"] for report in future_reports],
                    })
            else:
                fcf_condition_status = "INSUFFICIENT_DATA"
            true_codes = {reason["code"] for reason in reasons}
            condition_statuses = {
                "revenue_decline": "TRUE" if "REVENUE_DECLINE_10PCT" in true_codes else "FALSE" if now.get("revenue") not in (None, 0) and nxt.get("revenue") is not None else "UNKNOWN",
                "income_to_loss": "TRUE" if "POSITIVE_INCOME_TO_LOSS" in true_codes else "FALSE" if now.get("net_income") is not None and nxt.get("net_income") is not None else "UNKNOWN",
                "ocf_deterioration": "TRUE" if "OCF_DECLINE_OR_NEGATIVE" in true_codes else "FALSE" if now.get("operating_cash_flow") is not None and nxt.get("operating_cash_flow") is not None else "UNKNOWN",
                "debt_to_assets_increase": "TRUE" if "DEBT_TO_ASSETS_INCREASE_10PP" in true_codes else "FALSE" if None not in (debt_t, debt_t1, assets_t, assets_t1) and assets_t and assets_t1 else "UNKNOWN",
                "two_period_negative_fcf": "TRUE" if fcf_condition_status == "VERIFIED_TRUE" else "FALSE" if fcf_condition_status == "VERIFIED_FALSE" else "UNKNOWN",
            }
            true_count = sum(value == "TRUE" for value in condition_statuses.values())
            unknown_conditions = sorted(key for key, value in condition_statuses.items() if value == "UNKNOWN")
            # Two verified adverse conditions prove a positive even if other
            # components are missing. A negative is verified only when fewer
            # than two conditions can still possibly be true.
            status = "VERIFIED" if true_count >= 2 or true_count + len(unknown_conditions) < 2 else "REQUIRES_HUMAN_REVIEW"
            labels.append({
                "observation_id": current["observation_id"], "ticker": current["ticker"],
                "financial_deterioration_12m": int(true_count >= 2) if status == "VERIFIED" else None,
                "label_status": status, "label_generated_by": "deterministic_forward_outcome_rule_v1",
                "outcome_source_observation": future["observation_id"], "outcome_available_at": future["source_available_time"],
                "outcome_source_hash": future["source_hash"], "reason": reasons,
                "available_components": available, "required_components": len(required),
                "fcf_two_subsequent_periods": fcf_condition_status,
                "fcf_outcome_sources": [report["accession"] for report in future_reports],
                "condition_statuses": condition_statuses,
                "unknown_conditions": unknown_conditions,
            })
            labelled_ids.add(current["observation_id"])
    for row in observations:
        if row["observation_id"] not in labelled_ids:
            cutoff = datetime.fromisoformat(row["information_cutoff"])
            window_end = datetime.fromisoformat(row["outcome_window_end"])
            later = sorted(
                (
                    candidate for candidate in by_ticker.get(row["ticker"], [])
                    if candidate["fiscal_year"] == row["fiscal_year"] + 1
                    and datetime.fromisoformat(candidate["source_available_time"]) > cutoff
                ),
                key=lambda candidate: candidate["source_available_time"],
            )
            coverage_end = datetime.fromisoformat(outcome_data_available_through) if outcome_data_available_through else None
            if later and datetime.fromisoformat(later[0]["source_available_time"]) > window_end:
                code = "TRUE_NO_ELIGIBLE_OUTCOME"
            elif not later and (coverage_end is None or coverage_end < window_end):
                code = "RIGHT_CENSORED_DATA_HORIZON"
            elif not later:
                code = "TRUE_NO_ELIGIBLE_OUTCOME"
            else:
                code = "OTHER"
            labels.append({
                "observation_id": row["observation_id"], "ticker": row["ticker"],
                "financial_deterioration_12m": None, "label_status": "INSUFFICIENT_DATA",
                "label_generated_by": "deterministic_forward_outcome_rule_v1",
                "reason": [{
                    "code": code,
                    "outcome_window_end": row["outcome_window_end"],
                    "outcome_data_available_through": outcome_data_available_through,
                    "next_annual_available_at": later[0]["source_available_time"] if later else None,
                }],
            })
    labels.sort(key=lambda row: row["observation_id"])
    return labels


def readiness_report(observations: list[dict[str, Any]], labels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    labels = labels or []
    labelled = {row["observation_id"] for row in labels if row.get("financial_deterioration_12m") in {0, 1}}
    companies = defaultdict(set)
    for row in observations:
        companies[row["ticker"]].add(row["fiscal_year"])
    temporal = sum(len(years) >= 2 for years in companies.values())
    return {
        "NUMERIC_READY": "VERIFIED" if observations else "INSUFFICIENT_DATA",
        "LABEL_READY": "VERIFIED" if labelled else "INSUFFICIENT_DATA",
        "DOCUMENT_READY": "INSUFFICIENT_DATA",
        "TEMPORAL_READY": "VERIFIED" if temporal else "INSUFFICIENT_DATA",
        "EVIDENCE_READY": "INSUFFICIENT_DATA",
        "AGENT_READY": "BLOCKED_EXTERNAL_DEPENDENCY",
        "numeric_observations": len(observations), "labelled_observations": len(labelled),
        "temporal_companies": temporal,
    }
