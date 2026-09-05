from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from .domain import FinancialValue
from .normalization import normalize_line_item, parse_number


class DocumentParser:
    """Extracts page text, sections, and conservative line-item candidates.

    Native PDF text is preferred. OCR is intentionally an explicit fallback so
    low-quality OCR cannot silently become high-confidence financial evidence.
    """
    SECTION_PATTERNS: ClassVar[dict[str, str]] = {"balance_sheet":r"balance sheets?|statement of financial position","income_statement":r"statements? of (operations|income)","cash_flow":r"statements? of cash flows?","md&a":r"management.?s discussion","risk_factors":r"risk factors","auditor_report":r"report of independent"}

    def extract_pages(self,path:str|Path)->dict[int,str]:
        path=Path(path)
        if path.suffix.lower()==".txt": return {1:path.read_text(encoding="utf-8")}
        try:
            import fitz
        except ImportError as exc: raise RuntimeError("PDF support requires PyMuPDF; install project dependencies.") from exc
        with fitz.open(path) as doc:return {i+1:p.get_text("text") for i,p in enumerate(doc)}

    def identify_sections(self,pages:dict[int,str])->dict[str,list[int]]:
        found={k:[] for k in self.SECTION_PATTERNS}
        for page,text in pages.items():
            for name,pat in self.SECTION_PATTERNS.items():
                if re.search(pat,text,re.IGNORECASE):found[name].append(page)
        return found

    def extract_values(self,pages:dict[int,str],document:str,default_year:int,currency="USD",scale=None)->list[FinancialValue]:
        out=[]
        line_re=re.compile(r"^\s*([A-Za-z][A-Za-z '&-]{2,60})\s+((?:[$€£]?\(?[\d,]+(?:\.\d+)?\)?\s*){1,3})$")
        number_re=re.compile(r"[$€£]?\(?[\d,]+(?:\.\d+)?\)?")
        for page,text in pages.items():
            header=" ".join(text.splitlines()[:15])
            years=[int(y) for y in re.findall(r"\b20\d{2}\b",header)][:3] or [default_year]
            detected_currency="EUR" if "€" in text or re.search(r"\bEUR\b",header) else "GBP" if "£" in text or re.search(r"\bGBP\b",header) else "USD" if "$" in text or re.search(r"\bUSD\b",header) else currency
            scale_match=re.search(r"(?:in|amounts in)\s+(thousands|millions|billions)",header,re.IGNORECASE)
            detected_scale=scale_match.group(1) if scale_match else scale
            statement=next((name for name,pat in self.SECTION_PATTERNS.items() if name in {"balance_sheet","income_statement","cash_flow"} and re.search(pat,header,re.IGNORECASE)),"unknown")
            for line in text.splitlines():
                m=line_re.match(line); key=normalize_line_item(m.group(1)) if m else None
                if key:
                    raws=number_re.findall(m.group(2))
                    mapped_years=years if len(years)>=len(raws) else [default_year]*len(raws)
                    for raw,year in zip(raws,mapped_years):
                        value=parse_number(raw,detected_scale)
                        out.append(FinancialValue(key,value,year,statement,currency=detected_currency,document=document,page=page,source_text=line.strip(),confidence=.8 if statement!="unknown" else .65,restated=bool(re.search(r"restated",header,re.IGNORECASE))))
        return out
