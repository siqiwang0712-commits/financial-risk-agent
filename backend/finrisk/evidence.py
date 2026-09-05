from __future__ import annotations

import re

from .domain import Evidence


class EvidenceVerifier:
    def verify(self,evidence: Evidence,page_texts: dict[int,str]) -> Evidence:
        source=" ".join(evidence.source_text.split())
        page=" ".join(page_texts.get(evidence.page,"").split())
        exact=bool(source) and source.casefold() in page.casefold()
        if not exact and source:
            tokens=set(re.findall(r"\w+",source.casefold())); hay=set(re.findall(r"\w+",page.casefold()))
            exact=len(tokens)>=5 and len(tokens & hay)/len(tokens)>=.9
        return Evidence(evidence.document,evidence.page,evidence.source_text,evidence.fiscal_year,evidence.confidence if exact else min(evidence.confidence,.25),exact)

