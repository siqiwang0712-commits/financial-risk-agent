"""Run the explicitly post-hoc GPT-5 comparator without persisting credentials."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from finrisk.e4_agent import packet
from finrisk.e4_core import canonical_hash, read_json, write_json
from finrisk.e4_evaluation import performance

PROVIDER = "https://api.chatanywhere.tech"
MODEL = "gpt-5"
REPRESENTATIONS = ("A0", "A1", "A2")
SYSTEM_PROMPT = """You are a structured financial-risk reasoning comparator. Judge every case independently. Never compare, rank, normalize, or transfer evidence across cases. Use only the supplied case packet. A risk_score is an uncalibrated heuristic index, not a probability. Return only the required JSON. Keep each summary under 24 words."""
TEMPERATURE = 1
MAX_COMPLETION_TOKENS = 10000
BATCH_TARGET = 25
OUTPUT = ROOT / "research/e4_posthoc/gpt5_comparator"
ARTIFACTS = ROOT / "research/e4/_artifacts"


def _headers() -> dict[str, str]:
    key = os.environ.get("CHATANYWHERE_API_KEY")
    if not key:
        raise RuntimeError("CHATANYWHERE_API_KEY is required")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _request(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 900) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    request = urllib.request.Request(PROVIDER.rstrip("/") + path, data=body, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        safe = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"provider HTTP {exc.code}: {safe}") from exc


def _model_discovery() -> tuple[dict[str, Any], int | None]:
    listing = _request("GET", "/v1/models", timeout=60)
    models = listing.get("data", [])
    exact = [row for row in models if row.get("id") == MODEL]
    if len(exact) != 1:
        available = sorted(str(row.get("id")) for row in models if row.get("id"))
        write_json(OUTPUT / "model_discovery.json", {"provider": PROVIDER, "exact_model": MODEL, "available_model_ids": available, "exact_available": False})
        raise RuntimeError("exact gpt-5 is unavailable; no fallback is permitted")
    detail = exact[0]
    try:
        detail_response = _request("GET", f"/v1/models/{MODEL}", timeout=60)
        if isinstance(detail_response, dict):
            detail = {**detail, **detail_response}
    except RuntimeError:
        pass
    context = next((detail.get(key) for key in ("context_window", "context_length", "max_context_length", "max_model_len") if isinstance(detail.get(key), int)), None)
    public_detail = {key: value for key, value in detail.items() if key.lower() not in {"api_key", "authorization"}}
    write_json(OUTPUT / "model_discovery.json", {"provider": PROVIDER, "exact_model": MODEL, "exact_available": True, "model_metadata": public_detail, "context_limit": context})
    return public_detail, context


def _schema(max_items: int) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["results"],
        "properties": {"results": {"type": "array", "minItems": 1, "maxItems": max_items, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["case_id", "risk_score", "reason_codes", "summary"],
            "properties": {
                "case_id": {"type": "string"}, "risk_score": {"type": "number", "minimum": 0, "maximum": 1},
                "reason_codes": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "summary": {"type": "string", "maxLength": 240},
            },
        }}},
    }


def _payload(representation: str, packets: list[dict[str, Any]]) -> dict[str, Any]:
    user = {
        "representation": representation,
        "instructions": "Assess each case independently. Do not rank cases, compare companies, normalize within the batch, or transfer evidence between cases.",
        "cases": packets,
    }
    return {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(user, sort_keys=True, separators=(",", ":"))}],
        "temperature": TEMPERATURE,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_schema", "json_schema": {"name": "e4_posthoc_comparator", "strict": True, "schema": _schema(len(packets))}},
    }


def _parse(response: dict[str, Any], expected: list[str]) -> list[dict[str, Any]]:
    content = response["choices"][0]["message"]["content"]
    rows = json.loads(content)["results"]
    ids = [row.get("case_id") for row in rows]
    if sorted(ids) != sorted(expected) or len(ids) != len(set(ids)):
        raise ValueError("GPT-5 output IDs do not exactly match input IDs")
    for row in rows:
        score = row.get("risk_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("GPT-5 risk_score is invalid")
        if not isinstance(row.get("reason_codes"), list) or not all(isinstance(item, str) for item in row["reason_codes"]):
            raise ValueError("GPT-5 reason_codes are invalid")
        if not isinstance(row.get("summary"), str):
            raise TypeError("GPT-5 summary is invalid")
    return sorted(rows, key=lambda row: row["case_id"])


def _call(payload: dict[str, Any], expected: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    errors = []
    for attempt in (1, 2):
        started = time.monotonic()
        try:
            response = _request("POST", "/v1/chat/completions", payload)
            parsed = _parse(response, expected)
            safe_response = {
                "model": response.get("model"), "usage": response.get("usage"),
                "finish_reasons": [item.get("finish_reason") for item in response.get("choices", [])],
                "content": response["choices"][0]["message"]["content"],
            }
            return parsed, {"attempt": attempt, "latency_ms": round((time.monotonic() - started) * 1000, 3), "response": safe_response}
        except (RuntimeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"attempt": attempt, "error": type(exc).__name__, "message": str(exc)[:1000]})
    raise RuntimeError(json.dumps(errors, separators=(",", ":")))


def _smoke(first_packet: dict[str, Any]) -> dict[str, Any]:
    payload = _payload("A0", [first_packet])
    parsed, raw = _call(payload, [first_packet["case_id"]])
    return {"schema_valid": True, "model": MODEL, "request_hash": canonical_hash(payload), "result": parsed, "transport": raw}


def _build_batches(rows: list[dict[str, Any]], context_limit: int) -> dict[str, Any]:
    budget = int(context_limit * 0.70)
    batches = []
    for representation in REPRESENTATIONS:
        packets = [packet(row, representation) for row in rows]
        for start in range(0, len(packets), BATCH_TARGET):
            candidate = packets[start:start + BATCH_TARGET]
            estimated = math.ceil(len(json.dumps(_payload(representation, candidate), ensure_ascii=False)) / 4)
            if estimated > budget:
                raise RuntimeError(f"{representation} batch exceeds 70% confirmed context budget")
            batches.append({
                "batch_id": f"GPT5-{representation}-{start // BATCH_TARGET + 1:04d}", "representation": representation,
                "case_ids": [item["case_id"] for item in candidate], "packet_hashes": [canonical_hash(item) for item in candidate],
                "estimated_input_tokens": estimated, "packets": candidate,
            })
    return {
        "status": "POST_HOC", "provider": PROVIDER, "model": MODEL, "temperature": TEMPERATURE,
        "max_completion_tokens": MAX_COMPLETION_TOKENS, "context_limit": context_limit, "context_budget": budget,
        "target_batch_size": BATCH_TARGET, "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "retry": "one exact retry; no prompt/model/feature changes", "batches": batches,
    }


def _evaluate(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = {row["observation_id"]: row for row in read_json(ARTIFACTS / "outcomes.json")}
    b6 = {row["observation_id"]: row for row in read_json(ARTIFACTS / "numeric_predictions.json") if row["model_id"] == "B6"}
    rows = []
    for row in predictions:
        outcome = outcomes[row["observation_id"]]
        if outcome["label_status"] == "VERIFIED":
            rows.append({**row, "label": outcome["financial_deterioration_12m"], "sector": "MASKED"})
    summaries = {model: performance([row for row in rows if row["model_id"] == model]) for model in REPRESENTATIONS}
    a2 = {row["observation_id"]: row for row in rows if row["model_id"] == "A2"}
    hybrid = []
    for observation_id in sorted(a2):
        score = 0.5 * float(b6[observation_id]["score"]) + 0.5 * float(a2[observation_id]["score"])
        hybrid.append({**a2[observation_id], "model_id": "GPT5_H0_POSTHOC", "score": score})
    summaries["GPT5_H0_POSTHOC"] = performance(hybrid)
    return {"status": "POST_HOC_EXPLORATORY_ANALYSIS", "reliability": "UNCALIBRATED", "summaries": summaries, "claim_boundary": "Does not modify or confirm E4 P1/P2/P3 and cannot be described as validated, confirmed, established, or prospective."}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "batch_manifest.json").exists() or (OUTPUT / "predictions.json").exists():
        raise RuntimeError("refusing to overwrite an existing GPT-5 comparator run")
    metadata, context_limit = _model_discovery()
    feature_report = read_json(ARTIFACTS / "feature_report.json")
    selected = set(feature_report["e4b_ids"])
    rows = [row for row in read_json(ARTIFACTS / "features.json") if row["observation_id"] in selected]
    smoke = _smoke(packet(rows[0], "A0"))
    write_json(OUTPUT / "structured_smoke.json", smoke)
    if context_limit is None:
        write_json(OUTPUT / "BLOCKED.json", {"reason": "Exact gpt-5 was available and schema smoke passed, but the provider did not expose a confirmable context limit. No batch inference was run."})
        raise RuntimeError("provider did not expose a confirmable gpt-5 context limit")
    manifest = _build_batches(rows, context_limit)
    write_json(OUTPUT / "batch_manifest.json", manifest, frozen=True)
    by_case = {row["masked_company_id"]: row for row in rows}
    predictions, raw = [], []
    for batch in manifest["batches"]:
        payload = _payload(batch["representation"], batch["packets"])
        parsed, transport = _call(payload, batch["case_ids"])
        raw.append({"batch_id": batch["batch_id"], "request_hash": canonical_hash(payload), "transport": transport})
        for result in parsed:
            source = by_case[result["case_id"]]
            predictions.append({
                "observation_id": source["observation_id"], "masked_company_id": result["case_id"],
                "model_id": batch["representation"], "score": round(float(result["risk_score"]), 10),
                "prediction": int(float(result["risk_score"]) >= 0.5), "coverage": 1.0, "abstained": False,
                "reason_codes": result["reason_codes"], "summary": result["summary"],
                "input_hash": canonical_hash(packet(source, batch["representation"])), "config_hash": canonical_hash(manifest),
            })
    predictions.sort(key=lambda row: (row["observation_id"], row["model_id"]))
    write_json(OUTPUT / "predictions.json", predictions, frozen=True)
    write_json(OUTPUT / "raw_responses.json", raw, frozen=True)
    write_json(OUTPUT / "results.json", _evaluate(predictions), frozen=True)
    write_json(OUTPUT / "run_summary.json", {"status": "POST_HOC", "provider": PROVIDER, "model": MODEL, "model_metadata": metadata, "prediction_count": len(predictions), "batch_count": len(manifest["batches"]), "prediction_hash": canonical_hash(predictions)}, frozen=True)
    (OUTPUT / "STATUS.md").write_text("# Post-hoc GPT-5 External Comparator\n\nStatus: **COMPLETED — POST-HOC ONLY**\n\nThis run used exact `gpt-5` through the frozen provider and batches. It does not modify E4 confirmatory evidence. See `results.json`.\n", encoding="utf-8")
    print(json.dumps({"status": "POST_HOC_COMPLETED", "model": MODEL, "predictions": len(predictions), "batches": len(manifest["batches"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
