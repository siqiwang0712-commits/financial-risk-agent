from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .domain import FinancialValue, ReconciliationResult

SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
MAX_SEC_RESPONSE_BYTES = 100 * 1024 * 1024

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
    "total_debt": ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"),
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
        if pause_seconds < 0 or max_retries < 0:
            raise ValueError("SEC pause_seconds and max_retries cannot be negative")
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.pause_seconds = pause_seconds
        self.max_retries=max_retries
        self._last_request_at=0.0

    @staticmethod
    def _normalize_cik(cik: str) -> str:
        raw = str(cik).strip()
        if re.fullmatch(r"[0-9]{1,10}", raw) is None:
            raise ValueError("SEC CIK must contain between 1 and 10 ASCII digits")
        return raw.zfill(10)

    def _cache_path(self, cache_key: str | None, suffix: str) -> Path | None:
        if self.cache_dir is None or cache_key is None:
            return None
        # Cache identifiers become filenames. Restrict them to one plain segment
        # so a caller cannot escape the configured cache root with ``../`` or an
        # absolute path.
        if re.fullmatch(r"[A-Za-z0-9._-]{1,200}", cache_key) is None:
            raise ValueError("SEC cache key contains unsafe characters")
        return self.cache_dir / f"{cache_key}{suffix}"

    @staticmethod
    def _validated_sec_url(url: str) -> str:
        parsed = urlparse(url)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("SEC endpoint contains an invalid port") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"data.sec.gov", "www.sec.gov"}
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            raise ValueError("SEC requests require an official HTTPS endpoint")
        return url

    @staticmethod
    def _read_verified_cache(cache: Path) -> bytes:
        if cache.stat().st_size > MAX_SEC_RESPONSE_BYTES:
            raise ValueError(f"SEC cache exceeds configured size limit: {cache}")
        hash_path = cache.with_suffix(".sha256")
        if not hash_path.is_file():
            # A crash between the data write and sidecar write leaves exactly this
            # state. Treat it as incomplete, not trusted historical evidence.
            raise ValueError(f"SEC cache hash is missing: {cache}")
        if hash_path.stat().st_size > 128:
            raise ValueError(f"SEC cache hash is invalid: {hash_path}")
        expected = hash_path.read_text(encoding="ascii").strip()
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError(f"SEC cache hash is invalid: {hash_path}")
        raw = cache.read_bytes()
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected):
            raise ValueError(f"SEC cache hash mismatch: {cache}")
        return raw

    @staticmethod
    def _json_object(raw: bytes) -> dict[str, Any]:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise TypeError("SEC JSON response must be an object")
        return payload

    @staticmethod
    def _read_bounded(response, limit: int = MAX_SEC_RESPONSE_BYTES) -> bytes:
        declared = response.headers.get("Content-Length")
        if declared:
            try:
                if int(declared) > limit:
                    raise ValueError("SEC response exceeds configured size limit")
            except ValueError as exc:
                if str(exc) == "SEC response exceeds configured size limit":
                    raise
                raise ValueError("SEC response has an invalid Content-Length") from exc
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("SEC response exceeds configured size limit")
        return raw

    def get_json(self, url: str, cache_key: str | None = None) -> dict[str, Any]:
        cache = self._cache_path(cache_key, ".json")
        if cache and cache.exists():
            return self._json_object(self._read_verified_cache(cache))
        url = self._validated_sec_url(url)
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
                with urllib.request.urlopen(request, timeout=60) as response:
                    payload = self._json_object(self._read_bounded(response))
                break
            except urllib.error.HTTPError as exc:
                if exc.code==403:raise RuntimeError("SEC rejected this network with HTTP 403; do not bypass Fair Access controls") from exc
                if exc.code not in {429,500,502,503,504} or attempt>=self.max_retries:raise
                retry_after=exc.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt,8))
            except urllib.error.URLError:
                if attempt>=self.max_retries:raise
                time.sleep(min(2**attempt,8))
        if payload is None:
            raise RuntimeError("SEC JSON request completed without a response")
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
            cache.write_bytes(raw);cache.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(),encoding="ascii")
        return payload

    def get_bytes(self, url: str, cache_key: str | None = None) -> bytes:
        """Fetch an SEC filing artifact with the same fair-access and hash policy."""
        cache = self._cache_path(cache_key, ".bin")
        if cache and cache.exists():
            return self._read_verified_cache(cache)
        url = self._validated_sec_url(url)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,*/*",
                "Accept-Encoding": "identity",
                "Host": urlparse(url).netloc,
            },
        )
        raw = None
        for attempt in range(self.max_retries + 1):
            delay = self.pause_seconds - (time.monotonic() - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
            try:
                self._last_request_at = time.monotonic()
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = self._read_bounded(response)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    raise RuntimeError("SEC rejected this network with HTTP 403; do not bypass Fair Access controls") from exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                retry_after = exc.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 8))
            except urllib.error.URLError:
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2**attempt, 8))
        if raw is None:
            raise RuntimeError("SEC filing request completed without a response")
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(raw)
            cache.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="ascii")
        return raw

    def companyfacts(self, cik: str) -> dict[str, Any]:
        normalized = self._normalize_cik(cik)
        return self.get_json(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{normalized}.json", f"companyfacts-{normalized}")

    def ticker_to_cik(self, ticker: str) -> str:
        if not isinstance(ticker, str) or re.fullmatch(r"[A-Za-z0-9.-]{1,20}", ticker.strip()) is None:
            raise ValueError("SEC ticker contains invalid characters")
        payload = self.get_json(
            "https://www.sec.gov/files/company_tickers.json", "company-tickers"
        )
        target = ticker.upper().strip()
        for company in payload.values():
            if not isinstance(company, dict):
                continue
            candidate = company.get("ticker")
            if isinstance(candidate, str) and candidate.upper() == target:
                return self._normalize_cik(company.get("cik_str", ""))
        raise KeyError(f"unknown SEC ticker: {ticker}")

    def submissions(self, cik: str) -> dict[str, Any]:
        normalized = self._normalize_cik(cik)
        return self.get_json(
            f"{SEC_BASE}/submissions/CIK{normalized}.json",
            f"submissions-{normalized}",
        )

    def latest_filing(self, ticker: str, forms: tuple[str, ...] = ("10-K", "10-Q")) -> dict[str, Any]:
        cik = self.ticker_to_cik(ticker)
        payload = self.submissions(cik)
        filings = payload.get("filings", {}) if isinstance(payload, dict) else {}
        recent = filings.get("recent", {}) if isinstance(filings, dict) else {}
        if not isinstance(recent, dict) or not isinstance(recent.get("form"), list):
            raise TypeError(f"SEC submissions are malformed for {ticker}")
        for index, form in enumerate(recent["form"]):
            if form not in forms:
                continue
            try:
                accession = recent["accessionNumber"][index]
                primary_document = recent["primaryDocument"][index]
                filing_date = recent["filingDate"][index]
                report_date = recent["reportDate"][index]
            except (KeyError, IndexError, TypeError):
                # SEC responses occasionally contain a partially populated recent
                # table. Skip an incomplete row instead of crashing the whole
                # acquisition boundary with IndexError.
                continue
            if not isinstance(accession, str) or not isinstance(primary_document, str):
                continue
            if (
                re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession) is None
                or re.fullmatch(r"[A-Za-z0-9._-]{1,255}", primary_document) is None
            ):
                continue
            accession_path = accession.replace("-", "")
            return {
                "ticker": ticker.upper(),
                "cik": cik,
                "form": form,
                "accession": accession,
                "filing_date": filing_date,
                "report_date": report_date,
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
        # SEC companyfacts attaches a filing's `fy` to comparative facts too.
        # The period end, not that filing metadata, determines which fiscal-year
        # observation this value represents.  Without this guard a prior-year
        # balance or revenue repeated in the newest 10-K can replace the current
        # value simply because it has the newest accession/filed date.
        try:
            period_end = date.fromisoformat(str(item["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if period_end.year != fiscal_year:
            continue
        if not instant:
            try:
                period_start = date.fromisoformat(str(item["start"]))
            except (KeyError, TypeError, ValueError):
                continue
            duration_days = (period_end - period_start).days
            if not 300 <= duration_days <= 380:
                continue
        result.append(item)
    return result


def _concepts_of(facts: dict[str, Any], taxonomy: str) -> list[dict[str, Any]]:
    """Concepts of a taxonomy, or [] when the caller sent something else."""
    concepts = facts.get(taxonomy)
    if not isinstance(concepts, dict):
        return []
    return [concept for concept in concepts.values() if isinstance(concept, dict)]


def _units_of(concept: dict[str, Any]) -> dict[str, Any]:
    units = concept.get("units")
    return units if isinstance(units, dict) else {}


def _numeric_value(item: dict[str, Any]) -> float | None:
    """`val` as a finite float, or None when it is absent or not a number."""
    try:
        value = float(item["val"])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def parse_companyfacts(payload: dict[str, Any], fiscal_years: list[int] | None = None) -> list[FinancialValue]:
    """Normalize SEC companyfacts and resolve duplicate/restated facts deterministically.

    For a line item/year, the most recently filed annual fact wins. A changed
    value reported by a later accession is marked restated and all provenance is
    retained on the selected FinancialValue.
    """
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        return []
    taxonomies = [name for name in ("us-gaap", "ifrs-full") if name in facts]
    available_years: set[int] = set()
    for taxonomy in taxonomies:
        # `companyfacts` is accepted from a public POST body, so every level of it
        # is caller-controlled: a taxonomy can be a list, a concept can be a
        # string, and `units` can hold anything. Skipping the malformed branches
        # keeps a bad payload from surfacing as a 500.
        for concept in _concepts_of(facts, taxonomy):
            for values in _units_of(concept).values():
                if not isinstance(values, list):
                    continue
                available_years.update(
                    v.get("fy") for v in values if isinstance(v, dict) and isinstance(v.get("fy"), int)
                )
    years = fiscal_years or sorted(available_years)
    output: list[FinancialValue] = []
    for year in years:
        for line_item, aliases in CONCEPTS.items():
            selected: tuple[str, str, str, dict[str, Any], list[dict[str, Any]]] | None = None
            selected_key: tuple[bool, str, str] | None = None
            for taxonomy in taxonomies:
                taxonomy_facts = facts.get(taxonomy)
                if not isinstance(taxonomy_facts, dict):
                    continue
                for concept_name in aliases:
                    concept = taxonomy_facts.get(concept_name)
                    if not isinstance(concept, dict):
                        continue
                    for unit_name, entries in _units_of(concept).items():
                        if not isinstance(entries, list):
                            continue
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
            numeric = _numeric_value(item)
            if numeric is None:
                # A fact without a usable `val` is not a fact; it used to raise
                # KeyError/ValueError out of the public normalize endpoint.
                continue
            values = {candidate.get("val") for candidate in candidates}
            accession = item.get("accn", "")
            cik = str(payload.get("cik", "")).lstrip("0")
            accession_path = accession.replace("-", "")
            filing_url = f"{SEC_ARCHIVES}/{cik}/{accession_path}/" if accession else None
            output.append(FinancialValue(
                line_item=line_item, value=numeric, fiscal_year=year,
                statement="xbrl", unit="currency" if unit_name != "shares" else "shares",
                currency=unit_name if len(unit_name) == 3 else "USD",
                document=f"SEC {item.get('form', 'filing')} {accession}", page=0,
                source_text=f"{taxonomy}:{concept_name}={item['val']} {unit_name}", confidence=0.99,
                restated=len(values) > 1, source_type="sec_xbrl", taxonomy=taxonomy,
                concept=concept_name, accession=accession, filed_at=item.get("filed"),
                period_start=item.get("start"), period_end=item.get("end"),
                original_unit=unit_name, provenance_url=filing_url,
            ))
        year_values = {value.line_item: value for value in output if value.fiscal_year == year}
        if "total_debt" not in year_values:
            current = year_values.get("short_term_debt")
            noncurrent = year_values.get("long_term_debt")
            if (
                current is not None
                and noncurrent is not None
                and current.accession == noncurrent.accession
                and current.period_end == noncurrent.period_end
                and current.original_unit == noncurrent.original_unit
            ):
                output.append(
                    FinancialValue(
                        line_item="total_debt",
                        value=float(current.value) + float(noncurrent.value),
                        fiscal_year=year,
                        statement="xbrl",
                        unit=current.unit,
                        currency=current.currency,
                        document=current.document,
                        page=0,
                        source_text="short_term_debt + long_term_debt",
                        confidence=min(current.confidence, noncurrent.confidence),
                        restated=current.restated or noncurrent.restated,
                        source_type="sec_xbrl_derived",
                        accession=current.accession,
                        filed_at=max(current.filed_at or "", noncurrent.filed_at or ""),
                        period_end=current.period_end,
                        original_unit=current.original_unit,
                        provenance_url=current.provenance_url,
                    )
                )
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
    except (
        OSError,
        RuntimeError,
        KeyError,
        LookupError,
        TypeError,
        ValueError,
        urllib.error.URLError,
    ) as exc:
        return {
            "status": "SOURCE_UNAVAILABLE",
            "filing": None,
            "decision": "ABSTAIN",
            "coverage_impact": "authoritative SEC filing metadata unavailable",
            "error_type": type(exc).__name__,
        }
