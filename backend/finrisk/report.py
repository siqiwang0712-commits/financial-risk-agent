from __future__ import annotations

from pathlib import Path

from .domain import Assessment


def render_text_report(a:Assessment)->str:
    lines=[f"FINRISK ASSESSMENT — {a.company}",f"Reporting period: {a.reporting_period}",f"Overall Risk: {a.overall_score}/100 ({a.risk_level})",f"Confidence: {a.confidence:.2f}",a.disclaimer,"","EIGHT RISK DIMENSIONS"]
    for name,d in a.dimensions.items():lines.append(f"- {name}: {d['score']}/100 ({d['level']}); drivers: {', '.join(d['key_drivers']) or 'none triggered'}")
    lines += ["","QUANTITATIVE MODELS"]+[f"- {m.name}: {m.output if m.output is not None else 'N/A'} — {m.interpretation}; missing: {', '.join(m.missing_components) or 'none'}" for m in a.models]
    lines += ["","TRIGGERED RULES"]+[f"- {r.rule_id} [{r.severity}] {r.rationale} Evidence: {', '.join(r.evidence)}" for r in a.triggered_rules]
    lines += ["","CONTRADICTIONS"]+[f"- {c.management_claim} | {'; '.join(c.conflicting_evidence)} | {c.interpretation}" for c in a.contradictions]
    lines += ["","MISSING INFORMATION"]+(a.missing_information or ["- None identified."])
    return "\n".join(lines)


def export_pdf(a:Assessment,path:str|Path)->Path:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:raise RuntimeError("PDF export requires reportlab.") from exc
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);c=canvas.Canvas(str(path),pagesize=A4);_,h=A4;y=h-50
    for raw in render_text_report(a).splitlines():
        chunks=[raw[i:i+105] for i in range(0,max(1,len(raw)),105)] or [""]
        for line in chunks:
            if y<50:c.showPage();y=h-50
            c.drawString(40,y,line);y-=14
    c.save();return path
