from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .domain import FinancialValue, ReconciliationResult

SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# Ordered aliases: the first reliably present concept wins. Values in SEC
# companyfacts are already expressed in the stated unit (normally USD/shares).
CONCEPTS: dict[str, tuple[str, ...]] = {
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "accounts_receivable": ("AccountsReceivableNetCurrent", "AccountsNotesAndLoansReceivableNetCurrent"),
    "inventory": ("InventoryNet",),
    "current_assets": ("AssetsCurrent",),
    "total_assets": ("Assets",),
    "accounts_payable": ("AccountsPayableCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "short_term_debt": ("ShortTermBorrowings", "ShortTermDebtCurrent", "LongTermDebtCurrent"),
    "long_term_debt": ("LongTermDebtNoncurrent",),
    "total_debt": ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebt"),
    "total_liabilities": ("Liabilities",),
    "shareholder_equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "retained_earnings": ("RetainedEarningsAccumulatedDeficit",),
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "interest_expense": ("InterestExpenseNonOperating", "InterestAndDebtExpense"),
    "pretax_income": ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "investing_cash_flow": ("NetCashProvidedByUsedInInvestingActivities",),
    "financing_cash_flow": ("NetCashProvidedByUsedInFinancingActivities",),
}

INSTANT_ITEMS = {
    "cash", "accounts_receivable", "inventory", "current_assets", "total_assets",
    "accounts_payable", "current_liabilities", "short_term_debt", "long_term_debt",
    "total_debt", "total_liabilities", "shareholder_equity", "retained_earnings",
}


class SecClient:
    """Small, polite SEC JSON client with an explicit identifying User-Agent."""

    def __init__(self, user_agent: str, cache_dir: Path | None = None, pause_seconds: float = 0.12, max_retries: int = 3):
        if "@" not in user_agent:
            raise ValueError("SEC user_agent must identify an application and contact email")
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.pause_seconds = pause_seconds
        self.max_retries=max_retries
        self._last_request_at=0.0

    def get_json(self, url: str, cache_key: str | None = None) -> dict[str, Any]:
        cache = self.cache_dir / f"{cache_key}.json" if self.cache_dir and cache_key else None
        if cache and cache.exists():
            raw=cache.read_bytes();hash_path=cache.with_suffix(".sha256")
            if hash_path.exists() and hashlib.sha256(raw).hexdigest()!=hash_path.read_text(encoding="ascii").strip():raise ValueError(f"SEC cache hash mismatch: {cache}")
            return json.loads(raw)
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Encoding": "identity",
            "Host": urlparse(url).netloc,
        })
        payload=None
        for attempt in range(self.max_retries+1):
            delay=self.pause_seconds-(time.monotonic()-self._last_request_at)
            if delay>0:time.sleep(delay)
            try:
                self._last_request_at=time.monotonic()
                with urllib.request.urlopen(request, timeout=60) as response:payload=json.load(response)
                break
            except urllib.error.HTTPError as exc:
                if exc.code==403:raise RuntimeError("SEC rejected this network with HTTP 403; do not bypass Fair Access controls") from exc
                if exc.code not in {429,500,502,503,504} or attempt>=self.max_retries:raise
                retry_after=exc.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt,8))
            except urllib.error.URLError:
                if attempt>=self.max_retries:raise
                time.sleep(min(2**attempt,8))
        assert payload is not None
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
            cache.write_bytes(raw);cache.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(),encoding="ascii")
        return payload

    def companyfacts(self, cik: str) -> dict[str, Any]:
        normalized = str(cik).zfill(10)
        return self.get_json(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{normalized}.json", f"companyfacts-{normalized}")

    def ticker_to_cik(self, ticker: str) -> str:
        payload = self.get_json(
            "https://www.sec.gov/files/company_tickers.json", "company-tickers"
        )
        target = ticker.upper().strip()
        for company in payload.values():
            if company.get("ticker", "").upper() == target:
                return str(company["cik_str"]).zfill(10)
        raise KeyError(f"unknown SEC ticker: {ticker}")

    def submissions(self, cik: str) -> dict[str, Any]:
        normalized = str(cik).zfill(10)
        return self.get_json(
            f"{SEC_BASE}/submissions/CIK{normalized}.json",
            f"submissions-{normalized}",
        )

    def latest_filing(self, ticker: str, forms: tuple[str, ...] = ("10-K", "10-Q")) -> dict[str, Any]:
        cik = self.ticker_to_cik(ticker)
        payload = self.submissions(cik)
        recent = payload.get("filings", {}).get("recent", {})
        for index, form in enumerate(recent.get("form", [])):
            if form not in forms:
                continue
            accession = recent["accessionNumber"][index]
            primary_document = recent["primaryDocument"][index]
            accession_path = accession.replace("-", "")
            return {
                "ticker": ticker.upper(),
                "cik": cik,
                "form": form,
                "accession": accession,
                "filing_date": recent["filingDate"][index],
                "report_date": recent["reportDate"][index],
                "primary_document": primary_document,
                "filing_url": f"{SEC_ARCHIVES}/{int(cik)}/{accession_path}/{primary_document}",
                "companyfacts_url": f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            }
        raise LookupError(f"no supported filing found for {ticker}")


def _annual_candidates(entries: list[dict[str, Any]], fiscal_year: int, instant: bool) -> list[dict[str, Any]]:
    result = []
    for item in entries:
        if item.get("form") not in {"10-K", "10-K/A", "20-F", "20-F/A"} or item.get("fy") != fiscal_year:
            continue
        if not instant and item.get("fp") not in {"FY", None}:
            continue
        result.append(item)
    return result


def parse_companyfacts(payload: dict[str, Any], fiscal_years: list[int] | None = None) -> list[FinancialValue]:
    """Normalize SEC companyfacts and resolve duplicate/restated facts deterministically.

    For a line item/year, the most recently filed annual fact wins. A changed
    value reported by a later accession is marked restated and all provenance is
    retained on the selected FinancialValue.
    """
    facts = payload.get("facts", {})
    taxonomies = [name for name in ("us-gaap", "ifrs-full") if name in facts]
    available_years: set[int] = set()
    for taxonomy in taxonomies:
        for concept in facts[taxonomy].values():
            for values in concept.get("units", {}).values():
                available_years.update(v.get("fy") for v in values if isinstance(v.get("fy"), int))
    years = fiscal_years or sorted(available_years)
    output: list[FinancialValue] = []
    for year in years:
        for line_item, aliases in CONCEPTS.items():
            selected: tuple[str, str, str, dict[str, Any], list[dict[str, Any]]] | None = None
            selected_key: tuple[bool, str, str] | None = None
            for taxonomy in taxonomies:
                for concept_name in aliases:
                    concept = facts[taxonomy].get(concept_name)
                    if not concept:
                        continue
                    for unit_name, entries in concept.get("units", {}).items():
                        candidates = _annual_candidates(entries, year, line_item in INSTANT_ITEMS)
                        if candidates:
                            candidates.sort(key=lambda x: (x.get("filed", ""), x.get("accn", "")))
                            candidate = candidates[-1]
                            candidate_key = (
                                unit_name == "USD",
                                candidate.get("filed", ""),
                                candidate.get("accn", ""),
                            )
                            if selected_key is None or candidate_key > selected_key:
                                selected = taxonomy, concept_name, unit_name, candidate, candidates
                                selected_key = candidate_key
            if selected is None:
                continue
            taxonomy, concept_name, unit_name, item, candidates = selected
            values = {candidate.get("val") for candidate in candidates}
            accession = item.get("accn", "")
            cik = str(payload.get("cik", "")).lstrip("0")
            accession_path = accession.replace("-", "")
            filing_url = f"{SEC_ARCHIVES}/{cik}/{accession_path}/" if accession else None
            output.append(FinancialValue(
                line_item=line_item, value=float(item["val"]), fiscal_year=year,
                statement="xbrl", unit="currency" if unit_name != "shares" else "shares",
                currency=unit_name if len(unit_name) == 3 else "USD",
                document=f"SEC {item.get('form', 'filing')} {accession}", page=0,
                source_text=f"{taxonomy}:{concept_name}={item['val']} {unit_name}", confidence=0.99,
                restated=len(values) > 1, source_type="sec_xbrl", taxonomy=taxonomy,
                concept=concept_name, accession=accession, filed_at=item.get("filed"),
                period_start=item.get("start"), period_end=item.get("end"),
                original_unit=unit_name, provenance_url=filing_url,
            ))
    return output


def values_by_year(values: list[FinancialValue]) -> dict[int, dict[str, float]]:
    grouped: dict[int, dict[str, float]] = defaultdict(dict)
    for value in values:
        if value.value is not None:
            grouped[value.fiscal_year][value.line_item] = value.value
    return dict(grouped)


def reconcile_sources(xbrl: list[FinancialValue], document: list[FinancialValue], relative_tolerance: float = 0.01) -> list[ReconciliationResult]:
    xmap = {(x.line_item, x.fiscal_year): x for x in xbrl}
    dmap = {(x.line_item, x.fiscal_year): x for x in document}
    results = []
    for key in sorted(set(xmap) | set(dmap)):
        xv, dv = xmap.get(key), dmap.get(key)
        if xv is None or dv is None:
            results.append(ReconciliationResult(key[0], key[1], "single_source", "xbrl" if xv else "document", xv.value if xv else None, dv.value if dv else None, None, None, "Only one source supplied this fact; uncertainty is retained.", xv, dv))
            continue
        absolute = abs(xv.value - dv.value) if xv.value is not None and dv.value is not None else None
        relative = absolute / max(abs(xv.value), 1.0) if absolute is not None else None
        status = "matched" if relative is not None and relative <= relative_tolerance else "conflict"
        explanation = "Sources agree within configured tolerance." if status == "matched" else "Sources disagree; XBRL remains authoritative and the document value is flagged for review."
        results.append(ReconciliationResult(key[0], key[1], status, "xbrl", xv.value, dv.value, absolute, relative, explanation, xv, dv))
    return results


def write_snapshot(values: list[FinancialValue], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(v) for v in values], indent=2), encoding="utf-8")


def acquire_latest_filing(client: SecClient, ticker: str) -> dict[str, Any]:
    """Fail-closed SEC acquisition boundary for product and worker callers."""
    try:
        return {"status": "READY", "filing": client.latest_filing(ticker), "decision": None}
    except (OSError, RuntimeError, KeyError, LookupError, urllib.error.URLError) as exc:
        return {
            "status": "SOURCE_UNAVAILABLE",
            "filing": None,
            "decision": "ABSTAIN",
            "coverage_impact": "authoritative SEC filing metadata unavailable",
            "error_type": type(exc).__name__,
        }
