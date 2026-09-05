"""Build compact, versioned SEC XBRL snapshots for the public benchmark.

This networked step is intentionally separate from evaluation. Evaluation uses
the checked-in compact snapshots, while this script makes their origin auditable.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from finrisk.xbrl import SecClient, parse_companyfacts

COMPANIES = (
    {"id": "aapl", "company": "Apple Inc.", "cik": "0000320193", "years": [2023, 2024]},
    {"id": "msft", "company": "Microsoft Corporation", "cik": "0000789019", "years": [2023, 2024]},
    {"id": "intc", "company": "Intel Corporation", "cik": "0000050863", "years": [2023, 2024]},
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="research/benchmark/snapshots")
    parser.add_argument("--cache-dir", default=".cache/sec")
    parser.add_argument("--user-agent", default=os.getenv("SEC_USER_AGENT"))
    args = parser.parse_args()
    if not args.user_agent:
        raise SystemExit("Set SEC_USER_AGENT='FinRisk-Agent contact@example.com'")
    root = Path(__file__).resolve().parents[1]
    output = root / args.output_dir
    client = SecClient(args.user_agent, root / args.cache_dir)
    manifest = {"dataset_id": "finrisk-sec-mini-v1", "kind": "public_company", "source": "SEC Company Facts API", "examples": []}
    for company in COMPANIES:
        payload = client.companyfacts(company["cik"])
        values = parse_companyfacts(payload, company["years"])
        path = output / f"{company['id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"company": company["company"], "cik": company["cik"], "values": [asdict(v) for v in values]}, indent=2), encoding="utf-8")
        manifest["examples"].append({**company, "snapshot": str(path.relative_to(root)).replace("\\", "/"), "split": {"aapl": "train", "msft": "validation", "intc": "test"}[company["id"]]})
    manifest_path = root / "research/benchmark/public_company_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {len(COMPANIES)} company-disjoint snapshots to {manifest_path}")


if __name__ == "__main__":
    main()
