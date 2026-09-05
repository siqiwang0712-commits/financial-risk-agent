import fitz
from fastapi.testclient import TestClient
from finrisk.api import app


def test_pdf_upload_reaches_assessment_pipeline():
    doc=fitz.open();page=doc.new_page();page.insert_text((72,72),"BALANCE SHEET\nCash and cash equivalents 1,250\nTotal assets 5,000")
    pdf=doc.tobytes();doc.close()
    response=TestClient(app).post("/api/v1/documents/analyze",data={"company":"Synthetic API Co","fiscal_year":"2025"},files={"file":("synthetic.pdf",pdf,"application/pdf")})
    assert response.status_code==200
    body=response.json()
    assert body["company"]=="Synthetic API Co"
    assert body["extraction"]["candidate_count"]>=2
    assert body["extraction"]["review_required"] is True

def test_upload_rejects_non_pdf():
    response=TestClient(app).post("/api/v1/documents/analyze",data={"company":"X","fiscal_year":"2025"},files={"file":("x.pdf",b"not-pdf","application/pdf")})
    assert response.status_code==415
