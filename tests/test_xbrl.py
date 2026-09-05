import hashlib
import json

import pytest
from finrisk.domain import FinancialValue
from finrisk.xbrl import (
    SecClient,
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
