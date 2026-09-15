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
# The two guards are per-branch, and that matters:
#
#   * Word tokens (`thousands`, `millions`, `mn`, `mm`, ...) need only word
#     boundaries. `(?<!\w)` stops `column` matching the bare `mn` alternative and
#     `immediate` matching `mm`; `(?!\w)` stops a token that runs on into a longer
#     word. A comma must NOT be excluded here: `"(In Millions, Except Per Share
#     Data)"` and `"Dollars in Thousands, except share data"` are among the
#     commonest scale declarations in a 10-K header, and excluding `,` silently
#     dropped them -- leaving the page unscaled, i.e. a 1,000x/1,000,000x
#     *under*statement, the mirror image of the error this pattern exists to fix.
#
#   * The `000` shorthand additionally excludes commas on both sides. It means
#     "thousands" only as a standalone token ("(000s)", "in 000's"); as the tail of
#     a number it is just digits. Without the comma guards, a header containing
#     "$1,000,000" matched the bare `000` and the page was scaled by 1000x.
_SCALE_WORD_PATTERN = re.compile(
    r"(?<!\w)(thousands?|millions?|billions?|000s|mn|mm|bn)(?!\w)",
    re.IGNORECASE,
)
_SCALE_NUMERIC_PATTERN = re.compile(r"(?<![\w,])(000)(?![\w,])")

# One financial number as it can appear in a filing table.  The parser and
# `parse_number` must accept the same separator conventions; otherwise a value
# such as `1.234,56` is correctly normalised in isolation but split into
# `1.234` and `56` before the normaliser ever sees it.
_NUMBER_TOKEN = (
    r"[$€£]?\(?-?(?:"
    r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r")\)?"
)


def _scale_token(header: str) -> str | None:
    """The scale token a filing header declares, lower-cased, or `None`.

    Two patterns rather than one alternation, because the lookarounds differ per
    branch and both branches must expose their token as `group(1)` for the
    `_SCALE_TOKENS` lookup. Word tokens are tried first so that "in 000s" resolves
    through `000s` (thousands) rather than the bare `000` shorthand.
    """
    match = _SCALE_WORD_PATTERN.search(header) or _SCALE_NUMERIC_PATTERN.search(header)
    return match.group(1).lower() if match else None


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
        line_re=re.compile(
            rf"^\s*([A-Za-z][A-Za-z '&-]{{2,60}})\s+"
            rf"({_NUMBER_TOKEN}(?:\s+{_NUMBER_TOKEN}){{0,2}})\s*$"
        )
        number_re=re.compile(_NUMBER_TOKEN)
        for page,text in pages.items():
            header=" ".join(text.splitlines()[:15])
            years=[int(y) for y in re.findall(r"\b20\d{2}\b",header)][:3] or [default_year]
            detected_currency="EUR" if "€" in text or re.search(r"\bEUR\b",header) else "GBP" if "£" in text or re.search(r"\bGBP\b",header) else "USD" if "$" in text or re.search(r"\bUSD\b",header) else currency
            scale_token=_scale_token(header)
            detected_scale=_SCALE_TOKENS.get(scale_token) if scale_token else scale
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
