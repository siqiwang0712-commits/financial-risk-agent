from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .contradictions import detect_contradictions, evaluate_claim_consistency
from .domain import Assessment, RuleSignal
from .enterprise.applicability import (
    ALTMAN_VARIANT_REQUIREMENTS,
    MODEL_KEYS,
    MODEL_REQUIREMENTS,
    enforce_applicability,
)
from .enterprise.fusion import failure_aware_decision, hierarchical_escalation
from .enterprise.tension import classify_tension
from .evidence import (
    PROOF_COVERED_STATUSES,
    EvidenceVerifier,
    claim_is_grounded,
    has_risk_language,
)
from .facts import build_facts, narrative_signals
from .llm import NarrativeProvider, provider_from_env
from .metrics import calculate_metrics, resolve_total_debt
from .models import altman_z, beneish_m, ohlson_o, piotroski_f
from .rules import RuleEngine
from .scoring import aggregate, confidence, confidence_components, effective_signals
from .severity import severity_label


class FinRiskPipeline:
    def __init__(
        self,
        root: Path | None = None,
        provider: NarrativeProvider | None = None,
    ):
        self.root = root or Path(__file__).resolve().parents[2]
        self.rules_source = (self.root / "rules" / "rules.json").read_text(
            encoding="utf-8"
        )
        self.scoring_source = (self.root / "config" / "scoring.json").read_text(
            encoding="utf-8"
        )
        rules_payload = json.loads(self.rules_source)
        self.rules = RuleEngine(rules_payload["rules"])
        self.scoring = json.loads(self.scoring_source)
        self.model_scoring = json.loads(
            (self.root / "config" / "model_scoring.json").read_text(encoding="utf-8")
        )
        self.decision_policy = json.loads(
            (self.root / "config" / "decision_policy.json").read_text(encoding="utf-8")
        )
        self.provider = provider or provider_from_env()
        self.verifier = EvidenceVerifier()
        self._assert_signals_are_not_double_counted()
        self._assert_model_names_are_known()

    def _assert_model_names_are_known(self) -> None:
        """Fail at construction when the config names a model the code cannot route.

        `config/model_scoring.json` is a versioned artifact edited independently of
        the code. An unknown name used to surface as a bare `KeyError` in the middle
        of a request -- i.e. an unexplained 500 with no pointer to the config.
        """
        unknown = sorted(
            {mapping["model"] for mapping in self.model_scoring["mappings"]} - set(MODEL_KEYS)
        )
        if unknown:
            raise ValueError(f"model_scoring.json names unknown models: {unknown}")

    def _assert_signals_are_not_double_counted(self) -> None:
        """Fail fast when one risk signal can be produced twice for one dimension.

        `rules.json` and `model_scoring.json` are independent registries that both
        write into the same dimension. A `(metric, operator, threshold, category)`
        signature present in both added its delta twice (Beneish scored +36 in the
        accounting dimension instead of +18). Only *single-condition* rules are
        compared: a multi-condition rule may legitimately reuse an atomic
        comparison that another rule owns alone.
        """
        def signature(metric, operator, value, category):
            return (metric, operator, value, category)

        owners: dict[tuple, str] = {}
        for rule in self.rules.rules:
            if len(rule["conditions"]) != 1:
                continue
            condition = rule["conditions"][0]
            key = signature(condition["metric"], condition["operator"], condition["value"], rule["category"])
            if key in owners:
                raise ValueError(
                    f"duplicate risk signal {key}: {rule['id']} repeats {owners[key]}"
                )
            owners[key] = rule["id"]
        for mapping in self.model_scoring["mappings"]:
            key = signature(mapping["metric"], mapping["operator"], mapping["threshold"], mapping["category"])
            if key in owners:
                raise ValueError(
                    f"duplicate risk signal {key}: model mapping {mapping['id']} repeats {owners[key]}"
                )
            owners[key] = mapping["id"]

    def decide(self, assessment: Assessment) -> dict:
        """Attach the single decision-bearing score to an assessment payload.

        Both the deterministic endpoint and the agent path route through here, so
        `overall_score` always means "the score the decision was derived from".
        The weighted aggregate is preserved under an explicit legacy name instead
        of being published as a second, differently-defined `overall_score`
        (previously 44.1 on one endpoint and 74.0 on the other for the same input).
        """
        payload = assessment.to_dict()
        dimension_scores = {
            name: value.get("score")
            for name, value in payload.get("dimensions", {}).items()
        }
        fusion = hierarchical_escalation(
            dimension_scores,
            assessment.evidence_coverage,
            assessment.confidence,
            self.decision_policy,
        )
        weighted = assessment.overall_score
        score = fusion.score if fusion.score is not None else weighted
        payload["weighted_dimension_score"] = weighted
        payload["legacy_weighted_score"] = weighted
        payload["overall_score"] = score
        payload["risk_level"] = severity_label(score)
        # A suppressed extraction must not read as a clean result: it is the same
        # failure signal as a provider that could not be reached.
        failures = (
            {"llm_unavailable": True}
            if getattr(assessment, "narrative_suppressed", False)
            else {}
        )
        failure = failure_aware_decision(fusion, failures)
        # Kept in step with the agent path: `final_decision` must be the
        # failure-aware disposition, not the raw fusion outcome, so the two published
        # decisions cannot disagree.
        payload["final_decision"] = failure["decision"]
        payload["failure_state"] = failure
        payload["model_disagreement"] = fusion.disagreement
        payload["enterprise_fusion"] = fusion.__dict__
        return payload

    def assess(self,company:str,year:int,current:dict,previous:dict|None=None,pages:dict[int,str]|None=None,document="Annual Report",entity_type="industrial",source_map:dict|None=None,narrative_claims:list|None=None,claim_verifications:list|None=None) -> Assessment:
        pages=pages or {}
        source_map=source_map or {}
        metrics=calculate_metrics(current,year,previous)
        for metric in metrics.values():
            seen=set()
            for key in metric.inputs:
                for ev in source_map.get(key,[]):
                    identity=(ev.document,ev.page,ev.source_text)
                    if identity not in seen:metric.source_refs.append(ev);seen.add(identity)

        def period_refs(raw_key: str, fiscal_year: int) -> list:
            refs = list(source_map.get(raw_key, []))
            return [ref for ref in refs if ref.fiscal_year == fiscal_year]

        def debt_requirements(values: dict, fiscal_year: int) -> list[tuple[str, int]]:
            _, parents = resolve_total_debt(values)
            return [(parent, fiscal_year) for parent in parents]

        def metric_requirements(name: str) -> list[tuple[str, int]]:
            if name.endswith("_growth"):
                base = name.removesuffix("_growth")
                if base == "free_cash_flow":
                    return [(key, period) for period in (year, year - 1) for key in ("operating_cash_flow", "capital_expenditure")]
                if base == "total_debt":
                    return debt_requirements(current, year) + debt_requirements(previous or {}, year - 1)
                return [(base, year), (base, year - 1)]
            aliases = {
                "EBIT": "ebit" if current.get("ebit") is not None else "operating_income",
                "EBITDA": "ebitda",
                "assets_basis": "total_assets",
                "equity_basis": "shareholder_equity",
                "receivables_basis": "accounts_receivable",
                "inventory_basis": "inventory",
                "payables_basis": "accounts_payable",
            }
            requirements = []
            metric = metrics[name]
            for input_name in metric.inputs:
                if input_name in metrics and input_name != name:
                    requirements.extend(metric_requirements(input_name))
                elif input_name == "free_cash_flow":
                    requirements.extend(metric_requirements("free_cash_flow"))
                elif input_name == "COGS":
                    requirements.extend((("revenue", year), ("gross_profit", year)))
                elif input_name in {"total_debt", "short_term_debt", "long_term_debt"} and "debt" in metric.formula.casefold():
                    requirements.extend(debt_requirements(current, year) if input_name == "total_debt" else [(input_name, year)])
                else:
                    raw = aliases.get(input_name, input_name)
                    requirements.append((raw, year))
                    if previous and input_name.endswith("_basis") and "average" in metric.formula:
                        requirements.append((raw, year - 1))
            return list(dict.fromkeys(requirements))

        def complete_refs(requirements: list[tuple[str, int]]) -> list:
            groups = [period_refs(key, period) for key, period in requirements]
            refs = [ref for group in groups for ref in group]
            return refs if groups and all(groups) else []

        def fact_requirements(name: str) -> list[tuple[str, int]]:
            if name in metrics:
                return metric_requirements(name)
            if name in {"accounts_receivable_growth_gap", "inventory_growth_gap"}:
                base = name.removesuffix("_gap")
                return metric_requirements(base) + metric_requirements("revenue_growth")
            if name.endswith("_change") and name.removesuffix("_change") in metrics:
                base = name.removesuffix("_change")
                current_requirements = metric_requirements(base)
                prior_requirements = [(key, period - 1) for key, period in current_requirements if period == year]
                return list(dict.fromkeys(current_requirements + prior_requirements))
            return [(name, year)]
        resolved_debt, debt_parents = resolve_total_debt(current)
        if current.get("total_debt") is None and resolved_debt is not None:
            source_map = dict(source_map)
            source_map["total_debt"] = [
                evidence for parent in debt_parents for evidence in source_map.get(parent, [])
            ]
        model_input=current|{"working_capital":metrics["working_capital"].value,"ebit":current.get("ebit") if current.get("ebit") is not None else current.get("operating_income")}
        models=[altman_z(model_input,entity_type)]
        if previous: models += [beneish_m(current,previous),piotroski_f(current,previous)]
        models += [ohlson_o(model_input)]
        models = enforce_applicability(models, entity_type, model_input | current)
        if narrative_claims is None:
            raw_claims=self.provider.extract(pages,document,year) if pages else []
            verified=[]; accepted=[]
            for claim in raw_claims:
                ev=self.verifier.verify(claim.evidence,pages)
                if ev.verified and not claim_is_grounded(
                    claim.claim, ev.source_text, pages.get(ev.page, "")
                ):
                    # The quote is on the page, but the free-text `claim` is not
                    # supported by it. Left as-is this let an unrelated claim carry a
                    # verified quotation into a +30 going-concern rule.
                    ev=replace(ev,verified=False,verification_status="unverified",confidence=min(ev.confidence,0.25))
                verified.append(ev)
                if ev.verified: claim.evidence=ev; accepted.append(claim)
        else:
            # Supplied by the caller so narrative extraction runs exactly once per
            # analysis. `claim_verifications` carries the full verification list,
            # not just the accepted subset, so `verified_claim_coverage` keeps its
            # original denominator (fraction of extracted claims that verified).
            accepted=list(narrative_claims)
            verified=list(claim_verifications or [])
        # One definition of the fact set, shared with the Agent path.
        facts = build_facts(current, previous, year, metrics, models, accepted)
        signals_by_source = narrative_signals(accepted)
        source_map = dict(source_map)
        for key, items in signals_by_source.items():
            if items:
                source_map[key] = [item.evidence for item in items]
        # Extraction ran inline (the deterministic endpoint). A schema-valid empty
        # claim set is indistinguishable from "no risk language found", so flag the
        # case where risk-bearing text produced nothing; `decide` escalates it.
        narrative_suppressed = bool(
            narrative_claims is None and pages and not accepted
            and has_risk_language(pages)
        )
        signals=self.rules.evaluate(facts)
        ops={"<":lambda a,b:a<b,"<=":lambda a,b:a<=b,">":lambda a,b:a>b,">=":lambda a,b:a>=b}
        for mapping in self.model_scoring["mappings"]:
            value=facts.get(mapping["metric"])
            if value is not None and ops[mapping["operator"]](value,mapping["threshold"]):
                # A caller-supplied metric name can cross the threshold even when the
                # model producing it was never evaluated (Beneish/Piotroski need a prior
                # period), so the lookup must not raise StopIteration.
                model=next((m for m in models if m.name==mapping["model"]),None)
                if model is None:
                    continue
                refs=[]
                for key in model.inputs:refs.extend(source_map.get(key,[]))
                model_key = MODEL_KEYS[mapping["model"]]
                if model_key == "altman":
                    variant = model.derived_outputs.get("variant", "public_manufacturer")
                    base_required = sorted(ALTMAN_VARIANT_REQUIREMENTS[variant])
                else:
                    base_required = sorted(MODEL_REQUIREMENTS[model_key])
                if mapping["model"] in {"Beneish M-Score", "Piotroski F-Score"}:
                    required = [f"current:{key}" for key in base_required] + [f"prior:{key}" for key in base_required]
                else:
                    required = base_required
                provenance = {}
                for key in required:
                    period = year
                    raw_key = key
                    if key.startswith("current:"):
                        raw_key = key.split(":", 1)[1]
                    elif key.startswith("prior:"):
                        raw_key = key.split(":", 1)[1]
                        period = year - 1
                    elif key == "prior_net_income":
                        raw_key, period = "net_income", year - 1
                    if raw_key in metrics and period == year:
                        provenance[key] = complete_refs(metric_requirements(raw_key))
                    else:
                        provenance[key] = complete_refs([(raw_key, period)])
                signals.append(RuleSignal(mapping["id"],mapping["category"],"model",mapping["delta"],f'{mapping["model"]} crossed configured risk threshold; model limitations still apply.',[f'{mapping["metric"]}={value} {mapping["operator"]} {mapping["threshold"]}'],refs,family=f'model:{mapping["model"]}',required_inputs=required,input_provenance=provenance))
        for signal in signals:
            keys=[item.split("=",1)[0] for item in signal.evidence]
            refs=list(signal.source_refs)
            input_provenance = dict(signal.input_provenance)
            for key in keys:
                refs.extend(source_map.get(key,[]))
                if key in metrics:
                    refs.extend(metrics[key].source_refs)
                    input_provenance[key] = complete_refs(fact_requirements(key))
                else:
                    input_provenance[key] = complete_refs(fact_requirements(key))
            signal.source_refs=list({(e.document,e.page,e.source_text):e for e in refs}.values())
            signal.required_inputs = signal.required_inputs or keys
            signal.input_provenance = {
                key: input_provenance.get(key, list(source_map.get(key, [])))
                for key in signal.required_inputs
            }
        contradictions=detect_contradictions(accepted,facts)
        # Claim-level consistency is derived here, from the same `accepted` claims
        # and the same thick `facts` that produced `contradictions`, so the tension
        # list can never contradict the contradiction list.
        claim_evaluations=[];tensions=[]
        for claim in accepted:
            evaluation=evaluate_claim_consistency(claim,facts)
            claim_evaluations.append(evaluation.to_dict())
            tensions.append(classify_tension(claim,list(evaluation.supporting_evidence),list(evaluation.opposing_evidence),"Compared with all available normalized evidence for the claim category.","complete" if not evaluation.missing_evidence_types else "incomplete_context",evaluation.reason_code).to_dict())
        score,level,dimensions=aggregate(signals,contradictions,self.scoring)
        missing=[f"{m.name}: N/A — {m.missing_reason} Impact: assessment confidence reduced." for m in metrics.values() if m.value is None]
        numeric_evidence=[e for refs in source_map.values() for e in refs]
        conf=confidence(current,verified,models,previous is not None,numeric_evidence)
        components=confidence_components(current,verified,models,previous is not None,numeric_evidence)
        # A weaker member suppressed by family de-duplication cannot alter the
        # decision and therefore cannot alter the proof gate either.
        material_groups = [
            signal.input_provenance.get(name, [])
            for signal in effective_signals(signals)
            for name in signal.required_inputs
        ]
        # Proof gate: a material input group counts as covered only when it is
        # non-empty and every reference is `verified`. `located` intentionally does
        # not qualify here (see `evidence.PROOF_COVERED_STATUSES`).
        evidence_coverage = round(
            sum(bool(refs) and all(ref.verification_status in PROOF_COVERED_STATUSES for ref in refs) for refs in material_groups)
            / len(material_groups),
            3,
        ) if material_groups else 0.0
        nodes=[];edges=[]
        for key,refs in source_map.items():
            for i,e in enumerate(refs):nodes.append({"id":f"value:{key}:{i}","type":"financial_value","label":key,"document":e.document,"page":e.page,"status":e.verification_status})
        for name,m in metrics.items():
            nodes.append({"id":f"metric:{name}","type":"metric","label":name,"formula":m.formula})
            for key in m.inputs:
                for i,_ in enumerate(source_map.get(key,[])):edges.append({"from":f"value:{key}:{i}","to":f"metric:{name}","relation":"input_to"})
        for model in models:
            model_id="model:"+model.name.lower().replace(" ","_")
            nodes.append({"id":model_id,"type":"model","label":model.name,"applicability":model.applicability})
            for key in model.inputs:
                for i,_ in enumerate(source_map.get(key,[])):edges.append({"from":f"value:{key}:{i}","to":model_id,"relation":"model_input"})
        for s in signals:
            nodes.append({"id":f"signal:{s.rule_id}","type":"signal","label":s.rule_id})
            if s.rule_id.startswith("MODEL_"):
                model_name=next((m["model"] for m in self.model_scoring["mappings"] if m["id"]==s.rule_id),None)
                if model_name:edges.append({"from":"model:"+model_name.lower().replace(" ","_"),"to":f"signal:{s.rule_id}","relation":"mapped_to"})
            for key in [x.split("=",1)[0] for x in s.evidence]:
                target=f"metric:{key}" if key in metrics else None
                if target:edges.append({"from":target,"to":f"signal:{s.rule_id}","relation":"triggers"})
            edges.append({"from":f"signal:{s.rule_id}","to":f"dimension:{s.category}","relation":"contributes_to"})
        for i,claim in enumerate(accepted):nodes.append({"id":f"claim:{i}","type":"claim","label":claim.claim,"page":claim.evidence.page})
        for i,c in enumerate(contradictions):
            nodes.append({"id":f"contradiction:{i}","type":"contradiction","label":c.category})
            edges.append({"from":f"claim:{accepted.index(next(x for x in accepted if x.claim==c.management_claim))}","to":f"contradiction:{i}","relation":"claim_input"})
            edges.append({"from":f"contradiction:{i}","to":f"dimension:{c.category}","relation":"contributes_to"})
        for category in dimensions:nodes.append({"id":f"dimension:{category}","type":"dimension","label":category});edges.append({"from":f"dimension:{category}","to":"overall","relation":"weighted_into"})
        nodes.append({"id":"overall","type":"assessment","label":"overall risk"})
        graph={"nodes":nodes,"edges":edges}
        result=Assessment(company,str(year),score,level,conf,dimensions,metrics,models,signals,contradictions,missing,confidence_components=components,evidence_graph=graph,evidence_quality=conf,evidence_coverage=evidence_coverage,reliability_status="UNCALIBRATED",claim_consistency_evaluations=claim_evaluations,disclosure_tensions=tensions)
        # Not a dataclass field, so `to_dict()` - and therefore the published payload -
        # is unchanged; it only lets `decide` escalate a suppressed extraction.
        result.narrative_suppressed = narrative_suppressed
        return result
