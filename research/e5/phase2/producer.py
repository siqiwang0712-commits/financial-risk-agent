"""Study-only raw numeric producer, before evidence verification and Assurance.

This is an explicit structured-numeric scope, not an LLM or the released Agent.
It reuses the released metric/model/rule/fusion computations. Computational input
completeness in raw fusion is not represented as verified evidence coverage.
"""
from __future__ import annotations

import dataclasses
import operator
from pathlib import Path

from finrisk.domain import RuleSignal
from finrisk.e4_core import EXTENDED_ALIASES
from finrisk.enterprise.applicability import enforce_applicability
from finrisk.enterprise.fusion import hierarchical_escalation
from finrisk.facts import build_facts
from finrisk.metrics import calculate_metrics
from finrisk.models import altman_z, beneish_m, ohlson_o, piotroski_f
from finrisk.rules import RuleEngine
from finrisk.scoring import REQUIRED_FIELDS, aggregate

from ..execution.core import digest, file_hash, read_json, require

FIELDS = tuple(sorted(EXTENDED_ALIASES))
FEATURE_NAMES = ('fiscal_year',) + tuple(f'{period}__{key}' for period in ('current', 'previous') for key in FIELDS)
COMPONENTS = ('backend/finrisk/metrics.py', 'backend/finrisk/models.py', 'backend/finrisk/facts.py',
              'backend/finrisk/rules.py', 'backend/finrisk/scoring.py', 'backend/finrisk/enterprise/fusion.py',
              'backend/finrisk/enterprise/applicability.py', 'config/scoring.json', 'config/model_scoring.json',
              'config/decision_policy.json', 'rules/rules.json', 'rules/disabled_rules.json')


def flatten(current: dict, previous: dict | None, year: int) -> dict:
    return {'fiscal_year': year} | {f'{period}__{key}': source.get(key)
                                  for period, source in [('current', current), ('previous', previous or {})]
                                  for key in FIELDS}


class NumericProposalProducer:
    def __init__(self, root: Path):
        self.root = root
        runtime_sources = sorted(str(p.relative_to(root)) for p in (root / 'backend/finrisk').rglob('*.py'))
        self.files = {name: file_hash(root / name) for name in set(COMPONENTS) | set(runtime_sources)}
        self.files['research/e5/phase2/producer.py'] = file_hash(Path(__file__))
        self.rules = RuleEngine.from_file(root / 'rules/rules.json')
        self.scoring = read_json(root / 'config/scoring.json')
        self.mapping = read_json(root / 'config/model_scoring.json')['mappings']
        self.fusion_policy = read_json(root / 'config/decision_policy.json')
        self.schema = {'version': 'e5-index-numeric-v2', 'source_roles': ['INDEX_FILING'],
                       'features': list(FEATURE_NAMES), 'comparatives': 'SAME_INDEX_ACCESSION_ONLY',
                       'missing_values': 'EXPLICIT_NULL_NEVER_ZERO'}
        self.identity = {'version': 'e5-structured-numeric-raw-v2-complete-runtime-identity', 'code_hash': digest(self.files),
                         'model': 'RELEASED_NUMERIC_TRADITIONAL_RULE_FUSION_STUDY_BOUNDARY',
                         'prompt_hash': None, 'tool_definition_hash': digest({'components': list(COMPONENTS), 'schema': self.schema}),
                         'generation_parameters': {'deterministic': True, 'provider_calls': 0},
                         'score_semantics': 'UNCALIBRATED_RAW_RISK_POINTS_DIVIDED_BY_100'}

    def __call__(self, packet: dict) -> dict:
        require(set(packet['features']) == set(FEATURE_NAMES), 'numeric feature schema differs or includes labels')
        require(all(file_hash(self.root / name) == h for name, h in self.files.items()), 'producer code/config drift')
        features = packet['features']
        current = {key: features[f'current__{key}'] for key in FIELDS}
        previous = {key: features[f'previous__{key}'] for key in FIELDS}
        year = features['fiscal_year']
        require(type(year) is int, 'fiscal year must be an integer')
        metrics = calculate_metrics(current, year, previous)
        model_input = current | {'working_capital': metrics['working_capital'].value,
                                 'ebit': current.get('operating_income')}
        models = [altman_z(model_input, 'industrial'), beneish_m(current, previous),
                  piotroski_f(current, previous), ohlson_o(model_input)]
        models = enforce_applicability(models, 'industrial', model_input)
        facts = build_facts(current, previous, year, metrics, models, ())
        signals = self.rules.evaluate(facts)
        operators = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}
        for item in self.mapping:
            value = facts.get(item['metric'])
            if value is not None and operators[item['operator']](value, item['threshold']):
                signals.append(RuleSignal(item['id'], item['category'], 'model', item['delta'],
                                          'Frozen traditional-model mapping', [f"{item['metric']}={value}"],
                                          family='model:' + item['model'], required_inputs=[item['metric']]))
        _, _, dimensions = aggregate(signals, [], self.scoring)
        completeness = sum(current.get(k) is not None for k in REQUIRED_FIELDS) / len(REQUIRED_FIELDS)
        fusion = hierarchical_escalation({k: v['score'] for k, v in dimensions.items()},
                                        completeness, completeness, self.fusion_policy)
        score = fusion.score
        raw = {'scope': 'STRUCTURED_NUMERIC_NO_NARRATIVE_PROVIDER', 'risk_points': score,
               'fusion': fusion.to_dict(), 'dimensions': dimensions,
               'metrics': {k: v.value for k, v in metrics.items()},
               'triggered_rules': [dataclasses.asdict(s) for s in signals],
               'model_outputs': [dataclasses.asdict(m) for m in models],
               'computational_input_completeness': completeness,
               'evidence_verification_performed': False, 'assurance_performed': False,
               'producer_hash': digest(self.identity)}
        return {'raw_structured_output': raw,
                'normalized_risk_score': None if score is None else score / 100.,
                'proposed_decision': fusion.proposed_decision.value}
