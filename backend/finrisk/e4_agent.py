"""Frozen local-Agent packets, batching, execution, and replay for E4."""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .e4_core import _models, canonical_hash

REPRESENTATIONS = ("A0", "A1", "A2")
MODEL = "qwen2.5:0.5b"
MODEL_DIGEST = "a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67"
MODEL_BLOB_DIGEST = "c5396e06af29"
RUNTIME = "alpine/ollama:0.12.3"
RUNTIME_DIGEST = "sha256:8ab809d178ea5c67bfffdfece64f9d68faf2a810addfe107de864b1c76106ba5"
CONTEXT_LIMIT = 4096
CONTEXT_BUDGET = int(CONTEXT_LIMIT * 0.70)
MAX_BATCH = 25
SEED = 20260924
OPTIONS = {"temperature": 0, "seed": SEED, "num_ctx": CONTEXT_LIMIT, "num_predict": 3072, "num_thread": 8}

SYSTEM_PROMPT = (
    "You are a local financial-reasoning comparator. Judge every case independently. "
    "Never rank cases, compare cases, transfer evidence between cases, or normalize scores "
    "relative to the batch. risk_score is a heuristic index in [0,1], not probability of "
    "default. Use only the supplied case packet. Return every case_id exactly once."
)


def output_schema(case_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "cases": {
                "type": "array",
                "minItems": case_count,
                "maxItems": case_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "case_id": {"type": "string"},
                        "risk_score": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason_codes": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                        "summary": {"type": "string", "maxLength": 360},
                    },
                    "required": ["case_id", "risk_score", "reason_codes", "summary"],
                },
            }
        },
        "required": ["cases"],
    }


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def packet(row: dict[str, Any], representation: str) -> dict[str, Any]:
    if representation not in REPRESENTATIONS:
        raise ValueError(f"unknown representation: {representation}")
    missing = {
        "raw_current": sorted(key for key, value in row["current"].items() if value is None),
        "raw_previous": sorted(key for key, value in row["previous"].items() if value is None),
        "metrics": sorted(key for key, value in row["metrics"].items() if value is None),
    }
    value: dict[str, Any] = {"case_id": row["masked_company_id"]}
    if representation in {"A0", "A2"}:
        value["raw_fy2024"] = _without_none(row["current"])
        value["raw_same_filing_fy2023"] = _without_none(row["previous"])
    if representation in {"A1", "A2"}:
        value["engineered_features"] = _without_none(row["metrics"])
        value["missingness"] = missing
    if representation == "A2":
        models = _models(row)
        value["traditional_model_outputs"] = [
            {
                "model": model.name,
                "output": model.output,
                "applicability": model.applicability,
                "missing": model.missing_components,
            }
            for model in models
        ]
    forbidden = {"cik", "accession", "ticker", "company_name", "outcome", "label", "B0", "B2", "B6", "score"}
    if forbidden & set(value):
        raise RuntimeError("identity, outcome, or deterministic final score leaked into Agent packet")
    return value


def prompt_hash(representation: str) -> str:
    return canonical_hash({"system": SYSTEM_PROMPT, "representation": representation, "version": "e4-agent-prompt-v1"})


def estimate_tokens(value: Any) -> int:
    # Qwen numeric JSON measured close to two characters/token.  The estimate
    # uses the full rendered request and rounds upward; the runtime-reported
    # prompt count is also a mandatory hard gate.
    return math.ceil(len(json.dumps(value, sort_keys=True, separators=(",", ":"))) / 2)


def _preflight_tokens(representation: str, cases: list[dict[str, Any]]) -> int:
    user = json.dumps({"representation": representation, "cases": cases}, sort_keys=True, separators=(",", ":"))
    schema = json.dumps(output_schema(len(cases)), sort_keys=True, separators=(",", ":"))
    # Include chat-template and role-marker headroom measured outside either
    # case content or JSON schema.
    return math.ceil((len(SYSTEM_PROMPT) + len(user) + len(schema) + 256) / 2)


def make_batches(rows: list[dict[str, Any]], representation: str) -> list[dict[str, Any]]:
    packets = [packet(row, representation) for row in sorted(rows, key=lambda item: item["observation_id"])]
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in packets:
        candidate = current + [item]
        if current and (len(candidate) > MAX_BATCH or _preflight_tokens(representation, candidate) > CONTEXT_BUDGET):
            batches.append(current)
            current = [item]
        else:
            current = candidate
        if _preflight_tokens(representation, current) > CONTEXT_BUDGET:
            raise RuntimeError(f"single {representation} packet exceeds the frozen context budget")
    if current:
        batches.append(current)
    return [
        {
            "batch_id": f"{representation}-{index:04d}",
            "representation": representation,
            "case_ids": [item["case_id"] for item in items],
            "packet_hashes": [canonical_hash(item) for item in items],
            "estimated_input_tokens": _preflight_tokens(representation, items),
            "packets": items,
        }
        for index, items in enumerate(batches, 1)
    ]


def build_manifest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    batches = [batch for representation in REPRESENTATIONS for batch in make_batches(rows, representation)]
    return {
        "version": "e4-agent-batches-v1",
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "model_blob_digest": MODEL_BLOB_DIGEST,
        "runtime": RUNTIME,
        "runtime_digest": RUNTIME_DIGEST,
        "tokenizer": "Qwen2 BPE (GGUF metadata)",
        "quantization": "Q4_K_M",
        "context_limit": CONTEXT_LIMIT,
        "context_budget": CONTEXT_BUDGET,
        "options": OPTIONS,
        "retry_policy": "one exact retry, then deterministic left/right bisection",
        "prompt_hashes": {representation: prompt_hash(representation) for representation in REPRESENTATIONS},
        "batches": batches,
    }


def validate_agent_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "finrisk-e4-agent-api"}:
        raise RuntimeError("E4 Agent API must be localhost or the isolated internal service")


def http_transport(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    validate_agent_url(url)
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        return json.loads(response.read())


def _request(batch: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    representation = batch["representation"]
    cases = batch["packets"]
    return {
        "model": MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"representation": representation, "cases": cases}, sort_keys=True, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "e4_batch", "strict": True, "schema": output_schema(len(cases))}},
        "options": options,
    }


class AgentSchemaError(ValueError):
    """A deterministic, machine-classifiable structured-output failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _parse(response: dict[str, Any], expected_ids: list[str]) -> list[dict[str, Any]]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AgentSchemaError("MISSING_RESPONSE_CONTENT", "Agent response content is missing") from exc
    if not isinstance(content, str):
        raise AgentSchemaError("NON_STRING_CONTENT", "Agent response content is not text")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AgentSchemaError("MALFORMED_JSON", "Agent response is not valid JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("cases"), list):
        raise AgentSchemaError("MISSING_CASES_ARRAY", "Agent response has no cases array")
    cases = parsed["cases"]
    ids = [row.get("case_id") for row in cases]
    if len(ids) != len(set(ids)):
        raise AgentSchemaError("DUPLICATE_CASE_IDS", "Agent output contains duplicate case IDs")
    if sorted(ids) != sorted(expected_ids):
        raise AgentSchemaError("CASE_ID_MISMATCH", "Agent output case IDs do not exactly match the input batch")
    for row in cases:
        score = row.get("risk_score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise AgentSchemaError("NON_NUMERIC_SCORE", "Agent risk_score is not numeric")
        if not math.isfinite(float(score)) or not 0 <= score <= 1:
            raise AgentSchemaError("SCORE_OUT_OF_RANGE", "Agent risk_score is outside [0,1]")
        reason_codes = row.get("reason_codes")
        if not isinstance(reason_codes, list) or not all(isinstance(item, str) for item in reason_codes):
            raise AgentSchemaError("INVALID_REASON_CODES", "Agent reason_codes must be a string array")
        if not isinstance(row.get("summary"), str):
            raise AgentSchemaError("INVALID_SUMMARY", "Agent summary must be text")
    return sorted(cases, key=lambda row: row["case_id"])


@dataclass
class BatchResult:
    cases: list[dict[str, Any]]
    raw: list[dict[str, Any]]
    failures: list[dict[str, Any]]


Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class ContextBudgetError(RuntimeError):
    pass


def execute_batch(
    batch: dict[str, Any],
    url: str,
    transport: Transport = http_transport,
    options: dict[str, Any] | None = None,
) -> BatchResult:
    options = dict(options or OPTIONS)
    raw = []
    request = _request(batch, options)
    last_error = ""
    for attempt in (1, 2):
        started = time.monotonic()
        try:
            response = transport(url, request)
            prompt_tokens = response.get("usage", {}).get("prompt_tokens")
            if prompt_tokens is not None and int(prompt_tokens) > CONTEXT_BUDGET:
                raise ContextBudgetError(
                    f"runtime prompt count {prompt_tokens} exceeds frozen budget {CONTEXT_BUDGET}"
                )
            cases = _parse(response, batch["case_ids"])
            raw.append({"attempt": attempt, "request_hash": canonical_hash(request), "response": response, "latency_ms": round((time.monotonic() - started) * 1000, 3)})
            return BatchResult(cases, raw, [])
        except ContextBudgetError:
            raise
        except AgentSchemaError as exc:
            last_error = exc.code
            raw.append({
                "attempt": attempt,
                "request_hash": canonical_hash(request),
                "error": "AgentSchemaError",
                "error_code": exc.code,
                "response": response,
                "response_hash": canonical_hash(response),
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            })
        except (KeyError, TypeError, ValueError, OSError) as exc:
            last_error = type(exc).__name__
            raw.append({"attempt": attempt, "request_hash": canonical_hash(request), "error": last_error, "latency_ms": round((time.monotonic() - started) * 1000, 3)})
    if len(batch["packets"]) == 1:
        return BatchResult([], raw, [{"case_id": batch["case_ids"][0], "reason": "AGENT_FAILED", "error": last_error}])
    midpoint = (len(batch["packets"]) + 1) // 2
    results = []
    for suffix, packets in (("L", batch["packets"][:midpoint]), ("R", batch["packets"][midpoint:])):
        child = {
            **batch,
            "batch_id": f"{batch['batch_id']}-{suffix}",
            "packets": packets,
            "case_ids": [item["case_id"] for item in packets],
            "packet_hashes": [canonical_hash(item) for item in packets],
        }
        results.append(execute_batch(child, url, transport, options))
    return BatchResult(
        [case for result in results for case in result.cases],
        raw + [item for result in results for item in result.raw],
        [failure for result in results for failure in result.failures],
    )


def run_agent(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    config_hash: str,
    url: str,
    transport: Transport = http_transport,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_case = {row["masked_company_id"]: row for row in rows}
    predictions = []
    raw_runs = []
    failures = []
    for batch in manifest["batches"]:
        result = execute_batch(batch, url, transport)
        raw_runs.append({"batch_id": batch["batch_id"], "records": result.raw})
        failures.extend({**failure, "batch_id": batch["batch_id"], "representation": batch["representation"]} for failure in result.failures)
        for case in result.cases:
            source = by_case[case["case_id"]]
            predictions.append({
                "observation_id": source["observation_id"],
                "masked_company_id": source["masked_company_id"],
                "model_id": batch["representation"],
                "score": round(float(case["risk_score"]), 10),
                "prediction": int(float(case["risk_score"]) >= 0.5),
                "coverage": 1.0,
                "abstained": False,
                "reason_codes": case["reason_codes"],
                "summary": case["summary"],
                "input_hash": canonical_hash(packet(source, batch["representation"])),
                "config_hash": config_hash,
            })
        for failure in result.failures:
            source = by_case[failure["case_id"]]
            predictions.append({
                "observation_id": source["observation_id"],
                "masked_company_id": source["masked_company_id"],
                "model_id": batch["representation"],
                "score": None,
                "prediction": None,
                "coverage": 0.0,
                "abstained": True,
                "reason_codes": ["AGENT_FAILED"],
                "summary": "",
                "input_hash": canonical_hash(packet(source, batch["representation"])),
                "config_hash": config_hash,
            })
    predictions.sort(key=lambda row: (row["observation_id"], row["model_id"]))
    return predictions, {"raw_runs": raw_runs, "failures": failures, "prediction_count": len(predictions)}


def replay_frozen_agent(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    raw: dict[str, Any],
    config_hash: str,
) -> list[dict[str, Any]]:
    """Rebuild predictions solely from frozen HTTP responses and failures."""
    by_case = {row["masked_company_id"]: row for row in rows}
    batches = {batch["batch_id"]: batch for batch in manifest["batches"]}
    recovered: dict[tuple[str, str], dict[str, Any] | None] = {}

    for run in raw["raw_runs"]:
        batch = batches[run["batch_id"]]
        allowed = set(batch["case_ids"])
        for record in run["records"]:
            response = record.get("response")
            if response is None:
                continue
            content = json.loads(response["choices"][0]["message"]["content"])
            response_ids = [case["case_id"] for case in content["cases"]]
            if not response_ids or not set(response_ids) <= allowed:
                raise ValueError("frozen Agent response contains an unexpected case ID")
            for case in _parse(response, response_ids):
                key = (batch["representation"], case["case_id"])
                if key in recovered:
                    raise ValueError("frozen Agent responses contain a duplicate case")
                recovered[key] = case

    for failure in raw["failures"]:
        key = (failure["representation"], failure["case_id"])
        if key in recovered:
            raise ValueError("a frozen Agent case is both successful and failed")
        recovered[key] = None

    expected = {
        (batch["representation"], case_id)
        for batch in manifest["batches"]
        for case_id in batch["case_ids"]
    }
    if set(recovered) != expected:
        raise ValueError("frozen Agent replay does not cover the complete manifest")

    predictions = []
    for (representation, case_id), case in recovered.items():
        source = by_case[case_id]
        if case is None:
            score = None
            prediction = None
            coverage = 0.0
            reason_codes = ["AGENT_FAILED"]
            summary = ""
        else:
            score = round(float(case["risk_score"]), 10)
            prediction = int(score >= 0.5)
            coverage = 1.0
            reason_codes = case["reason_codes"]
            summary = case["summary"]
        predictions.append({
            "observation_id": source["observation_id"],
            "masked_company_id": case_id,
            "model_id": representation,
            "score": score,
            "prediction": prediction,
            "coverage": coverage,
            "abstained": case is None,
            "reason_codes": reason_codes,
            "summary": summary,
            "input_hash": canonical_hash(packet(source, representation)),
            "config_hash": config_hash,
        })
    return sorted(predictions, key=lambda row: (row["observation_id"], row["model_id"]))


def hybrid_predictions(numeric: list[dict[str, Any]], agent: list[dict[str, Any]], config_hash: str) -> list[dict[str, Any]]:
    b6 = {row["observation_id"]: row for row in numeric if row["model_id"] == "B6"}
    a2 = {row["observation_id"]: row for row in agent if row["model_id"] == "A2"}
    output = []
    for observation_id in sorted(set(b6) & set(a2)):
        left, right = b6[observation_id], a2[observation_id]
        score = None if left["score"] is None or right["score"] is None else 0.5 * float(left["score"]) + 0.5 * float(right["score"])
        output.append({
            "observation_id": observation_id,
            "masked_company_id": left["masked_company_id"],
            "model_id": "H0",
            "score": None if score is None else round(score, 10),
            "prediction": None if score is None else int(score >= 0.5),
            "coverage": min(float(left["coverage"]), float(right["coverage"])),
            "abstained": score is None,
            "reason_codes": ["H0_FIXED_EQUAL_WEIGHT"],
            "input_hash": canonical_hash({"B6": left["input_hash"], "A2": right["input_hash"]}),
            "config_hash": config_hash,
        })
    return output


def manifest_hash(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
