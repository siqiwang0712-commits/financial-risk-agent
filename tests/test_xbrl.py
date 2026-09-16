import hashlib
import json
from typing import ClassVar

import pytest
from finrisk.domain import FinancialValue
from finrisk.xbrl import (
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
