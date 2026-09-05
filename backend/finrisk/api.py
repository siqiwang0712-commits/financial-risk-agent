from __future__ import annotations

from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError: FastAPI=None
from .pipeline import FinRiskPipeline

if FastAPI:
    class AssessmentRequest(BaseModel):
        company:str=Field(min_length=1); fiscal_year:int; current:dict[str,float|bool|str|None]; previous:dict[str,float|bool|str|None]|None=None; pages:dict[int,str]={}; document:str="Annual Report"; entity_type:str="industrial"
    app=FastAPI(title="FinRisk-Agent API",version="0.1.0",description="Evidence-grounded hybrid financial risk assessment")
    pipeline=FinRiskPipeline(Path(__file__).resolve().parents[2])
    @app.get("/health")
    def health():return {"status":"ok","llm_provider":"mock"}
    @app.post("/api/v1/assess")
    def assess(req:AssessmentRequest):
        try:return pipeline.assess(req.company,req.fiscal_year,req.current,req.previous,req.pages,req.document,req.entity_type).to_dict()
        except ValueError as exc:raise HTTPException(422,str(exc))
else:
    app=None

