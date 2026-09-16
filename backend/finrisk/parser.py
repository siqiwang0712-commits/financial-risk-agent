from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from .domain import FinancialValue
from .normalization import normalize_line_item, parse_number

# Statement-scale tokens as they actually appear in filing headers: "in thousands",
# "amounts in $ millions", "millions of dollars", "(000s)", "in 000's", "US$ mm".
# The old pattern only recognised "in|amounts in thousands|millions|billions", so
# "(000s)" and "in $ thousands" fell through and a "thousands" table was read as
# dollars — every absolute-amount threshold rule then mis-scales by 1000x while
# ratio rules look fine.
_SCALE_TOKENS = {
    "thousand": "thousand", "thousands": "thousands", "000s": "thousands", "000": "thousands",
    "million": "million", "millions": "millions", "mn": "millions", "mm": "millions",
    "billion": "billion", "billions": "billions", "bn": "billions",
}
_SCALE_PATTERN = re.compile(
    r"(thousands?|millions?|billions?|000s|000|mn|mm|bn)\b", re.IGNORECASE
)


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
            import pymupdf as fitz
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
        # A financial row has a label followed by values.  Capture the complete
        # label (including commas and "net") and postpone value selection until
        # the table's local column header is known.  Page-global year zip mapping
        # misread note numbers as values and unrelated narrative years as columns.
        line_re=re.compile(r"^\s*([A-Za-z][A-Za-z ,.'&/()-]{2,90})\s+(.*?)\s*$")
        number_re=re.compile(r"(?<![A-Za-z])(?:[-−]?[$€£]?\(?\d[\d,]*(?:\.\d+)?%?\)?)(?![A-Za-z])")
        for page,text in pages.items():
            lines=text.splitlines()
            header=" ".join(lines[:15])
            detected_currency="EUR" if "€" in text or re.search(r"\bEUR\b",header) else "GBP" if "£" in text or re.search(r"\bGBP\b",header) else "USD" if "$" in text or re.search(r"\bUSD\b",header) else currency
            scale_match=_SCALE_PATTERN.search(header)
            detected_scale=_SCALE_TOKENS.get(scale_match.group(1).lower()) if scale_match else scale
            statement=next((name for name,pat in self.SECTION_PATTERNS.items() if name in {"balance_sheet","income_statement","cash_flow"} and re.search(pat,header,re.IGNORECASE)),"unknown")
            active_years: list[int] = []
            active_context = ""
            for line_number, line in enumerate(lines):
                header_years=[int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", line)]
                # Only a local row containing at least two year headers opens a
                # comparative table.  A sole date in prose is not a value column.
                if len(header_years) >= 2:
                    active_years=header_years
                    active_context=" ".join(lines[max(0,line_number-3):line_number+1])
                m=line_re.match(line); key=normalize_line_item(m.group(1)) if m else None
                if key:
                    raws=number_re.findall(m.group(2))
                    if not raws:
                        continue
                    # A leading Note column is metadata.  Values occupy the last
                    # N numeric cells aligned to N local year columns, rather than
                    # the first N numbers on the row.
                    years = active_years[:len(raws)] if active_years and len(raws) <= len(active_years) else active_years
                    values = raws[-len(years):] if years else raws[:1]
                    mapped_years = years or [default_year]
                    context = f"{active_context} {line}"
                    local_currency="EUR" if "€" in context or re.search(r"\bEUR\b",context,re.IGNORECASE) else "GBP" if "£" in context or re.search(r"\bGBP\b",context,re.IGNORECASE) else detected_currency
                    local_scale_match=_SCALE_PATTERN.search(context)
                    local_scale=_SCALE_TOKENS.get(local_scale_match.group(1).lower()) if local_scale_match else detected_scale
                    for raw,year in zip(values,mapped_years):
                        value=parse_number(raw,local_scale)
                        out.append(FinancialValue(key,value,year,statement,currency=local_currency,document=document,page=page,source_text=line.strip(),confidence=.8 if statement!="unknown" else .65,restated=bool(re.search(r"restated",context,re.IGNORECASE))))
        return out
