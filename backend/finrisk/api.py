from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

try:
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    from starlette.concurrency import run_in_threadpool
except ImportError: FastAPI=None
from .domain import Evidence
from .parser import DocumentParser
from .pipeline import FinRiskPipeline

if FastAPI:
    class AssessmentRequest(BaseModel):
        company:str=Field(min_length=1); fiscal_year:int; current:dict[str,float|bool|str|None]; previous:dict[str,float|bool|str|None]|None=None; pages:dict[int,str]={}; document:str="Annual Report"; entity_type:str="industrial"
    app=FastAPI(title="FinRisk-Agent API",version="0.1.0",description="Evidence-grounded hybrid financial risk assessment")
    app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000"],allow_methods=["GET","POST"],allow_headers=["*"])
    pipeline=FinRiskPipeline(Path(__file__).resolve().parents[2])
    parser=DocumentParser()
    @app.get("/health")
    def health():return {"status":"ok","llm_provider":"mock"}
    @app.post("/api/v1/assess")
    def assess(req:AssessmentRequest):
        try:return pipeline.assess(req.company,req.fiscal_year,req.current,req.previous,req.pages,req.document,req.entity_type).to_dict()
        except ValueError as exc:raise HTTPException(422,str(exc))

    @app.post("/api/v1/documents/analyze")
    async def analyze_document(company:str=Form(...),fiscal_year:int=Form(...),file:UploadFile=File(...)):  # noqa: B008
        data=await file.read(50*1024*1024+1)
        if len(data)>50*1024*1024:raise HTTPException(413,"PDF exceeds 50 MB limit")
        if not data.startswith(b"%PDF"):raise HTTPException(415,"Only valid PDF files are accepted")
        with NamedTemporaryFile(suffix=".pdf",delete=False) as tmp:
            tmp.write(data);path=Path(tmp.name)
        try:
            try:pages=await run_in_threadpool(parser.extract_pages,path)
            except Exception as exc:raise HTTPException(422,"PDF parsing failed; the file may be damaged or unsupported") from exc
            if len(pages)>500:raise HTTPException(422,"PDF exceeds the 500-page analysis limit")
            extracted=parser.extract_values(pages,file.filename or "Annual Report",fiscal_year)
            if not extracted:raise HTTPException(422,"No reliable financial line items were extracted; manual review is required")
            current={};sources={};candidates={};review_issues=[]
            for item in extracted:
                if item.fiscal_year!=fiscal_year:continue
                candidates.setdefault(item.line_item,set()).add(item.value)
                sources.setdefault(item.line_item,[]).append(Evidence(item.document,item.page,item.source_text,item.fiscal_year,item.confidence,False,"located"))
            for key,values in candidates.items():
                usable={v for v in values if v is not None}
                if len(usable)==1:current[key]=usable.pop()
                elif len(usable)>1:review_issues.append({"line_item":key,"reason":"conflicting candidates","values":sorted(usable)})
            if not current:raise HTTPException(422,"No unambiguous values were available for the requested fiscal year")
            result=pipeline.assess(company,fiscal_year,current,pages=pages,document=file.filename or "Annual Report",source_map=sources)
            payload=result.to_dict();payload["extraction"]={"candidate_count":len(extracted),"review_required":True,"review_issues":review_issues,"sections":parser.identify_sections(pages)}
            return payload
        finally:path.unlink(missing_ok=True)
else:
    app=None
