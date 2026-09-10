"""Acquire the pre-registered SEC corpus with point-in-time filtering.

Requires an identifying SEC_USER_AGENT. Raw HTTP cache remains local/ignored;
compact PIT-filtered snapshots and their hashes are the reproducible inputs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import urllib.error
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from finrisk.empirical_validation import validate_dataset_integrity
from finrisk.xbrl import SEC_ARCHIVES, SEC_BASE, SecClient, parse_companyfacts

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "research/empirical_v1/acquisition_plan.csv"
OUTPUT = ROOT / "research/empirical_v1"
ACQUISITION_ERRORS = (
    OSError,
    RuntimeError,
    ValueError,
    KeyError,
    LookupError,
    urllib.error.URLError,
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def pit_companyfacts(payload: dict, cutoff: str) -> dict:
    filtered = json.loads(json.dumps(payload))
    for taxonomy in filtered.get("facts", {}).values():
        for concept in taxonomy.values():
            for unit, facts in concept.get("units", {}).items():
                concept["units"][unit] = [
                    fact for fact in facts if str(fact.get("filed", "9999-12-31")) <= cutoff
                ]
    return filtered


def expanded_submissions(client: SecClient, submissions: dict) -> dict:
    """Merge SEC historical submission shards into the recent column layout."""
    expanded = json.loads(json.dumps(submissions))
    recent = expanded.setdefault("filings", {}).setdefault("recent", {})
    for descriptor in expanded.get("filings", {}).get("files", []):
        name = descriptor.get("name")
        if not name:
            continue
        historical = client.get_json(f"{SEC_BASE}/submissions/{name}", f"submissions-history-{name}")
        for field, values in historical.items():
            if isinstance(values, list):
                recent.setdefault(field, []).extend(values)
    return expanded


def annual_filing(submissions: dict, fiscal_year: int) -> dict | None:
    recent = submissions.get("filings", {}).get("recent", {})
    candidates = []
    for index, form in enumerate(recent.get("form", [])):
        report_dates = recent.get("reportDate", [])
        accessions = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])
        if index >= min(len(report_dates), len(accessions), len(primary_documents), len(filing_dates)):
            continue
        report_date = report_dates[index]
        if form in {"10-K", "10-K/A"} and report_date.startswith(str(fiscal_year)):
            candidates.append({
                "accession": accessions[index],
                "filing_date": filing_dates[index],
                "accepted_at": recent.get("acceptanceDateTime", [""] * len(recent.get("form", [])))[index] or f"{filing_dates[index]}T23:59:59Z",
                "period_end": report_date,
                "primary_document": primary_documents[index],
                "form": form,
            })
    # The prediction cutoff is the earliest public annual filing for the period.
    # Later amendments/restatements are outcomes of the PIT guard, not silently
    # substituted feature inputs.
    return min(candidates, key=lambda item: (item["filing_date"], item["form"] != "10-K"), default=None)


def main() -> None:
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise SystemExit("SEC_USER_AGENT is required; no corpus was fabricated")
    plans = list(csv.DictReader(PLAN.open(encoding="utf-8")))
    client = SecClient(user_agent, ROOT / ".cache/sec-empirical", pause_seconds=0.15)
    manifest_path = OUTPUT / "corpus_manifest.json"
    observations = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    completed = {item["observation_id"] for item in observations}
    failures = []
    for ticker in dict.fromkeys(item["ticker"] for item in plans):
        pending = [item for item in plans if item["ticker"] == ticker and item["observation_id"] not in completed]
        if not pending:
            continue
        try:
            cik = client.ticker_to_cik(ticker)
            submissions = expanded_submissions(client, client.submissions(cik))
            raw = client.companyfacts(cik)
            raw_hash = hashlib.sha256(canonical_bytes(raw)).hexdigest()
        except ACQUISITION_ERRORS as exc:  # persisted failure; acquisition continues
            failures.extend({"observation_id": item["observation_id"], "error_type": type(exc).__name__, "detail": str(exc)} for item in pending)
            continue
        for planned in pending:
            try:
                filing = annual_filing(submissions, int(planned["fiscal_year"]))
                if filing is None:
                    raise RuntimeError("missing 10-K metadata")
                cutoff = filing["accepted_at"]
                accession_path = filing["accession"].replace("-", "")
                filing_url = f"{SEC_ARCHIVES}/{int(cik)}/{accession_path}/{filing['primary_document']}"
                filing_bytes = client.get_bytes(filing_url, f"filing-{filing['accession']}")
                filing_hash = hashlib.sha256(filing_bytes).hexdigest()
                filtered = pit_companyfacts(raw, cutoff[:10])
                values = parse_companyfacts(filtered, [int(planned["fiscal_year"])])
                if not values:
                    raise RuntimeError("no PIT XBRL facts")
                snapshot = {
                "ticker": ticker,
                "cik": cik,
                "information_cutoff": cutoff,
                "raw_companyfacts_hash": raw_hash,
                "filing_hash": filing_hash,
                "values": [asdict(value) for value in values],
                }
                snapshot_bytes = canonical_bytes(snapshot)
                snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
                snapshot_path = OUTPUT / "snapshots" / f"{planned['observation_id']}.json"
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                snapshot_path.write_bytes(snapshot_bytes)
                observations.append(
                {
                    "observation_id": planned["observation_id"],
                    "ticker": ticker,
                    "cik": cik,
                    "sector": planned["sector"],
                    "fiscal_year": int(planned["fiscal_year"]),
                    "period_end": filing["period_end"],
                    "filing_date": filing["filing_date"],
                    "accession": filing["accession"],
                    "source_url": str(snapshot_path.relative_to(ROOT)).replace("\\", "/"),
                    "companyfacts_url": f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
                    "filing_url": filing_url,
                    "source_hash": snapshot_hash,
                    "raw_source_hash": raw_hash,
                    "filing_hash": filing_hash,
                    "source_available_time": cutoff,
                    "information_cutoff": cutoff,
                    "outcome_window_end": (date.fromisoformat(cutoff[:10]) + timedelta(days=365)).isoformat(),
                    "split": planned["split"],
                    "annotation_status": "pending",
                    "snapshot": str(snapshot_path.relative_to(ROOT)).replace("\\", "/"),
                    "label_generated_by": "independent_reviewers",
                    "system_score_used_as_label": False,
                }
                )
                manifest_path.write_text(json.dumps(observations, indent=2), encoding="utf-8")
            except ACQUISITION_ERRORS as exc:
                failures.append({"observation_id": planned["observation_id"], "error_type": type(exc).__name__, "detail": str(exc)})
    integrity = validate_dataset_integrity(observations)
    if observations and not integrity["valid"]:
        raise RuntimeError(f"integrity gate stopped corpus: {integrity['errors']}")
    manifest_path.write_text(json.dumps(observations, indent=2), encoding="utf-8")
    (OUTPUT / "acquisition_integrity.json").write_text(json.dumps(integrity, indent=2), encoding="utf-8")
    (OUTPUT / "acquisition_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    status = {
        "dataset": "FinRisk Evaluation Corpus v1",
        "target_observations": 90,
        "real_observations_acquired": len(observations),
        "failed_observations": len(failures),
        "status": "ACQUIRED" if len(observations) == 90 and integrity["valid"] else "INSUFFICIENT_DATA",
        "integrity_gate": integrity["gate"],
        "source": "SEC official endpoints",
        "synthetic_data_used": False,
    }
    (OUTPUT / "corpus_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(f"acquired {len(observations)}/90 PIT observations; failures={len(failures)}; integrity={integrity['gate']}")


if __name__ == "__main__":
    main()
