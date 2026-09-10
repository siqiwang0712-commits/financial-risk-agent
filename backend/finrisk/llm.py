from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .domain import Evidence, NarrativeClaim


class NarrativeProvider(Protocol):
    def extract(self,pages:dict[int,str],document:str,year:int)->list[NarrativeClaim]: ...


class MockNarrativeProvider:
    """Deterministic provider for tests and offline demos; never invents evidence."""
    patterns: ClassVar[dict[str, tuple[str, str]]] = {"going concern":("business_going_concern","negative"),"substantial doubt":("business_going_concern","negative"),"refinancing":("liquidity","negative"),"customer concentration":("business_going_concern","negative"),"material weakness":("governance_audit","negative"),"liquidity remains strong":("liquidity","positive"),"sufficient sources of funding":("liquidity","positive"),"will be sufficient to satisfy":("liquidity","positive")}
    def extract(self,pages,document,year):
        claims=[]
        for page,text in pages.items():
            low=text.lower()
            for phrase,(cat,polarity) in self.patterns.items():
                if phrase in low:
                    sentence=next((s.strip() for s in text.replace("\n"," ").split(".") if phrase in s.lower()),phrase)
                    before=sentence.lower().split(phrase,1)[0]
                    if any(token in before.split()[-6:] for token in ("no","not","without")):continue
                    required = []
                    qualifiers = []
                    if cat == "liquidity" and polarity == "positive":
                        required = ["liquidity_position", "cash_generation", "funding_pressure"]
                        if "marketable securities" in sentence.lower() or "short-term investments" in sentence.lower():
                            required.append("liquid_investments")
                            qualifiers.append("liquid investments")
                        if "debt market" in sentence.lower() or "credit facilit" in sentence.lower():
                            required.append("funding_access")
                            qualifiers.append("external funding access")
                    claims.append(NarrativeClaim(sentence,cat,Evidence(document,page,sentence,year,.9),polarity,"category_general",polarity,"unspecified","management_statement",tuple(qualifiers),tuple(required)))
        return claims


ALLOWED_CATEGORIES = {"liquidity", "solvency_leverage", "profitability", "cash_flow", "earnings_quality", "accounting", "governance_audit", "business_going_concern"}


class ClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=3, max_length=500)
    risk_category: str
    page: int = Field(ge=1)
    evidence_text: str = Field(min_length=3, max_length=1200)
    confidence: float = Field(ge=0, le=1)
    polarity: str
    claim_target: str = Field(min_length=2, max_length=100)
    direction: str
    time_horizon: str = Field(min_length=2, max_length=100)
    basis: str = Field(min_length=2, max_length=100)
    qualifiers: list[str] = Field(max_length=20)
    required_evidence_types: list[str] = Field(min_length=1, max_length=10)


class NarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[ClaimOutput] = Field(max_length=100)


@dataclass(frozen=True)
class LLMCallLog:
    prompt_version: str
    provider: str
    model: str
    attempt: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    status: str
    input_hash: str = ""
    schema_hash: str = ""
    temperature: float = 0.0
    max_tokens: int = 0
    retry_policy: str = ""
    schema_valid: bool = False


class StructuredLLMProvider:
    """OpenAI-compatible, schema-constrained semantic extractor.

    It returns claims only. Financial arithmetic, rules and scores remain outside
    this class. A transport can be injected so tests never require network/API keys.
    """

    PROMPT_VERSION = "narrative-v1.1.0-claim-conditioned"
    SCHEMA: ClassVar[dict[str, Any]] = {
        "name": "finrisk_narrative_claims",
        "strict": True,
        "schema": {
            "type": "object", "additionalProperties": False,
            "properties": {"claims": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"}, "risk_category": {"type": "string", "enum": sorted(ALLOWED_CATEGORIES)},
                    "page": {"type": "integer", "minimum": 1}, "evidence_text": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "polarity": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                    "claim_target": {"type": "string"},
                    "direction": {"type": "string", "enum": ["positive", "negative", "neutral", "mixed"]},
                    "time_horizon": {"type": "string"},
                    "basis": {"type": "string"},
                    "qualifiers": {"type": "array", "items": {"type": "string"}},
                    "required_evidence_types": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                }, "required": ["claim", "risk_category", "page", "evidence_text", "confidence", "polarity", "claim_target", "direction", "time_horizon", "basis", "qualifiers", "required_evidence_types"],
            }}}, "required": ["claims"],
        },
    }

    def __init__(self, api_key: str | None = None, model: str = "gpt-4.1-mini", endpoint: str = "https://api.openai.com/v1/chat/completions", max_retries: int = 2, max_tokens: int = 1200, log_path: Path | None = None, transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None, input_cost_per_million: float = 0.0, output_cost_per_million: float = 0.0):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.endpoint = endpoint
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.log_path = log_path
        self.transport = transport or self._http_transport
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.call_logs: list[LLMCallLog] = []

    def _http_transport(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured; use MockNarrativeProvider for offline execution")
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)

    def _payload(self, pages: dict[int, str], document: str, year: int) -> dict[str, Any]:
        source = "\n\n".join(f"[PAGE {page}]\n{text}" for page, text in sorted(pages.items()))
        instructions = (
            "Extract only explicitly supported management/auditor risk claims. Copy evidence_text exactly from the supplied page. "
            "For each claim identify its target, direction, time horizon, basis, qualifiers, and the evidence constructs required to test it. "
            "Never calculate financial values, risk scores, bankruptcy probabilities, or infer fraud. Return no claim when evidence is absent. "
            f"Document={document}; fiscal_year={year}; prompt_version={self.PROMPT_VERSION}."
        )
        return {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens, "messages": [{"role": "system", "content": instructions}, {"role": "user", "content": source}], "response_format": {"type": "json_schema", "json_schema": self.SCHEMA}}

    @staticmethod
    def _content(response: dict[str, Any]) -> tuple[str, int, int]:
        usage = response.get("usage", {})
        content = response["choices"][0]["message"]["content"]
        return content, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))

    def _record(self, log: LLMCallLog) -> None:
        self.call_logs.append(log)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(log), sort_keys=True) + "\n")

    def extract(self, pages: dict[int, str], document: str, year: int) -> list[NarrativeClaim]:
        payload = self._payload(pages, document, year)
        input_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        schema_hash = hashlib.sha256(json.dumps(self.SCHEMA, sort_keys=True).encode()).hexdigest()
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            input_tokens = output_tokens = 0
            try:
                response = self.transport(payload)
                content, input_tokens, output_tokens = self._content(response)
                parsed = NarrativeOutput.model_validate_json(content)
                for claim in parsed.claims:
                    if claim.risk_category not in ALLOWED_CATEGORIES or claim.page not in pages:
                        raise ValueError("claim category/page is outside supplied evidence")
                cost = (input_tokens * self.input_cost_per_million + output_tokens * self.output_cost_per_million) / 1_000_000
                self._record(LLMCallLog(self.PROMPT_VERSION, "openai-compatible", self.model, attempt, input_tokens, output_tokens, round(cost, 8), int((time.perf_counter() - started) * 1000), "ok", input_hash, schema_hash, 0.0, self.max_tokens, f"exponential_backoff:{self.max_retries}", True))
                return [NarrativeClaim(c.claim, c.risk_category, Evidence(document, c.page, c.evidence_text, year, c.confidence), c.polarity, c.claim_target, c.direction, c.time_horizon, c.basis, tuple(c.qualifiers), tuple(c.required_evidence_types)) for c in parsed.claims]
            except (KeyError, TypeError, ValueError, ValidationError, urllib.error.URLError) as exc:
                last_error = exc
                self._record(LLMCallLog(self.PROMPT_VERSION, "openai-compatible", self.model, attempt, input_tokens, output_tokens, 0.0, int((time.perf_counter() - started) * 1000), f"error:{type(exc).__name__}", input_hash, schema_hash, 0.0, self.max_tokens, f"exponential_backoff:{self.max_retries}", False))
                if attempt <= self.max_retries:
                    time.sleep(min(2 ** (attempt - 1), 4))
        raise RuntimeError(f"structured narrative extraction failed after retries: {last_error}")


def provider_from_env() -> NarrativeProvider:
    provider = os.getenv("FINRISK_LLM_PROVIDER", "mock").lower()
    if provider == "mock":
        return MockNarrativeProvider()
    if provider in {"openai", "openai-compatible"}:
        return StructuredLLMProvider(
            model=os.getenv("FINRISK_LLM_MODEL", "gpt-4.1-mini"),
            endpoint=os.getenv("FINRISK_LLM_ENDPOINT", "https://api.openai.com/v1/chat/completions"),
            max_retries=int(os.getenv("FINRISK_LLM_MAX_RETRIES", "2")),
            max_tokens=int(os.getenv("FINRISK_LLM_MAX_TOKENS", "1200")),
            log_path=Path(os.getenv("FINRISK_LLM_LOG", "logs/llm-calls.jsonl")),
            input_cost_per_million=float(os.getenv("FINRISK_INPUT_COST_PER_MILLION", "0")),
            output_cost_per_million=float(os.getenv("FINRISK_OUTPUT_COST_PER_MILLION", "0")),
        )
    raise ValueError(f"unsupported FINRISK_LLM_PROVIDER: {provider}")
