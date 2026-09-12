from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

try:
    from fastapi import (
        Depends,
        FastAPI,
        File,
        Form,
        Header,
        HTTPException,
        Request,
        UploadFile,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field, field_validator
    from starlette.concurrency import run_in_threadpool
except ImportError:
    FastAPI = None

from .agent import FinancialRiskAgent
from .enterprise.api import enterprise_router
from .enterprise.decision import create_snapshot
from .enterprise.decision_bundle import build_decision_bundle
from .enterprise.domain import Principal
from .enterprise.observability import bind_correlation_id, structured_event
from .enterprise.postgres import PostgresEnterpriseRepository
from .enterprise.repository import InMemoryEnterpriseRepository
from .enterprise.security import (
    CredentialStore,
    PostgresCredentialStore,
    SlidingWindowRateLimiter,
)
from .enterprise.service import EnterpriseRiskService
from .pipeline import FinRiskPipeline
from .xbrl import parse_companyfacts, values_by_year


class PdfBoundaryError(ValueError):
    """A safe, client-facing PDF resource-boundary failure."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _positive_env_number(name: str, default: str, cast):
    raw = os.getenv(name, default)
    try:
        value = cast(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _pdf_limits() -> tuple[int, int, int, float]:
    upload_mb = _positive_env_number("FINRISK_MAX_UPLOAD_MB", "50", int)
    pages = _positive_env_number("FINRISK_MAX_PDF_PAGES", "500", int)
    chars = _positive_env_number("FINRISK_MAX_EXTRACTED_CHARS", "5000000", int)
    timeout = _positive_env_number(
        "FINRISK_ANALYSIS_TIMEOUT_SECONDS", "60", float
    )
    return upload_mb * 1024 * 1024, pages, chars, timeout


def _inspect_pdf(data: bytes, max_pages: int, max_chars: int) -> None:
    """Inspect a PDF synchronously; callers must run this in a bounded worker pool."""
    try:
        import fitz

        with fitz.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise PdfBoundaryError(422, "encrypted PDFs are not supported")
            if document.page_count > max_pages:
                raise PdfBoundaryError(413, "PDF page limit exceeded")
            extracted_chars = 0
            for page in document:
                extracted_chars += len(page.get_text("text"))
                if extracted_chars > max_chars:
                    raise PdfBoundaryError(413, "PDF extracted-text limit exceeded")
    except PdfBoundaryError:
        raise
    except Exception as exc:
        raise PdfBoundaryError(422, "PDF could not be safely parsed") from exc

if FastAPI:

    ROOT = Path(__file__).resolve().parents[2]

    def runtime_components():
        database_url = os.getenv("DATABASE_URL")
        environment = os.getenv("FINRISK_ENV", "development").lower()
        if environment == "production" and (
            not database_url or "local-development-only" in database_url
        ):
            raise RuntimeError("production requires an explicit DATABASE_URL with a non-default password")
        if database_url:
            repository = PostgresEnterpriseRepository.connect(database_url)
            if os.getenv("FINRISK_AUTO_MIGRATE", "0") == "1":
                for migration in sorted((ROOT / "migrations").glob("*.sql")):
                    repository.migrate(migration)
            credentials = PostgresCredentialStore(repository.connection)
        else:
            repository = InMemoryEnterpriseRepository()
            credentials = CredentialStore()
        return EnterpriseRiskService(repository), credentials

    class XbrlNormalizeRequest(BaseModel):
        companyfacts: dict
        fiscal_years: list[int] | None = None

    class AssessmentRequest(BaseModel):
        company: str = Field(min_length=1)
        fiscal_year: int
        current: dict[str, float | bool | None]
        previous: dict[str, float | bool | None] | None = None
        pages: dict[int, str] = Field(default_factory=dict)
        document: str = "Annual Report"
        entity_type: str = "industrial"
        entity_id: str | None = None

        @field_validator("current", "previous")
        @classmethod
        def finite_financial_inputs(cls, values):
            import math

            if values is None:
                return values
            boolean_signals = {
                "going_concern_doubt", "material_weakness", "refinancing_dependency"
            }
            for name, value in values.items():
                if isinstance(value, bool):
                    if name not in boolean_signals:
                        raise ValueError(f"boolean is not valid for numeric field {name}")
                elif value is not None and not math.isfinite(value):
                    raise ValueError(f"non-finite financial input: {name}")
            return values

    app = FastAPI(
        title="FinRisk-Agent API",
        version="0.3.2",
        description="Three-layer evidence-grounded financial risk agent",
    )
    cors_origins = [
        origin.strip()
        for origin in os.getenv("FINRISK_CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    pipeline = FinRiskPipeline(ROOT)
    agent = FinancialRiskAgent(ROOT, pipeline.provider)
    enterprise_service, credential_store = runtime_components()
    api_limiter = SlidingWindowRateLimiter(limit=int(os.getenv("FINRISK_RATE_LIMIT", "60")))
    bootstrap_enabled = os.getenv("FINRISK_ENABLE_ORG_BOOTSTRAP", "1") == "1" and os.getenv("FINRISK_ENV", "development") != "production"
    app.include_router(enterprise_router(enterprise_service, credential_store, api_limiter, bootstrap_enabled))
    api_logger = logging.getLogger("finrisk.api")

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        identifier = bind_correlation_id(request.headers.get("X-Correlation-Id"))
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - public boundary must sanitize unknown failures
            structured_event(api_logger, "http.unhandled", error_type=type(exc).__name__)
            response = JSONResponse(
                {"detail": "internal server error", "correlation_id": identifier},
                status_code=500,
            )
        response.headers["X-Correlation-Id"] = identifier
        structured_event(
            api_logger,
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        return response

    def authenticated_principal(x_api_key: str | None = Header(default=None)) -> Principal:
        if not x_api_key:
            raise HTTPException(401, "missing API key")
        try:
            principal = credential_store.authenticate(x_api_key)
        except PermissionError as exc:
            raise HTTPException(401, "invalid API key") from exc
        if not api_limiter.allow(f"core:{principal.organization_id}"):
            raise HTTPException(429, "rate limit exceeded")
        return principal

    protected = Depends(authenticated_principal)

    def persist_agent_snapshot(state, actor: Principal, entity_id: str | None) -> None:
        if entity_id is None:
            if os.getenv("FINRISK_ENV", "development").lower() == "production":
                raise HTTPException(422, "entity_id is required for persisted production analysis")
            return
        generated = state.analysis_snapshot
        if not generated:
            raise HTTPException(422, "agent did not produce a trusted analysis snapshot")
        frozen_output = dict(generated["frozen_output"])
        frozen_output["agent"] = {
            "risk_severity": state.risk_severity,
            "risk_trajectory": state.risk_trajectory,
            "evidence_coverage": state.evidence_coverage,
            "epistemics": state.epistemics,
            "decision_trace": state.decision_trace,
            "decision": state.decision,
        }
        snapshot = create_snapshot(
            actor.organization_id,
            entity_id,
            generated["frozen_input"],
            frozen_output,
            generated["document_versions"],
            generated["component_versions"],
        )
        try:
            saved = enterprise_service.save_snapshot(actor, snapshot)
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "analysis snapshot persistence rejected") from exc
        state.analysis_snapshot = asdict(saved)
        prior_bundle = state.decision_bundle
        state.decision_bundle = build_decision_bundle(
            actor.organization_id,
            entity_id,
            generated["document_versions"],
            generated["frozen_input"],
            frozen_output,
            prior_bundle.get("risk_state", {}),
            list(prior_bundle.get("evidence_paths", [])),
            prior_bundle.get("calculations", {}),
            list(prior_bundle.get("agent_trace", [])),
            generated["component_versions"],
            state.decision,
            risk_delta=prior_bundle.get("risk_delta"),
            human_review=prior_bundle.get("human_review"),
            epistemics=state.epistemics,
            component_telemetry=state.component_telemetry,
        ).to_dict()

    @app.get("/health/live")
    def health_live():
        return {"status": "alive"}

    @app.get("/health/ready")
    def health_ready():
        repository = enterprise_service.repository
        if isinstance(repository, PostgresEnterpriseRepository):
            try:
                with repository.connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    if cursor.fetchone()[0] != 1:
                        raise RuntimeError("unexpected database probe result")
            except Exception as exc:
                structured_event(api_logger, "health.database_unavailable")
                raise HTTPException(
                    503, "database readiness check failed"
                ) from exc
        return {
            "status": "ready",
            "repository": repository.__class__.__name__,
            "llm_provider": pipeline.provider.__class__.__name__,
            "agent_tools": agent.tools.names(),
        }

    @app.get("/health", include_in_schema=False)
    def health_compatibility():
        return health_ready()

    @app.get("/api/v1/public-pilot")
    def public_pilot():
        payload = json.loads(
            (ROOT / "research/results/public_v1/summary.json").read_text(encoding="utf-8")
        )
        full_hybrid = next(
            item for item in payload["summaries"] if item["baseline"] == "full_hybrid"
        )
        return {
            "snapshot": "v0.3.0 frozen public pilot",
            "runtime": "v0.3.2",
            "annotation_status": payload["annotation_status"],
            "rows": [
                {
                    "entity": item["company"],
                    "decision": "FLAG" if item["prediction"] else "PASS",
                    "score": item["overall_score"],
                    "coverage": full_hybrid["evidence_coverage"],
                    "reliability": "UNCALIBRATED",
                    "filing": item["example_id"],
                }
                for item in payload["decompositions"]
            ],
        }

    @app.post("/api/v1/xbrl/normalize")
    def normalize_xbrl(req: XbrlNormalizeRequest, actor: Principal = protected):
        values = parse_companyfacts(req.companyfacts, req.fiscal_years)
        return {
            "values": [value.__dict__ for value in values],
            "by_year": values_by_year(values),
        }

    @app.post("/api/v1/assess")
    def assess(req: AssessmentRequest, actor: Principal = protected):
        try:
            return pipeline.assess(
                req.company,
                req.fiscal_year,
                req.current,
                req.previous,
                req.pages,
                req.document,
                req.entity_type,
            ).to_dict()
        except ValueError as exc:
            structured_event(api_logger, "assessment.rejected", error_type=type(exc).__name__)
            raise HTTPException(422, "assessment input was rejected") from exc

    @app.post("/api/v1/agent/assess")
    def agent_assess(req: AssessmentRequest, actor: Principal = protected):
        state = agent.run(
            req.company,
            req.fiscal_year,
            req.current,
            req.previous,
            req.pages,
            req.document,
            req.entity_type,
        )
        if state.status == "FAILED":
            raise HTTPException(
                422, "agent assessment could not be completed"
            )
        persist_agent_snapshot(state, actor, req.entity_id)
        return state.to_dict()

    @app.post("/api/v1/documents/analyze")
    async def analyze_document(
        company: Annotated[str, Form()],
        fiscal_year: Annotated[int, Form()],
        file: Annotated[UploadFile, File()],
        entity_id: Annotated[str | None, Form()] = None,
        actor: Principal = protected,
    ):
        try:
            max_bytes, max_pages, max_chars, timeout_seconds = _pdf_limits()
        except RuntimeError as exc:
            structured_event(api_logger, "document.configuration_invalid")
            raise HTTPException(503, "document analysis is not configured safely") from exc
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, "PDF upload-size limit exceeded")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "Only valid PDF files are accepted")
        try:
            await run_in_threadpool(_inspect_pdf, data, max_pages, max_chars)
        except PdfBoundaryError as exc:
            raise HTTPException(exc.status_code, exc.detail) from exc
        with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            path = Path(tmp.name)
        try:
            try:
                state = await asyncio.wait_for(
                    run_in_threadpool(
                        agent.run_document,
                        company,
                        fiscal_year,
                        path,
                        file.filename or "Annual Report",
                    ),
                    timeout=timeout_seconds,
                )
            except TimeoutError as exc:
                structured_event(api_logger, "document.analysis_timeout")
                raise HTTPException(504, "document analysis timed out") from exc
            except HTTPException:
                raise
            except Exception as exc:
                structured_event(api_logger, "document.analysis_failed", error_type=type(exc).__name__)
                raise HTTPException(422, "document analysis could not be completed") from exc
            if state.status == "FAILED":
                raise HTTPException(
                    422,
                    "agent workflow could not be completed",
                )
            persist_agent_snapshot(state, actor, entity_id)
            payload = state.assessment or {}
            payload["agent"] = {
                key: value
                for key, value in state.to_dict().items()
                if key != "assessment"
            }
            return payload
        finally:
            path.unlink(missing_ok=True)
else:
    app = None
