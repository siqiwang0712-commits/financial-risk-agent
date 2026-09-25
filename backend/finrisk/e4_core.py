"""Deterministic, point-in-time data path for the frozen E4 study.

This module is research-only.  It reuses the v0.3.4 scoring functions while
keeping cohort discovery, feature construction, and future outcomes in
separate state-machine stages.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any

from .facts import build_facts
from .metrics import calculate_metrics
from .models import altman_z, beneish_m, ohlson_o, piotroski_f
from .numeric_benchmark import LogisticBaseline, ratio_risk_score, temporal_risk_score
from .research_eval import _model_probability
from .rules import RuleEngine
from .sec_bulk import CONCEPT_ALIASES, INSTANT_FIELDS, add_twelve_months

SOURCE_COMMIT = "4273b070678240fe7cbdf01a17527afcc71c500e"
SOURCE_TAG = "v0.3.4"
FEATURE_ARCHIVES = ("2024q3.zip", "2024q4.zip", "2025q1.zip", "2025q2.zip")
OUTCOME_ARCHIVES = ("2025q3.zip", "2025q4.zip", "2026q1.zip", "2026q2.zip")
REQUIRED_MEMBERS = frozenset({"sub.txt", "num.txt", "tag.txt", "pre.txt", "readme.htm"})
PREVIOUS_270_SHA256 = "d73b371ccb026f556387cf6ff8ba204a4fde0664dcd780f099f12aa005e36603"
SELECTION_SALT = "finrisk-e4-cohort-v1:"
AGENT_SALT = "finrisk-e4-agent-v1:"
STABILITY_SALT = "finrisk-e4-stability-v1:"
BATCH_SENSITIVITY_SALT = "finrisk-e4-batch-sensitivity-v1:"
MAX_COHORT = 2000
AGENT_COHORT_LIMIT = 50
STABILITY_LIMIT = 20
BATCH_SENSITIVITY_LIMIT = 10

EXTENDED_ALIASES: dict[str, tuple[str, ...]] = {
    **CONCEPT_ALIASES,
    "retained_earnings": ("RetainedEarningsAccumulatedDeficit",),
    "ppe": ("PropertyPlantAndEquipmentNet",),
    "depreciation": ("DepreciationDepletionAndAmortization", "Depreciation"),
    "sga": (
        "SellingGeneralAndAdministrativeExpense",
        "SellingAndMarketingExpense",
    ),
    "shares_outstanding": (
        "CommonStocksIncludingAdditionalPaidInCapitalMember",
        "CommonStockSharesOutstanding",
    ),
}

SHARE_FIELDS = frozenset({"shares_outstanding"})
E4_INSTANT_FIELDS = frozenset(INSTANT_FIELDS) | SHARE_FIELDS | frozenset(
    {"retained_earnings", "ppe"}
)


class Stage(IntEnum):
    INIT = 0
    INPUTS_VERIFIED = 1
    LOCAL_AGENT_VERIFIED = 2
    PROTOCOL_FROZEN = 3
    COHORT_FROZEN = 4
    FEATURES_FROZEN = 5
    PREDICTIONS_FROZEN = 6
    OUTCOMES_FROZEN = 7
    EVALUATED = 8
    REPRODUCED = 9
    README_RENDERED = 10


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any, *, frozen: bool = False) -> None:
    if frozen and path.exists():
        raise RuntimeError(f"refusing to overwrite frozen artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class StudyState:
    def __init__(self, artifacts: Path):
        self.artifacts = artifacts
        self.path = artifacts / "state.json"

    @property
    def stage(self) -> Stage:
        if not self.path.exists():
            return Stage.INIT
        return Stage[read_json(self.path)["stage"]]

    def require(self, expected: Stage) -> None:
        if self.stage != expected:
            raise RuntimeError(f"illegal E4 transition: expected {expected.name}, found {self.stage.name}")

    def advance(self, expected: Stage, target: Stage, evidence: dict[str, Any]) -> None:
        self.require(expected)
        if target.value != expected.value + 1:
            raise RuntimeError("state transitions must advance exactly one stage")
        previous = read_json(self.path).get("history", []) if self.path.exists() else []
        record = {
            "stage": target.name,
            "evidence": evidence,
            "history": previous + [{"from": expected.name, "to": target.name, "evidence": evidence}],
        }
        write_json(self.path, record)

    def snapshot(self) -> dict[str, Any]:
        return read_json(self.path) if self.path.exists() else {"stage": Stage.INIT.name, "history": []}


def git_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify_source(root: Path) -> dict[str, str]:
    commit = git_commit(root)
    if commit != SOURCE_COMMIT:
        raise RuntimeError(f"E4 requires {SOURCE_COMMIT}; found {commit}")
    tag = subprocess.run(
        ["git", "-C", str(root), "describe", "--exact-match", "--tags", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tag != SOURCE_TAG:
        raise RuntimeError(f"E4 requires tag {SOURCE_TAG}; found {tag}")
    return {"commit": commit, "tag": tag}


def verify_previous_270(path: Path) -> dict[str, Any]:
    file_hash = sha256_file(path)
    rows = read_json(path)
    if file_hash != PREVIOUS_270_SHA256 or not isinstance(rows, list) or len(rows) != 270:
        raise RuntimeError("previous external-validation cohort is not the exact frozen 270-item artifact")
    ciks = [str(row["cik"]).zfill(10) for row in rows]
    if len(set(ciks)) != 270:
        raise RuntimeError("previous 270 cohort contains duplicate or invalid CIKs")
    return {"sha256": file_hash, "count": len(ciks), "cik_set_hash": canonical_hash(sorted(ciks))}


def _zip_inventory(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC failure in {path.name}: {bad}")
        members = {item.filename.lower(): item for item in archive.infolist() if not item.is_dir()}
        missing = sorted(REQUIRED_MEMBERS - set(members))
        if missing:
            raise RuntimeError(f"{path.name} missing required members: {missing}")
        details = [
            {
                "name": item.filename,
                "bytes": item.file_size,
                "compressed_bytes": item.compress_size,
                "crc32": f"{item.CRC:08x}",
            }
            for item in sorted(archive.infolist(), key=lambda entry: entry.filename.lower())
            if not item.is_dir()
        ]
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "crc": "PASS",
        "members": details,
    }


def verify_inputs(feature_dir: Path, outcome_dir: Path, zenodo_dir: Path, previous_270: Path) -> dict[str, Any]:
    archives = []
    for name in FEATURE_ARCHIVES:
        archives.append({**_zip_inventory(feature_dir / name), "role": "feature"})
    for name in OUTCOME_ARCHIVES:
        archives.append({**_zip_inventory(outcome_dir / name), "role": "outcome"})
    zenodo = []
    for name in ("companies.csv.gz", "us-public-company-fundamentals.csv.gz", "README.md"):
        path = zenodo_dir / name
        if path.exists():
            zenodo.append({"name": name, "bytes": path.stat().st_size, "sha256": sha256_file(path), "md5": md5_file(path)})
    previous = verify_previous_270(previous_270)
    return {
        "status": "VERIFIED",
        "archives": archives,
        "previous_270": previous,
        "zenodo": zenodo,
        "inventory_hash": canonical_hash({"archives": archives, "previous_270": previous, "zenodo": zenodo}),
    }


def _archive_member(archive: zipfile.ZipFile, name: str) -> zipfile.ZipExtFile:
    names = {entry.filename.lower(): entry.filename for entry in archive.infolist()}
    return archive.open(names[name.lower()])


def _rows(path: Path, member: str) -> Iterable[dict[str, str]]:
    import io

    with zipfile.ZipFile(path) as archive, _archive_member(archive, member) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
        yield from csv.DictReader(text, delimiter="\t")


def sic_stratum(sic: int) -> str:
    if 100 <= sic <= 999:
        return "Agriculture"
    if 1000 <= sic <= 1499:
        return "Mining"
    if 1500 <= sic <= 1799:
        return "Construction"
    if 2000 <= sic <= 3999:
        return "Manufacturing"
    if 4000 <= sic <= 4999:
        return "Transportation_Utilities"
    if 5000 <= sic <= 5199:
        return "Wholesale"
    if 5200 <= sic <= 5999:
        return "Retail"
    if 7000 <= sic <= 8999:
        return "Services"
    if 9100 <= sic <= 9729:
        return "Public_Administration"
    return "Other_Nonfinancial"


def discover_filings(feature_dir: Path, excluded_ciks: set[str]) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for name in FEATURE_ARCHIVES:
        path = feature_dir / name
        archive_hash = sha256_file(path)
        for row in _rows(path, "sub.txt"):
            cik = str(row.get("cik", "")).zfill(10)
            filed = str(row.get("filed", ""))
            accession = str(row.get("adsh", ""))
            try:
                sic = int(row.get("sic") or 0)
            except ValueError:
                continue
            if (
                row.get("form") != "10-K"
                or str(row.get("fy")) != "2024"
                or not ("20240701" <= filed <= "20250630")
                or 6000 <= sic <= 6999
                or cik in excluded_ciks
                or not re.fullmatch(r"\d{10}", cik)
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession)
                or not re.fullmatch(r"\d{8}", str(row.get("period", "")))
            ):
                continue
            candidate = {
                "cik": cik,
                "accession": accession,
                "company_name": str(row.get("name", "")),
                "sic": sic,
                "sector": sic_stratum(sic),
                "period": str(row["period"]),
                "filed": filed,
                "accepted": str(row.get("accepted") or filed),
                "source_archive": name,
                "source_hash": archive_hash,
            }
            previous = candidates.get(cik)
            if previous is None or (filed, accession) < (previous["filed"], previous["accession"]):
                candidates[cik] = candidate
    return sorted(candidates.values(), key=lambda row: row["cik"])


def _unit_allowed(field: str, unit: str) -> bool:
    return unit == "shares" if field in SHARE_FIELDS else unit == "USD"


def _select(rows: list[dict[str, str]], field: str, period: str) -> tuple[float | None, dict[str, Any] | None]:
    aliases = EXTENDED_ALIASES[field]
    candidates: list[tuple[int, str, float, dict[str, str]]] = []
    for row in rows:
        if (
            row.get("tag") not in aliases
            or row.get("ddate") != period
            or not _unit_allowed(field, str(row.get("uom", "")))
            or (row.get("coreg") or "").strip()
            or (row.get("segments") or "").strip()
        ):
            continue
        qtrs = str(row.get("qtrs", ""))
        if field in E4_INSTANT_FIELDS and qtrs not in {"0", ""}:
            continue
        if field not in E4_INSTANT_FIELDS and qtrs not in {"4", "", "0"}:
            continue
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        candidates.append((aliases.index(str(row["tag"])), str(row["tag"]), value, row))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _, tag, value, row = candidates[0]
    return value, {
        "concept": tag,
        "period_end": period,
        "unit": row.get("uom"),
        "source_row": {key: row.get(key) for key in ("adsh", "tag", "version", "ddate", "qtrs", "uom", "coreg", "segments")},
    }


def _comparative_period(rows: list[dict[str, str]], current_period: str) -> str | None:
    current = date(int(current_period[:4]), int(current_period[4:6]), int(current_period[6:8]))
    target_year = current.year - 1
    try:
        target = current.replace(year=target_year)
    except ValueError:
        target = current.replace(year=target_year, day=28)
    dates = set()
    for row in rows:
        value = str(row.get("ddate", ""))
        if value.isdigit() and len(value) == 8:
            try:
                parsed = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
            except ValueError:
                continue
            if parsed.year == target_year and 300 <= (current - parsed).days <= 430:
                dates.add(value)
    ranked = []
    for value in dates:
        completeness = sum(_select(rows, field, value)[0] is not None for field in EXTENDED_ALIASES)
        parsed = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        day_gap = abs((parsed - target).days)
        ranked.append((-completeness, day_gap, value))
    return min(ranked)[2] if ranked else None


def extract_candidate_facts(feature_dir: Path, filings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_archive: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for filing in filings:
        by_archive[filing["source_archive"]][filing["accession"]] = filing
    output = []
    for archive_name in FEATURE_ARCHIVES:
        wanted = by_archive.get(archive_name, {})
        if not wanted:
            continue
        rows_by_accession: dict[str, list[dict[str, str]]] = defaultdict(list)
        aliases = {alias for values in EXTENDED_ALIASES.values() for alias in values}
        for row in _rows(feature_dir / archive_name, "num.txt"):
            accession = str(row.get("adsh", ""))
            if accession in wanted and row.get("tag") in aliases:
                rows_by_accession[accession].append(row)
        for accession, filing in wanted.items():
            filing_rows = rows_by_accession.get(accession, [])
            previous_period = _comparative_period(filing_rows, filing["period"])
            current: dict[str, float | None] = {}
            previous: dict[str, float | None] = {}
            provenance: dict[str, Any] = {}
            for field in EXTENDED_ALIASES:
                current[field], provenance[field] = _select(filing_rows, field, filing["period"])
                previous[field] = _select(filing_rows, field, previous_period)[0] if previous_period else None
            for facts in (current, previous):
                if facts.get("total_debt") is None and facts.get("short_term_debt") is not None and facts.get("long_term_debt") is not None:
                    facts["total_debt"] = float(facts["short_term_debt"]) + float(facts["long_term_debt"])
            metrics = calculate_metrics(current, 2024, previous)
            metric_values = {key: value.value for key, value in metrics.items()}
            usable = ratio_risk_score(metric_values) is not None and any(
                metric_values.get(key) is not None
                for key in ("revenue_growth", "operating_cash_flow_growth", "total_debt_growth", "cash_growth")
            )
            if usable:
                output.append({**filing, "previous_period": previous_period, "current": current, "previous": previous, "provenance": provenance})
    return sorted(output, key=lambda row: row["cik"])


def _stratified_sample(rows: list[dict[str, Any]], limit: int = MAX_COHORT) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return sorted(rows, key=lambda row: row["cik"])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["sector"]].append(row)
    exact = {key: limit * len(values) / len(rows) for key, values in groups.items()}
    quotas = {key: int(value) for key, value in exact.items()}
    remaining = limit - sum(quotas.values())
    order = sorted(groups, key=lambda key: (-(exact[key] - quotas[key]), key))
    for key in order[:remaining]:
        quotas[key] += 1
    sampled = []
    for key in sorted(groups):
        ranked = sorted(groups[key], key=lambda row: (hashlib.sha256(f"{SELECTION_SALT}{row['cik']}".encode()).hexdigest(), row["cik"]))
        sampled.extend(ranked[: quotas[key]])
    return sorted(sampled, key=lambda row: row["cik"])


def build_cohort(root: Path, feature_dir: Path, previous_270: Path, cache: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    previous_rows = read_json(previous_270)
    previous_ciks = {str(row["cik"]).zfill(10) for row in previous_rows}
    development = read_json(root / "research/empirical_v1/numeric_corpus.json")
    development_ciks = {str(row["cik"]).zfill(10) for row in development}
    public_payload = read_json(root / "research/benchmark/public_company_observations.json")
    public_rows = public_payload.get("examples", [])
    public_ciks = {str(row.get("cik", "")).zfill(10) for row in public_rows if row.get("cik")}
    excluded = previous_ciks | development_ciks | public_ciks
    discovered = discover_filings(feature_dir, excluded)
    usable = extract_candidate_facts(feature_dir, discovered)
    selected = _stratified_sample(usable)
    plan = []
    for index, row in enumerate(sorted(selected, key=lambda item: (hashlib.sha256(f"{SELECTION_SALT}{item['cik']}".encode()).hexdigest(), item["cik"])), 1):
        plan.append({
            "observation_id": f"E4_OBS_{index:06d}",
            "masked_company_id": f"E4_COMPANY_{index:06d}",
            "cik": row["cik"],
            "accession": row["accession"],
            "sic": row["sic"],
            "sector": row["sector"],
            "period": row["period"],
            "previous_period": row["previous_period"],
            "filed": row["filed"],
            "accepted": row["accepted"],
            "source_archive": row["source_archive"],
            "source_hash": row["source_hash"],
            "selection_hash": hashlib.sha256(f"{SELECTION_SALT}{row['cik']}".encode()).hexdigest(),
        })
    cache_rows = {row["cik"]: row for row in usable if row["cik"] in {item["cik"] for item in plan}}
    write_json(cache / "selected_feature_material.json", cache_rows)
    report = {
        "discovered_original_fy2024_10k": len(discovered),
        "usable_before_sampling": len(usable),
        "selected": len(plan),
        "sampling_applied": len(usable) > MAX_COHORT,
        "sector_counts": dict(sorted(Counter(item["sector"] for item in plan).items())),
        "excluded_previous_270": len(previous_ciks),
        "previous_270_hash": sha256_file(previous_270),
        "company_disjoint": not bool({item["cik"] for item in plan} & excluded),
    }
    return plan, report


def _accepted(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit()).ljust(14, "0")[:14]
    return datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def build_features(plan: list[dict[str, Any]], cached_material: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    observations = []
    for item in plan:
        source = cached_material[item["cik"]]
        accepted = _accepted(item["accepted"] or item["filed"])
        filed_at = f"{item['filed'][:4]}-{item['filed'][4:6]}-{item['filed'][6:8]}T23:59:59Z"
        cutoff = max(accepted, filed_at)
        metrics = calculate_metrics(source["current"], 2024, source["previous"])
        observations.append({
            "observation_id": item["observation_id"],
            "masked_company_id": item["masked_company_id"],
            "cik": item["cik"],
            "accession": item["accession"],
            "sic": item["sic"],
            "sector": item["sector"],
            "fiscal_year": 2024,
            "period_end": f"{item['period'][:4]}-{item['period'][4:6]}-{item['period'][6:8]}",
            "filing_date": filed_at[:10],
            "information_cutoff": cutoff,
            "outcome_window_end": add_twelve_months(datetime.fromisoformat(cutoff)).isoformat().replace("+00:00", "Z"),
            "source_archive": item["source_archive"],
            "source_hash": item["source_hash"],
            "current": source["current"],
            "previous": source["previous"],
            "metrics": {key: value.value for key, value in metrics.items()},
            "provenance": source["provenance"],
        })
    observations.sort(key=lambda row: row["observation_id"])
    e4b = sorted(observations, key=lambda row: (hashlib.sha256(f"{AGENT_SALT}{row['masked_company_id']}".encode()).hexdigest(), row["masked_company_id"]))[:AGENT_COHORT_LIMIT]
    stability = sorted(e4b, key=lambda row: hashlib.sha256(f"{STABILITY_SALT}{row['masked_company_id']}".encode()).hexdigest())[:STABILITY_LIMIT]
    batch = sorted(e4b, key=lambda row: hashlib.sha256(f"{BATCH_SENSITIVITY_SALT}{row['masked_company_id']}".encode()).hexdigest())[:BATCH_SENSITIVITY_LIMIT]
    report = {
        "e4a_count": len(observations),
        "e4b_ids": [row["observation_id"] for row in e4b],
        "stability_ids": [row["observation_id"] for row in stability],
        "batch_sensitivity_ids": [row["observation_id"] for row in batch],
        "feature_hash": canonical_hash(observations),
        "same_filing_comparatives": all(row["previous"] for row in observations),
    }
    return observations, report


def _entity_type(sic: int) -> str:
    return "public_manufacturer" if 2000 <= sic <= 3999 else "non_manufacturer"


def _models(row: dict[str, Any]) -> list[Any]:
    current = dict(row["current"])
    previous = dict(row["previous"])
    metrics = calculate_metrics(current, 2024, previous)
    model_input = {
        **current,
        "working_capital": metrics["working_capital"].value,
        "ebit": current.get("ebit") if current.get("ebit") is not None else current.get("operating_income"),
        "prior_net_income": previous.get("net_income"),
        "funds_from_operations": None,
        "gnp_price_index": None,
        "market_value_equity": None,
    }
    return [
        altman_z(model_input, _entity_type(int(row["sic"]))),
        beneish_m(current, previous),
        piotroski_f(current, previous),
        ohlson_o(model_input),
    ]


def fit_historical_logistic(root: Path) -> tuple[LogisticBaseline, dict[str, Any]]:
    observations = read_json(root / "research/empirical_v1/numeric_corpus.json")
    labels = read_json(root / "research/empirical_v1/deterioration_labels.json")
    by_id = {
        row["observation_id"]: int(row["financial_deterioration_12m"])
        for row in labels
        if row.get("label_status") == "VERIFIED" and row.get("financial_deterioration_12m") in {0, 1}
    }
    rows = [row for row in observations if row["observation_id"] in by_id]
    model = LogisticBaseline().fit(rows, [by_id[row["observation_id"]] for row in rows])
    return model, {
        "development_observations": len(rows),
        "development_companies": len({row["cik"] for row in rows}),
        "events": sum(by_id[row["observation_id"]] for row in rows),
        "means": model.means,
        "scales": model.scales,
        "weights": model.weights,
    }


def _record(row: dict[str, Any], model_id: str, score: float | None, coverage: float, reason_codes: list[str]) -> dict[str, Any]:
    return {
        "observation_id": row["observation_id"],
        "masked_company_id": row["masked_company_id"],
        "model_id": model_id,
        "score": None if score is None else round(float(score), 10),
        "prediction": None if score is None else int(float(score) >= 0.5),
        "coverage": round(coverage, 10),
        "abstained": score is None,
        "reason_codes": reason_codes,
        "input_hash": canonical_hash({"current": row["current"], "previous": row["previous"], "metrics": row["metrics"]}),
        "config_hash": "",
    }


def run_numeric(root: Path, observations: list[dict[str, Any]], config_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    logistic, logistic_manifest = fit_historical_logistic(root)
    logistic_scores = logistic.predict_scores(observations)
    rules = RuleEngine.from_file(root / "rules/rules.json")
    output = []
    for row, b1 in zip(observations, logistic_scores, strict=True):
        metrics = row["metrics"]
        models = _models(row)
        metric_count = sum(value is not None for value in metrics.values())
        current_metrics = calculate_metrics(row["current"], 2024, row["previous"])
        facts = build_facts(row["current"], row["previous"], 2024, current_metrics, models)
        signals = rules.evaluate(facts)
        b2 = min(1.0, sum(signal.score_delta for signal in signals if not signal.rule_id.startswith("MODEL_")) / 80)
        scores = {
            "B0": ratio_risk_score(metrics),
            "B1": b1,
            "B2": b2,
            "B3": _model_probability(type("Assessment", (), {"models": models})()),
            "B6": temporal_risk_score(metrics),
        }
        reasons = {
            "B0": [name for name in ("current_ratio", "debt_to_assets", "net_margin", "cfo_to_net_income", "fcf_margin") if metrics.get(name) is not None],
            "B1": ["HISTORICAL_LOGISTIC_V034"],
            "B2": [signal.rule_id for signal in signals],
            "B3": [f"{model.name}:{model.applicability}" for model in models],
            "B6": [name for name in ("revenue_growth", "operating_cash_flow_growth", "total_debt_growth", "cash_growth") if metrics.get(name) is not None],
        }
        for model_id, score in scores.items():
            coverage = metric_count / max(1, len(metrics)) if model_id in {"B0", "B1", "B2", "B6"} else sum(model.output is not None for model in models) / len(models)
            record = _record(row, model_id, score, coverage, reasons[model_id])
            record["config_hash"] = config_hash
            output.append(record)
    output.sort(key=lambda record: (record["observation_id"], record["model_id"]))
    return output, {"logistic": logistic_manifest, "prediction_count": len(output), "models": ["B0", "B1", "B2", "B3", "B6"]}
