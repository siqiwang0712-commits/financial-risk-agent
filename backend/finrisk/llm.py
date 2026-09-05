from __future__ import annotations

from typing import ClassVar, Protocol

from .domain import Evidence, NarrativeClaim


class NarrativeProvider(Protocol):
    def extract(self,pages:dict[int,str],document:str,year:int)->list[NarrativeClaim]: ...


class MockNarrativeProvider:
    """Deterministic provider for tests and offline demos; never invents evidence."""
    patterns: ClassVar[dict[str, tuple[str, str]]] = {"going concern":("going_concern","negative"),"substantial doubt":("going_concern","negative"),"refinancing":("liquidity","negative"),"customer concentration":("business","negative"),"material weakness":("governance_audit","negative"),"liquidity remains strong":("liquidity","positive")}
    def extract(self,pages,document,year):
        claims=[]
        for page,text in pages.items():
            low=text.lower()
            for phrase,(cat,polarity) in self.patterns.items():
                if phrase in low:
                    sentence=next((s.strip() for s in text.replace("\n"," ").split(".") if phrase in s.lower()),phrase)
                    claims.append(NarrativeClaim(sentence,cat,Evidence(document,page,sentence,year,.9),polarity))
        return claims
