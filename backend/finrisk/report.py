from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from .domain import Assessment


def render_text_report(a:Assessment)->str:
    lines=[f"FINRISK ASSESSMENT — {a.company}",f"Reporting period: {a.reporting_period}",f"Overall Risk: {a.overall_score}/100 ({a.risk_level})",f"Confidence: {a.confidence:.2f}",a.disclaimer,"","EIGHT RISK DIMENSIONS"]
    lines.append("Confidence is an uncalibrated evidence-coverage score: "+", ".join(f"{k}={v:.2f}" for k,v in a.confidence_components.items()))
    for name,d in a.dimensions.items():
        display="N/A" if d["score"] is None else f'{d["score"]}/100'
        lines.append(f"- {name}: {display} ({d['level']}); drivers: {', '.join(d['key_drivers']) or 'none triggered'}")
    lines += ["","QUANTITATIVE MODELS"]+[f"- {m.name}: {m.output if m.output is not None else 'N/A'} — {m.interpretation}; missing: {', '.join(m.missing_components) or 'none'}" for m in a.models]
    lines += ["","TRIGGERED RULES"]
    for r in a.triggered_rules:
        lines.append(f"- {r.rule_id} [{r.severity}] {r.rationale} Evidence: {', '.join(r.evidence)}")
        lines.extend(f"  Source: {e.document}, page {e.page}: {e.source_text} [{e.verification_status}]" for e in r.source_refs)
    lines += ["","CONTRADICTIONS"]+[f"- {c.management_claim} | {'; '.join(c.conflicting_evidence)} | {c.interpretation}" for c in a.contradictions]
    lines += ["","MISSING INFORMATION"]+(a.missing_information or ["- None identified."])
    return "\n".join(lines)


def export_pdf(a:Assessment,path:str|Path)->Path:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:raise RuntimeError("PDF export requires reportlab.") from exc
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);c=canvas.Canvas(str(path),pagesize=A4);w,h=A4;y=h-50;page=1
    c.setTitle(f"FinRisk Assessment - {a.company}");c.setAuthor("FinRisk-Agent")
    def footer():
        c.setFont("Helvetica",7);c.setFillColorRGB(.35,.35,.35);c.drawRightString(w-40,25,f"FinRisk-Agent | Page {page}");c.setFillColorRGB(0,0,0)
    for raw in render_text_report(a).splitlines():
        safe=raw.replace("—","-").replace("–","-")
        chunks=wrap(safe,width=92,break_long_words=True,break_on_hyphens=False) or [""]
        for line in chunks:
            if y<48:
                footer();c.showPage();page+=1;y=h-50
            c.setFont("Helvetica-Bold" if line.isupper() else "Helvetica",9)
            c.drawString(40,y,line);y-=12
    footer();c.save();return path
