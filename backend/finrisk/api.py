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
            current={};previous={};sources={};candidates={};review_issues=[]
            for item in extracted:
                candidates.setdefault((item.fiscal_year,item.line_item),[]).append(item)
                if item.fiscal_year==fiscal_year:sources.setdefault(item.line_item,[]).append(Evidence(item.document,item.page,item.source_text,item.fiscal_year,item.confidence,False,"located"))
            prior_year=max((y for y,_ in candidates if y<fiscal_year),default=None)
            for (candidate_year,key),items in candidates.items():
                if candidate_year not in {fiscal_year,prior_year}:continue
                ranked=sorted(items,key=lambda x:(x.restated,x.statement!="unknown",x.confidence),reverse=True)
                top_rank=(ranked[0].restated,ranked[0].statement!="unknown",ranked[0].confidence)
                top=[x for x in ranked if (x.restated,x.statement!="unknown",x.confidence)==top_rank]
                usable={x.value for x in top if x.value is not None}
                target=current if candidate_year==fiscal_year else previous
                if len(usable)==1:target[key]=usable.pop()
                elif len(usable)>1:review_issues.append({"line_item":key,"fiscal_year":candidate_year,"reason":"conflicting top-ranked candidates","values":sorted(usable)})
            if not current:raise HTTPException(422,"No unambiguous values were available for the requested fiscal year")
            result=pipeline.assess(company,fiscal_year,current,previous or None,pages,file.filename or "Annual Report",source_map=sources)
            payload=result.to_dict();payload["extraction"]={"candidate_count":len(extracted),"prior_year":prior_year,"review_required":True,"review_issues":review_issues,"sections":parser.identify_sections(pages)}
            return payload
        finally:path.unlink(missing_ok=True)
else:
    app=None
