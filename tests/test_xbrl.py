import hashlib
import json
import urllib.error
from pathlib import Path
from typing import ClassVar

import pytest
from finrisk.domain import FinancialValue
from finrisk.xbrl import (
    MAX_SEC_RESPONSE_BYTES,
    SecClient,
    acquire_latest_filing,
    parse_companyfacts,
    reconcile_sources,
    values_by_year,
)


def fixture():
    return {"cik":320193,"facts":{"us-gaap":{"Assets":{"units":{"USD":[
        {"fy":2024,"fp":"FY","form":"10-K","val":100,"filed":"2024-10-01","accn":"1","end":"2024-09-30"},
        {"fy":2024,"fp":"FY","form":"10-K/A","val":110,"filed":"2024-11-01","accn":"2","end":"2024-09-30"}
    ]}},"RevenueFromContractWithCustomerExcludingAssessedTax":{"units":{"USD":[
        {"fy":2024,"fp":"FY","form":"10-K","val":50,"filed":"2024-10-01","accn":"1","start":"2023-10-01","end":"2024-09-30"}
    ]}}}}}


def test_companyfacts_restated_and_provenance():
    values=parse_companyfacts(fixture(),[2024]); by_year=values_by_year(values)
    assets=next(v for v in values if v.line_item=="total_assets")
    assert by_year[2024]["total_assets"]==110
    assert assets.restated and assets.source_type=="sec_xbrl" and assets.concept=="Assets" and assets.accession=="2"


def test_reconciliation_prefers_xbrl_and_flags_conflict():
    x=FinancialValue("cash",100,2024,"xbrl",source_type="sec_xbrl")
    matched=FinancialValue("cash",100.5,2024,"balance_sheet")
    conflict=FinancialValue("cash",80,2024,"balance_sheet")
    assert reconcile_sources([x],[matched])[0].status=="matched"
    result=reconcile_sources([x],[conflict])[0]
    assert result.status=="conflict" and result.authoritative_source=="xbrl" and result.relative_difference==.2

def test_sec_cache_is_hash_verified(tmp_path):
    raw=json.dumps({"ok":True}).encode();cache=tmp_path/"sample.json";cache.write_bytes(raw)
    cache.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(),encoding="ascii")
    client=SecClient("FinRisk test@example.com",tmp_path)
    assert client.get_json("https://example.invalid","sample")=={"ok":True}
    cache.write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="hash mismatch"):client.get_json("https://example.invalid","sample")


def test_sec_binary_cache_is_hash_verified(tmp_path):
    raw = b"<html>inline xbrl</html>"
    cache = tmp_path / "filing.bin"
    cache.write_bytes(raw)
    cache.with_suffix(".sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="ascii")
    client = SecClient("FinRisk test@example.com", tmp_path)
    assert client.get_bytes("https://example.invalid", "filing") == raw
    cache.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        client.get_bytes("https://example.invalid", "filing")


@pytest.mark.parametrize(("suffix", "method"), [(".json", "get_json"), (".bin", "get_bytes")])
def test_sec_cache_without_hash_fails_closed(tmp_path, suffix, method):
    (tmp_path / f"incomplete{suffix}").write_bytes(b"{}")
    client = SecClient("FinRisk test@example.com", tmp_path)
    with pytest.raises(ValueError, match="hash is missing"):
        getattr(client, method)("https://example.invalid", "incomplete")


def test_sec_cache_rejects_oversized_content_before_reading(tmp_path, monkeypatch):
    cache = tmp_path / "oversized.bin"
    cache.write_bytes(b"content")
    cache.with_suffix(".sha256").write_text("0" * 64, encoding="ascii")
    original_stat = Path.stat

    def oversized_stat(path):
        result = original_stat(path)
        if path == cache:
            return type("Stat", (), {"st_size": MAX_SEC_RESPONSE_BYTES + 1})()
        return result

    monkeypatch.setattr(Path, "stat", oversized_stat)
    client = SecClient("FinRisk test@example.com", tmp_path)
    with pytest.raises(ValueError, match="size limit"):
        client.get_bytes("https://example.invalid", "oversized")


@pytest.mark.parametrize("digest", ["not-a-digest", "0" * 129])
def test_sec_cache_rejects_invalid_hash_sidecars(tmp_path, digest):
    cache = tmp_path / "invalid.bin"
    cache.write_bytes(b"content")
    cache.with_suffix(".sha256").write_text(digest, encoding="ascii")
    client = SecClient("FinRisk test@example.com", tmp_path)
    with pytest.raises(ValueError, match="hash is invalid"):
        client.get_bytes("https://example.invalid", "invalid")


def test_sec_identifiers_cannot_escape_cache_root(tmp_path):
    client = SecClient("FinRisk test@example.com", tmp_path)
    with pytest.raises(ValueError, match="unsafe characters"):
        client.get_json("https://example.invalid", "../outside")
    with pytest.raises(ValueError, match="ASCII digits"):
        client.companyfacts("../../outside")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://data.sec.gov/test",
        "https://data.sec.gov:invalid/test",
        "https://data.sec.gov:444/test",
        "https://example.com/test",
    ],
)
def test_sec_network_requests_are_restricted_to_official_https_hosts(url):
    client = SecClient("FinRisk test@example.com")
    with pytest.raises(ValueError, match="SEC (requests require|endpoint contains)"):
        client.get_json(url)


@pytest.mark.parametrize(
    "options",
    [{"pause_seconds": -0.1}, {"max_retries": -1}],
)
def test_sec_client_rejects_negative_retry_configuration(options):
    with pytest.raises(ValueError, match="cannot be negative"):
        SecClient("FinRisk test@example.com", **options)


def test_sec_json_payload_must_be_an_object():
    with pytest.raises(TypeError, match="must be an object"):
        SecClient._json_object(b"[]")


@pytest.mark.parametrize("ticker", ["../ACME", "", None])
def test_sec_ticker_rejects_invalid_input(ticker):
    client = SecClient("FinRisk test@example.com")
    with pytest.raises(ValueError, match="ticker contains invalid"):
        client.ticker_to_cik(ticker)


def test_companyfacts_preserves_and_prefers_authoritative_unit():
    payload = fixture()
    payload["facts"]["us-gaap"]["Assets"]["units"]["EUR"] = [
        {"fy": 2024, "fp": "FY", "form": "10-K", "val": 999, "filed": "2025-01-01", "accn": "3", "end": "2024-09-30"}
    ]
    value = next(item for item in parse_companyfacts(payload, [2024]) if item.line_item == "total_assets")
    assert value.value == 110 and value.currency == "USD" and value.original_unit == "USD"


def test_sec_acquisition_fails_closed():
    client = SecClient("FinRisk test@example.com")
    client.latest_filing = lambda ticker: (_ for _ in ()).throw(RuntimeError("SEC unavailable"))
    result = acquire_latest_filing(client, "ACME")
    assert result["decision"] == "ABSTAIN" and result["filing"] is None


def test_sec_acquisition_abstains_on_malformed_submission_rows():
    client = SecClient("FinRisk test@example.com")
    responses = [
        {"0": {"ticker": "ACME", "cik_str": 42}},
        {
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "accessionNumber": [],
                    "primaryDocument": [],
                    "filingDate": [],
                    "reportDate": [],
                }
            }
        },
    ]
    client.get_json = lambda *_args, **_kwargs: responses.pop(0)
    result = acquire_latest_filing(client, "ACME")
    assert result["decision"] == "ABSTAIN"
    assert result["error_type"] == "LookupError"


def test_sec_acquisition_skips_unsafe_filing_paths():
    client = SecClient("FinRisk test@example.com")
    responses = [
        {"0": {"ticker": "ACME", "cik_str": 42}},
        {
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "accessionNumber": ["0000000042-26-000001"],
                    "primaryDocument": ["../../outside.htm"],
                    "filingDate": ["2026-09-01"],
                    "reportDate": ["2026-06-30"],
                }
            }
        },
    ]
    client.get_json = lambda *_args, **_kwargs: responses.pop(0)
    result = acquire_latest_filing(client, "ACME")
    assert result["decision"] == "ABSTAIN"
    assert result["error_type"] == "LookupError"


def test_companyfacts_debt_component_is_not_aggregate_and_derives_only_complete_total():
    payload = fixture()
    unit = payload["facts"]["us-gaap"]
    base = {"fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-10-01", "accn": "1", "end": "2024-09-30"}
    unit["LongTermDebtAndFinanceLeaseObligationsCurrent"] = {"units": {"USD": [{**base, "val": 999}]}}
    unit["LongTermDebtCurrent"] = {"units": {"USD": [{**base, "val": 10}]}}
    unit["LongTermDebtNoncurrent"] = {"units": {"USD": [{**base, "val": 40}]}}
    values = parse_companyfacts(payload, [2024])
    total = next(value for value in values if value.line_item == "total_debt")
    assert total.value == 50
    assert total.source_type == "sec_xbrl_derived"

    del unit["LongTermDebtNoncurrent"]
    incomplete = parse_companyfacts(payload, [2024])
    assert not any(value.line_item == "total_debt" for value in incomplete)


def test_companyfacts_uses_period_end_not_comparative_filing_year():
    payload = fixture()
    entries = payload["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    entries.append({
        "fy": 2024, "fp": "FY", "form": "10-K", "val": 70,
        "filed": "2025-10-01", "accn": "new-comparative", "end": "2023-09-30",
    })
    revenue = payload["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
    revenue.extend([
        {"fy": 2024, "fp": "FY", "form": "10-K", "val": 40, "filed": "2025-10-01", "accn": "new-comparative", "start": "2022-10-01", "end": "2023-09-30"},
        {"fy": 2024, "fp": "FY", "form": "10-K", "val": 15, "filed": "2025-10-01", "accn": "quarter", "start": "2024-07-01", "end": "2024-09-30"},
    ])
    values = parse_companyfacts(payload, [2024])
    assert next(value for value in values if value.line_item == "total_assets").value == 110
    assert next(value for value in values if value.line_item == "revenue").value == 50


def test_sec_response_reader_rejects_unbounded_payloads():
    class Response:
        def __init__(self):
            self.headers = {}

        def read(self, amount):
            return b"x" * amount

    with pytest.raises(ValueError, match="size limit"):
        SecClient._read_bounded(Response(), 16)

    class DeclaredOversized(Response):
        headers: ClassVar[dict[str, str]] = {"Content-Length": "17"}

    with pytest.raises(ValueError, match="size limit"):
        SecClient._read_bounded(DeclaredOversized(), 16)


def test_sec_network_json_is_bounded_and_hash_cached(monkeypatch, tmp_path):
    body = json.dumps({"ok": True}).encode()

    class Response:
        headers: ClassVar[dict[str, str]] = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, amount):
            assert amount == 100 * 1024 * 1024 + 1
            return body

    monkeypatch.setattr("finrisk.xbrl.urllib.request.urlopen", lambda *_, **__: Response())
    client = SecClient("FinRisk test@example.com", tmp_path, pause_seconds=0)
    assert client.get_json("https://data.sec.gov/test", "remote") == {"ok": True}
    assert (tmp_path / "remote.json").read_bytes() == b'{"ok":true}'
    assert (tmp_path / "remote.sha256").exists()

    class InvalidLength(Response):
        headers: ClassVar[dict[str, str]] = {"Content-Length": "invalid"}

    with pytest.raises(ValueError, match="invalid Content-Length"):
        SecClient._read_bounded(InvalidLength())


@pytest.mark.parametrize(
    "first_error",
    [
        urllib.error.HTTPError(
            "https://data.sec.gov/test", 429, "rate limited", {"Retry-After": "0"}, None
        ),
        urllib.error.URLError("temporary network failure"),
    ],
)
def test_sec_json_retries_transient_failures(monkeypatch, first_error):
    body = b'{"ok":true}'

    class Response:
        headers: ClassVar[dict[str, str]] = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _amount):
            return body

    outcomes = [first_error, Response()]

    def urlopen(*_args, **_kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("finrisk.xbrl.urllib.request.urlopen", urlopen)
    monkeypatch.setattr("finrisk.xbrl.time.sleep", lambda _seconds: None)
    client = SecClient("FinRisk test@example.com", pause_seconds=0, max_retries=1)
    assert client.get_json("https://data.sec.gov/test") == {"ok": True}


def test_sec_network_bytes_are_bounded_and_hash_cached(monkeypatch, tmp_path):
    body = b"<html>filing</html>"

    class Response:
        headers: ClassVar[dict[str, str]] = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, amount):
            assert amount == 100 * 1024 * 1024 + 1
            return body

    monkeypatch.setattr("finrisk.xbrl.urllib.request.urlopen", lambda *_, **__: Response())
    client = SecClient("FinRisk test@example.com", tmp_path, pause_seconds=0)
    assert client.get_bytes("https://www.sec.gov/Archives/test", "filing") == body
    assert (tmp_path / "filing.bin").read_bytes() == body
    assert client.get_bytes("https://example.invalid", "filing") == body
