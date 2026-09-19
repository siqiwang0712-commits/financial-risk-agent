from __future__ import annotations

import asyncio
import json
import logging
import math
import multiprocessing
import os
import queue as queue_module
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal

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
    from fastapi.encoders import jsonable_encoder
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
    from starlette.concurrency import run_in_threadpool
except ImportError:
    FastAPI = None

from .agent import FinancialRiskAgent
from .document_worker import run_document_worker
from .enterprise.api import enterprise_router
from .enterprise.decision import create_snapshot
from .enterprise.decision_bundle import build_decision_bundle
from .enterprise.domain import Principal
from .enterprise.observability import (
    bind_correlation_id,
    configure_logging,
    correlation_id,
    structured_event,
)
from .enterprise.postgres import PostgresEnterpriseRepository
from .enterprise.repository import InMemoryEnterpriseRepository
from .enterprise.security import (
    CredentialStore,
    PostgresCredentialStore,
    PostgresRateLimiter,
    RateLimiterUnavailable,
    SlidingWindowRateLimiter,
)
from .enterprise.service import EnterpriseRiskService
from .pipeline import FinRiskPipeline
from .secret_files import env_or_file as _env_or_file
from .xbrl import parse_companyfacts, values_by_year


async def _run_document_isolated(
    root: Path, company: str, year: int, path: Path, document: str, timeout: float
):
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(maxsize=1)
    process = context.Process(
        target=run_document_worker,
        args=(queue, str(root), company, year, str(path), document),
        daemon=True,
    )
    process.start()
    try:
        try:
            # Read while the child is alive. Joining first can deadlock when a
            # large AgentState fills the multiprocessing pipe during queue.put.
            status, result = await asyncio.to_thread(queue.get, True, timeout)
        except queue_module.Empty as exc:
            process.terminate()
            await asyncio.to_thread(process.join, 5)
            raise TimeoutError("document analysis timed out") from exc
        await asyncio.to_thread(process.join, 5)
        if process.is_alive():
            process.terminate()
            await asyncio.to_thread(process.join, 5)
        if status != "ok":
            raise RuntimeError(f"document worker failed: {result}")
        return result
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        queue.close()
        queue.join_thread()


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


def _json_safe(value):
    """Replace non-finite floats so the value survives `allow_nan=False` encoding.

    `json.loads("1e400")` yields `float('inf')`, and FastAPI echoes the offending
    input back inside its 422 body. Starlette serialises that body with
    `json.dumps(..., allow_nan=False)`, which raises
    `ValueError: Out of range float values are not JSON compliant` — so a request
    that was *correctly rejected* by the model validator answered 500 instead of
    422. Validation is right; the error path was the fragile part.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


# Driver-level failures that mean "the datastore could not be reached", as opposed to
# "the request was wrong" or "there is a bug here". Matched by class name across the
# MRO so neither `psycopg` nor `psycopg_pool` has to be importable to classify them.
_UNAVAILABLE_ERROR_NAMES = frozenset(
    {
        "OperationalError",
        "InterfaceError",
        "PoolClosed",
        "PoolTimeout",
        "TooManyRequests",
        "AdminShutdown",
        "CannotConnectNow",
        "ConnectionDoesNotExist",
    }
)


def _is_datastore_unavailable(exc: BaseException) -> bool:
    return any(cls.__name__ in _UNAVAILABLE_ERROR_NAMES for cls in type(exc).__mro__)


def max_upload_bytes() -> int:
    """The upload ceiling, in bytes, shared with the Next proxy.

    The proxy enforced `FINRISK_MAX_UPLOAD_BYTES` while the backend enforced
    `FINRISK_MAX_UPLOAD_MB` — two names, two units, one of them undocumented, so
    lowering the backend limit left the proxy accepting (and the user uploading)
    far more than the backend would take. `*_BYTES` is now the single knob; the
    historical `*_MB` name is still honoured so existing deployments and tests
    keep working.
    """
    configured_bytes = os.getenv("FINRISK_MAX_UPLOAD_BYTES")
    if configured_bytes:
        return int(_positive_env_number("FINRISK_MAX_UPLOAD_BYTES", "52428800", int))
    return int(_positive_env_number("FINRISK_MAX_UPLOAD_MB", "50", int)) * 1024 * 1024


def _pdf_limits() -> tuple[int, int, int, float]:
    pages = _positive_env_number("FINRISK_MAX_PDF_PAGES", "500", int)
    chars = _positive_env_number("FINRISK_MAX_EXTRACTED_CHARS", "5000000", int)
    timeout = _positive_env_number(
        "FINRISK_ANALYSIS_TIMEOUT_SECONDS", "60", float
    )
    return max_upload_bytes(), pages, chars, timeout


def _inspect_pdf(data: bytes, max_pages: int, max_chars: int) -> None:
    """Inspect a PDF synchronously; callers must run this in a bounded worker pool."""
    try:
        import pymupdf as fitz

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
    # Configure the root logger before anything logs; otherwise INFO events were
    # dropped by logging.lastResort and production ran silently.
    configure_logging()

    def runtime_components():
        database_url = _env_or_file("DATABASE_URL")
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
            credentials = PostgresCredentialStore(repository)
        else:
            repository = InMemoryEnterpriseRepository()
            credentials = CredentialStore()
        return EnterpriseRiskService(repository), credentials

    class XbrlNormalizeRequest(BaseModel):
        companyfacts: dict
        fiscal_years: list[int] | None = None

    class AssessmentRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        company: str = Field(min_length=1, max_length=300)
        fiscal_year: int = Field(ge=1900, le=2100)
        current: dict[str, float | bool | None]
        previous: dict[str, float | bool | None] | None = None
        previous_fiscal_year: int | None = Field(default=None, ge=1900, le=2100)
        pages: dict[int, str] = Field(default_factory=dict)
        document: str = Field(default="Annual Report", min_length=1, max_length=500)
        entity_type: Literal[
            "industrial", "manufacturing", "public_manufacturer", "public",
            "private", "private_company", "private_manufacturer",
            "non_manufacturer", "retail", "service", "bank", "banking",
            "financial_institution",
        ] = "industrial"
        entity_id: str | None = None

        @field_validator("current", "previous")
        @classmethod
        def finite_financial_inputs(cls, values):
            import math

            if values is None:
                return values
            if len(values) > 512:
                raise ValueError("financial input field limit exceeded")
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

        @field_validator("pages")
        @classmethod
        def bounded_pages(cls, pages):
            _, max_pages, max_chars, _ = _pdf_limits()
            if len(pages) > max_pages:
                raise ValueError("page limit exceeded")
            if any(page < 1 for page in pages):
                raise ValueError("page numbers must be positive")
            if sum(len(text) for text in pages.values()) > max_chars:
                raise ValueError("page-text limit exceeded")
            return pages

        @model_validator(mode="after")
        def consecutive_comparative_period(self):
            if self.previous is None and self.previous_fiscal_year is not None:
                raise ValueError("previous_fiscal_year requires previous values")
            if self.previous is not None:
                if self.previous_fiscal_year is None:
                    raise ValueError("previous_fiscal_year is required with previous values")
                if self.previous_fiscal_year != self.fiscal_year - 1:
                    raise ValueError("comparative period must be the immediately preceding fiscal year")
            return self

    app = FastAPI(
        title="FinRisk-Agent API",
        version="0.3.3",
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
    # Rate limits must hold across restarts and replicas, so they live in the same
    # store as the data whenever PostgreSQL is in use; the in-process window is only
    # the local fallback.
    api_limit = int(os.getenv("FINRISK_RATE_LIMIT", "60"))
    bootstrap_limit = int(os.getenv("FINRISK_BOOTSTRAP_RATE_LIMIT", "60"))
    if isinstance(enterprise_service.repository, PostgresEnterpriseRepository):
        api_limiter = PostgresRateLimiter(enterprise_service.repository, limit=api_limit)
        bootstrap_limiter = PostgresRateLimiter(
            enterprise_service.repository, limit=bootstrap_limit
        )
    else:
        api_limiter = SlidingWindowRateLimiter(limit=api_limit)
        bootstrap_limiter = SlidingWindowRateLimiter(limit=bootstrap_limit)
    # Case-insensitive environment check: `FINRISK_ENV=Production` previously read as
    # "not production", which re-enabled the unauthenticated bootstrap endpoint.
    finrisk_env = os.getenv("FINRISK_ENV", "development").strip().lower()
    # Production bootstrap is deliberately opt-in and token-gated.  Disabling it
    # unconditionally left a fresh production database with no way to provision
    # the first administrator; enabling it without a token is rejected by the
    # router's production token requirement.
    bootstrap_enabled = os.getenv("FINRISK_ENABLE_ORG_BOOTSTRAP", "1") == "1"
    bootstrap_token = _env_or_file("FINRISK_BOOTSTRAP_TOKEN")
    app.include_router(
        enterprise_router(
            enterprise_service,
            credential_store,
            api_limiter,
            bootstrap_enabled,
            bootstrap_token,
            require_bootstrap_token=finrisk_env == "production",
            bootstrap_limiter=bootstrap_limiter,
        )
    )
    api_logger = logging.getLogger("finrisk.api")

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Answer 422 with a body that is always serialisable.

        Without this the default handler echoed the offending input verbatim, and
        an out-of-range literal (`1e400` parses to `inf`) made Starlette's
        `allow_nan=False` encoder raise — turning a correct rejection into a 500.
        """
        return JSONResponse(
            status_code=422,
            content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
        )

    @app.exception_handler(RateLimiterUnavailable)
    async def rate_limiter_unavailable_handler(
        request: Request, exc: RateLimiterUnavailable
    ):
        """Fail closed with a controlled 503 when the limiter's store is down.

        The limiter is the only bound on the unauthenticated bootstrap route, so
        "cannot decide" must not mean "admit". Letting the driver error escape gave
        an unhandled 500 with a traceback; admitting the request would have been
        worse — it silently removed the rate limit for the duration of the outage.
        """
        structured_event(
            api_logger,
            "rate_limiter.unavailable",
            path=request.url.path,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "rate limiting is temporarily unavailable",
                "correlation_id": correlation_id.get(),
            },
            headers={"Retry-After": "5"},
        )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        identifier = bind_correlation_id(request.headers.get("X-Correlation-Id"))
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - public boundary must sanitize unknown failures
            if _is_datastore_unavailable(exc):
                # A datastore outage is not an internal defect: the request was fine and
                # the same call will work once the dependency is back, so 503 (with
                # `Retry-After`) is what a client — and a load balancer — must see. It
                # also used to be an unhandled 500 with a traceback in the log, which
                # reads as "the service is broken" rather than "the database is down".
                structured_event(
                    api_logger,
                    "http.datastore_unavailable",
                    path=request.url.path,
                    error_type=type(exc).__name__,
                )
                response = JSONResponse(
                    {
                        "detail": "the datastore is temporarily unavailable",
                        "correlation_id": identifier,
                    },
                    status_code=503,
                    headers={"Retry-After": "5"},
                )
            else:
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
        if not api_limiter.allow(f"core:{principal.organization_id}:{principal.user_id}"):
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
        # Re-analysing an unchanged filing produced a byte-identical snapshot under
        # a fresh random id, so `analysis_snapshots` (and the entity's risk
        # timeline) grew without bound while the decision bundle — which *is*
        # content-addressed — was correctly deduplicated. Reuse the frozen snapshot
        # instead: same evidence, same id, no new row, no new audit event.
        existing = enterprise_service.repository.find_snapshot(
            actor.organization_id, entity_id, snapshot.input_hash, snapshot.output_hash
        )
        reused_snapshot = existing is not None
        if reused_snapshot:
            state.analysis_snapshot = asdict(existing)
            snapshot = existing
        else:
            try:
                saved = enterprise_service.save_snapshot(actor, snapshot)
            except (KeyError, PermissionError, ValueError) as exc:
                raise HTTPException(422, "analysis snapshot persistence rejected") from exc
            state.analysis_snapshot = asdict(saved)
            snapshot = saved
        prior_bundle = state.decision_bundle
        bundle = build_decision_bundle(
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
        )
        reused_bundle = False
        try:
            enterprise_service.save_decision_bundle(actor, bundle)
        except ValueError as exc:
            # Re-analysing the same filing for the same entity derives the same
            # content-addressed bundle id, and both repositories reject a second
            # write with `decision bundle already exists`. That raised straight
            # out of this function, so every re-run of `/documents/analyze`
            # returned 500 — a normal user action. An identical bundle is already
            # on record; a different payload under the same id is a real
            # conflict and stays a 422.
            stored = None
            try:
                stored = enterprise_service.repository.get_decision_bundle(
                    actor.organization_id, entity_id, bundle.bundle_id
                )
            except (KeyError, ValueError):
                stored = None
            if stored is None or stored.bundle_hash != bundle.bundle_hash:
                structured_event(api_logger, "document.bundle_conflict")
                raise HTTPException(422, "decision bundle persistence rejected") from exc
            bundle = stored
            reused_bundle = True
        state.decision_bundle = bundle.to_dict()
        # Deduplication must not erase execution history. The snapshot and the bundle
        # may be reused, but this run still happened, and provenance has to be able to
        # say who ran it, when, against which entity/document, and with which engine /
        # model / ruleset versions — otherwise the audit trail silently under-counts
        # real analyses.
        try:
            enterprise_service.record_analysis_execution(
                actor,
                {
                    "entity_id": entity_id,
                    "snapshot_id": snapshot.id,
                    "decision_bundle_id": bundle.bundle_id,
                    "document_versions": dict(generated["document_versions"]),
                    "component_versions": dict(generated["component_versions"]),
                    "input_hash": snapshot.input_hash,
                    "output_hash": snapshot.output_hash,
                    "decision": state.decision,
                    "reused_snapshot": reused_snapshot,
                    "reused_decision_bundle": reused_bundle,
                },
            )
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(422, "analysis execution could not be recorded") from exc

    def validate_analysis_entity(actor: Principal, entity_id: str | None) -> None:
        """Reject an invalid/cross-tenant entity before doing expensive analysis."""
        if entity_id is None:
            if os.getenv("FINRISK_ENV", "development").lower() == "production":
                raise HTTPException(422, "entity_id is required for production analysis")
            return
        try:
            enterprise_service.repository.get_entity(actor.organization_id, entity_id)
        except KeyError as exc:
            raise HTTPException(422, "entity_id is not available to this tenant") from exc

    def document_response(state) -> dict:
        """Expose the result contract, not replay/snapshot internals or raw pages."""
        payload = dict(state.assessment or {})
        payload["agent"] = {
            key: value
            for key, value in state.to_dict().items()
            if key in {
                "status", "plan", "trace", "conclusions", "warnings", "reflection",
                "risk_score", "confidence", "confidence_semantics", "evidence_coverage",
                "risk_severity", "risk_trajectory", "decision", "model_disagreement",
                "fusion", "decision_trace", "role_review", "epistemics", "component_telemetry",
            }
        }
        return payload

    @app.get("/health/live")
    def health_live():
        return {"status": "alive"}

    @app.get("/health/ready")
    def health_ready():
        repository = enterprise_service.repository
        # `datastore` is reported so a deployment gate can assert that the process
        # really selected PostgreSQL. It used to be impossible to tell from the
        # outside: a wrong DATABASE_URL silently degraded to the in-memory
        # repository and every external check still passed.
        datastore = "postgres" if isinstance(repository, PostgresEnterpriseRepository) else "memory"
        if datastore == "postgres":
            try:
                if not repository.check_ready():
                    raise RuntimeError("unexpected database probe result")
            except Exception as exc:
                # A stale credential is the one database failure that is *silent*:
                # `POSTGRES_PASSWORD` is only applied when the volume is first
                # initialised, so changing it against an existing volume leaves the
                # server rejecting the new value while everything still looks
                # configured. Say so explicitly instead of reporting a generic
                # outage — the operator needs to know which of the two it is.
                # The pool reports a bare `PoolTimeout` when every attempt fails,
                # so the string alone cannot tell a rotated credential from an
                # outage. Ask the server directly, once, before falling back to
                # the generic answer.
                if "authentication failed" in str(exc).lower() or (
                    isinstance(repository, PostgresEnterpriseRepository)
                    and repository.credentials_rejected()
                ):
                    structured_event(api_logger, "health.database_auth_failed")
                    raise HTTPException(
                        503,
                        "database rejected the configured credentials: a pre-existing "
                        "PostgreSQL volume keeps the password it was initialised with "
                        "(rotate it inside the database, or recreate the volume)",
                        headers={"Retry-After": "5"},
                    ) from exc
                structured_event(api_logger, "health.database_unavailable")
                raise HTTPException(
                    503, "database readiness check failed", headers={"Retry-After": "5"}
                ) from exc
            # A reachable database is not a migrated one. The API once served a
            # zero-table database behind a green `/health/ready`, because the probe
            # only ran `SELECT 1`; every business request then failed while the
            # orchestrator believed the deploy was healthy. Migration state is a
            # separate fact, so it is checked separately — and reported separately,
            # because "not migrated" has a different fix from "not reachable".
            try:
                missing = repository.missing_schema_objects()
            except Exception as exc:
                structured_event(api_logger, "health.database_unavailable")
                raise HTTPException(
                    503, "database readiness check failed", headers={"Retry-After": "5"}
                ) from exc
            if missing:
                structured_event(
                    api_logger, "health.schema_incomplete", objects=",".join(missing)
                )
                # A missing schema is not self-healing on a short timer, but a load
                # balancer still needs a backoff hint rather than a tight retry loop.
                raise HTTPException(
                    503,
                    "database schema is not migrated: missing "
                    + ", ".join(missing)
                    + " (run scripts/validate_postgres_migration.py)",
                    headers={"Retry-After": "5"},
                )
        payload = {"status": "ready", "datastore": datastore}
        if datastore == "postgres":
            payload["schema"] = "complete"
        return payload

    @app.get("/health", include_in_schema=False)
    def health_compatibility():
        return health_ready()

    @app.get("/api/v1/public-pilot")
    def public_pilot():
        # Unauthenticated and served on every request, so a missing or malformed
        # snapshot has to be reported as "not available" rather than escaping as a
        # FileNotFoundError/StopIteration 500.
        try:
            payload = json.loads(
                (ROOT / "research/results/public_v1/summary.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "public pilot snapshot is unavailable") from exc
        full_hybrid = next(
            (item for item in payload.get("summaries", []) if item.get("baseline") == "full_hybrid"),
            None,
        )
        if full_hybrid is None:
            raise HTTPException(503, "public pilot snapshot is missing the full_hybrid baseline")
        return {
            "snapshot": "v0.3.0 frozen public pilot",
            "runtime": "v0.3.3",
            "annotation_status": payload.get("annotation_status"),
            # Benchmark-level only: copying this into every row incorrectly
            # represented one aggregate as three entity measurements.
            "benchmark_evidence_coverage": full_hybrid["evidence_coverage"],
            "rows": [
                {
                    "entity": item.get("company"),
                    "decision": "FLAG" if item.get("prediction") else "PASS",
                    "score": item.get("overall_score"),
                    "reliability": "UNCALIBRATED",
                    "filing": item.get("example_id"),
                }
                for item in payload.get("decompositions", [])
            ],
        }

    @app.post("/api/v1/xbrl/normalize")
    def normalize_xbrl(req: XbrlNormalizeRequest, actor: Principal = protected):
        # `companyfacts` is caller-supplied JSON with no schema behind it, so the
        # parser can still meet shapes it cannot normalize. Those are input
        # problems, not server faults.
        try:
            values = parse_companyfacts(req.companyfacts, req.fiscal_years)
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, f"companyfacts could not be normalized: {exc}") from exc
        return {
            "values": [value.__dict__ for value in values],
            "by_year": values_by_year(values),
        }

    @app.post("/api/v1/assess")
    def assess(req: AssessmentRequest, actor: Principal = protected):
        try:
            assessment = pipeline.assess(
                req.company,
                req.fiscal_year,
                req.current,
                req.previous,
                req.pages,
                req.document,
                req.entity_type,
            )
            # Both this endpoint and the agent path attach the decision-bearing
            # score through the same helper, so `overall_score` has one meaning and
            # `final_decision`/`enterprise_fusion` are present on both.
            return pipeline.decide(assessment)
        except ValueError as exc:
            structured_event(api_logger, "assessment.rejected", error_type=type(exc).__name__)
            raise HTTPException(422, "assessment input was rejected") from exc

    @app.post("/api/v1/agent/assess")
    def agent_assess(req: AssessmentRequest, actor: Principal = protected):
        validate_analysis_entity(actor, req.entity_id)
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
            validate_analysis_entity(actor, entity_id)
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
                # Every environment runs the analysis in a killable child process.
                # The development path used to run it on a worker thread, where
                # `asyncio.wait_for` only stopped *waiting*: a runaway parse kept
                # burning a thread and its memory after the request had already
                # answered 504. Same code path everywhere also means the timeout
                # contract is exercised locally, not only in production.
                state = await _run_document_isolated(
                    ROOT, company, fiscal_year, path,
                    file.filename or "Annual Report", timeout_seconds,
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
            return document_response(state)
        finally:
            path.unlink(missing_ok=True)
else:
    app = None
