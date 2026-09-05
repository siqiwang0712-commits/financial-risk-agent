from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    from starlette.concurrency import run_in_threadpool
except ImportError:
    FastAPI = None

from .agent import FinancialRiskAgent
from .pipeline import FinRiskPipeline
from .xbrl import parse_companyfacts, values_by_year

if FastAPI:

    class XbrlNormalizeRequest(BaseModel):
        companyfacts: dict
        fiscal_years: list[int] | None = None

    class AssessmentRequest(BaseModel):
        company: str = Field(min_length=1)
        fiscal_year: int
        current: dict[str, float | bool | str | None]
        previous: dict[str, float | bool | str | None] | None = None
        pages: dict[int, str] = {}
        document: str = "Annual Report"
        entity_type: str = "industrial"

    app = FastAPI(
        title="FinRisk-Agent API",
        version="0.2.0",
        description="Three-layer evidence-grounded financial risk agent",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    pipeline = FinRiskPipeline(Path(__file__).resolve().parents[2])
    agent = FinancialRiskAgent(Path(__file__).resolve().parents[2], pipeline.provider)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "llm_provider": pipeline.provider.__class__.__name__,
            "agent_tools": agent.tools.names(),
        }

    @app.post("/api/v1/xbrl/normalize")
    def normalize_xbrl(req: XbrlNormalizeRequest):
        values = parse_companyfacts(req.companyfacts, req.fiscal_years)
        return {
            "values": [value.__dict__ for value in values],
            "by_year": values_by_year(values),
        }

    @app.post("/api/v1/assess")
    def assess(req: AssessmentRequest):
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
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/v1/agent/assess")
    def agent_assess(req: AssessmentRequest):
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
                422, state.warnings[-1] if state.warnings else "Agent failed"
            )
        return state.to_dict()

    @app.post("/api/v1/documents/analyze")
    async def analyze_document(
        company: Annotated[str, Form()],
        fiscal_year: Annotated[int, Form()],
        file: Annotated[UploadFile, File()],
    ):
        data = await file.read(50 * 1024 * 1024 + 1)
        if len(data) > 50 * 1024 * 1024:
            raise HTTPException(413, "PDF exceeds 50 MB limit")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "Only valid PDF files are accepted")
        with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            path = Path(tmp.name)
        try:
            try:
                state = await run_in_threadpool(
                    agent.run_document,
                    company,
                    fiscal_year,
                    path,
                    file.filename or "Annual Report",
                )
            except Exception as exc:
                raise HTTPException(422, str(exc)) from exc
            if state.status == "FAILED":
                raise HTTPException(
                    422,
                    state.warnings[-1] if state.warnings else "Agent workflow failed",
                )
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
