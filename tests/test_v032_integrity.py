import json
import tomllib
from pathlib import Path

import pytest
from finrisk.empirical_validation import (
    migrate_provenance_v2,
    validate_dataset_integrity,
)
from finrisk.enterprise.domain import (
    AnalysisSnapshot,
    AuditEvent,
    Entity,
    ModelRecord,
    Organization,
    PolicyVersion,
    RiskCase,
    RiskDomain,
)
from finrisk.enterprise.fusion import (
    RiskContribution,
    deduplicate_contributions,
    hierarchical_escalation,
)
from finrisk.enterprise.integrity import DecisionReasonCode
from finrisk.enterprise.postgres import PostgresEnterpriseRepository
from finrisk.enterprise.security import (
    CredentialStore,
    PostgresCredentialStore,
    issue_api_key,
)
from finrisk.enterprise.temporal import RiskSnapshot
from finrisk.numeric_benchmark import ratio_risk_score
from finrisk.reproducibility import verify_frozen_experiment
from finrisk.research_schema import migrate_review_record_v1_to_v2
from finrisk.sec_bulk import build_reported_fcf_periods_v2

ROOT = Path(__file__).resolve().parents[1]


def _provenance_row() -> dict:
    return {
        "observation_id": "x-2024", "ticker": "X", "cik": "1", "sector": "test",
        "fiscal_year": 2024, "period_end": "2024-12-31", "filing_date": "2025-02-01",
        "accession": "a", "source_url": "https://sec.example/a", "source_hash": "a" * 64,
        "source_available_time": "2025-02-01T00:00:00Z", "information_cutoff": "2025-02-01T00:00:00Z",
        "outcome_window_end": "2026-02-01", "split": "train", "annotation_status": "pending",
    }


def _direct_provenance(concept: str) -> dict:
    return {
        "concept": concept, "unit": "USD", "period_end": "20241231",
        "source_row": {"adsh": "a", "tag": concept, "ddate": "20241231", "uom": "USD", "coreg": "", "segments": ""},
    }


def test_frozen_replay_is_read_only_and_hash_verified():
    directory = ROOT / "research/results/v0.3.1/benchmark_forensics/v0.3.1-E3"
    before = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    report = verify_frozen_experiment(directory, ROOT)
    after = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    assert report["artifact_integrity"] == "VERIFIED"
    assert report["writes_performed"] is False
    assert before == after


def test_review_schema_migration_is_non_mutating():
    original = {"reviewer_1_label": 1, "reviewer_2_label": 0}
    migrated = migrate_review_record_v1_to_v2(original)
    assert original == {"reviewer_1_label": 1, "reviewer_2_label": 0}
    assert migrated["reviewer_a_label"] == 1
    assert migrated["reviewer_b_label"] == 0
    assert migrated["human_adjudication_status"] == "NOT_COMPLETED"


def test_credentials_use_long_unique_identifier_and_rotation_revokes_old_key():
    store = CredentialStore()
    raw, credential = issue_api_key("org")
    assert len(credential.prefix) >= 36 and raw.startswith(credential.prefix + "_")
    store.register(credential)
    replacement, _ = store.rotate(credential.id)
    with pytest.raises(PermissionError):
        store.authenticate(raw)
    assert store.authenticate(replacement).organization_id == "org"


def test_used_fact_without_provenance_fails_closed():
    row = {**_provenance_row(), "facts": {"revenue": 1.0}, "fact_provenance": {}}
    report = validate_dataset_integrity([row])
    assert report["gate"] == "STOP"
    assert "FACT_PROVENANCE_MISSING" in {item["code"] for item in report["errors"]}


def test_direct_and_derived_fact_provenance_are_distinct_and_valid():
    row = _provenance_row()
    row["facts"] = {"short_term_debt": 2.0, "long_term_debt": 3.0, "total_debt": 5.0}
    row["fact_provenance"] = {
        "short_term_debt": _direct_provenance("ShortTermDebt"),
        "long_term_debt": _direct_provenance("LongTermDebt"),
        "total_debt": {"derived_from": ["short_term_debt", "long_term_debt"], "formula": "short_term_debt + long_term_debt"},
    }
    assert validate_dataset_integrity([row])["gate"] == "PASS"


def test_derived_fact_missing_parent_fails_closed():
    row = _provenance_row()
    row["facts"] = {"short_term_debt": 2.0, "total_debt": 5.0}
    row["fact_provenance"] = {
        "short_term_debt": _direct_provenance("ShortTermDebt"),
        "total_debt": {
            "derived_from": ["short_term_debt", "long_term_debt"],
            "formula": "short_term_debt + long_term_debt",
        },
    }
    codes = {item["code"] for item in validate_dataset_integrity([row])["errors"]}
    assert {"DERIVED_FACT_MISSING_PARENT", "DERIVED_PARENT_PROVENANCE_INVALID"} <= codes


def test_v2_migration_marks_unsupported_derivation_unavailable_without_mutation():
    row = _provenance_row()
    row["facts"] = {"short_term_debt": 2.0, "long_term_debt": None, "total_debt": 2.0}
    row["fact_provenance"] = {
        "short_term_debt": _direct_provenance("ShortTermDebt"),
        "total_debt": {
            "derived_from": ["short_term_debt", "long_term_debt"],
            "formula": "short_term_debt + long_term_debt",
        },
    }
    original = json.loads(json.dumps(row))
    migrated, audit = migrate_provenance_v2([row])
    assert row == original
    assert "total_debt" not in migrated[0]["facts"]
    assert migrated[0]["unavailable_facts"]["total_debt"]["status"] == "UNAVAILABLE"
    assert audit[0]["reason_code"] == "DERIVED_PARENT_UNAVAILABLE"
    assert validate_dataset_integrity(migrated)["gate"] == "PASS"


def test_v2_migration_does_not_hide_unknown_or_malformed_derivations():
    row = _provenance_row()
    row["facts"] = {"opaque_metric": 1.0}
    row["fact_provenance"] = {"opaque_metric": {"derived_from": "missing", "formula": "x"}}
    migrated, audit = migrate_provenance_v2([row])
    assert audit == []
    assert migrated[0]["facts"]["opaque_metric"] == 1.0
    assert validate_dataset_integrity(migrated)["gate"] == "STOP"


def test_unsupported_or_incorrect_derivation_fails_closed():
    row = _provenance_row()
    row["facts"] = {"short_term_debt": 2.0, "long_term_debt": 3.0, "total_debt": 6.0}
    row["fact_provenance"] = {
        "short_term_debt": _direct_provenance("ShortTermDebt"),
        "long_term_debt": _direct_provenance("LongTermDebt"),
        "total_debt": {"derived_from": ["short_term_debt", "long_term_debt"], "formula": "sum"},
    }
    assert "UNSUPPORTED_DERIVATION" in {
        item["code"] for item in validate_dataset_integrity([row])["errors"]
    }
    row["fact_provenance"]["total_debt"]["formula"] = "short_term_debt + long_term_debt"
    assert "DERIVED_VALUE_MISMATCH" in {
        item["code"] for item in validate_dataset_integrity([row])["errors"]
    }


def test_invalid_or_cyclic_derivation_fails_closed():
    row = _provenance_row()
    row["facts"] = {"a": 1.0, "b": 1.0}
    row["fact_provenance"] = {
        "a": {"derived_from": ["b"], "formula": "b"},
        "b": {"derived_from": ["a"], "formula": "a"},
    }
    assert "DERIVED_PROVENANCE_CYCLE" in {item["code"] for item in validate_dataset_integrity([row])["errors"]}
    row["fact_provenance"]["a"] = {"derived_from": [], "formula": ""}
    assert "INVALID_DERIVED_PROVENANCE" in {item["code"] for item in validate_dataset_integrity([row])["errors"]}


def test_version_metadata_is_consistent():
    from finrisk import __version__
    from finrisk.api import app

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    assert {__version__, app.version, pyproject["project"]["version"], frontend["version"]} == {"0.3.2"}


def test_ratio_missing_is_unavailable_and_cash_conversion_is_not_double_counted():
    assert ratio_risk_score({}) is None
    assert ratio_risk_score({"cfo_to_net_income": -2, "net_income": -1}) is None


def test_correlated_evidence_is_globally_capped():
    unique, suppressed = deduplicate_contributions([
        RiskContribution("liquidity", 70, "ev-a", evidence_group="filing-note-1"),
        RiskContribution("solvency", 60, "ev-b", evidence_group="filing-note-1"),
    ])
    assert len(unique) == 1 and unique[0].score == 70 and suppressed == 1


def test_aggregate_critical_has_distinct_reason_code():
    result = hierarchical_escalation({"liquidity": 75, "cash_flow": 75}, 1, 1)
    assert DecisionReasonCode.AGGREGATE_CRITICAL_SCORE.value in result.reason_codes
    assert DecisionReasonCode.CRITICAL_DIMENSION_ESCALATION.value not in result.reason_codes


def test_ytd_fcf_is_converted_to_standalone_periods():
    submissions = [
        {"adsh": "q1", "cik": "320193", "form": "10-Q", "period": "20230331", "filed": "20230501", "accepted": "20230501120000", "__archive_sha256": "a", "__archive_name": "q1"},
        {"adsh": "q2", "cik": "320193", "form": "10-Q", "period": "20230630", "filed": "20230801", "accepted": "20230801120000", "__archive_sha256": "b", "__archive_name": "q2"},
    ]
    numbers = []
    for adsh, period, qtrs, ocf, capex in (("q1", "20230331", "1", 100, 20), ("q2", "20230630", "2", 240, 50)):
        for tag, value in (("NetCashProvidedByUsedInOperatingActivities", ocf), ("PaymentsToAcquirePropertyPlantAndEquipment", capex)):
            numbers.append({"adsh": adsh, "tag": tag, "version": "us-gaap/2023", "coreg": "", "ddate": period, "qtrs": qtrs, "uom": "USD", "value": str(value), "segments": ""})
    rows = build_reported_fcf_periods_v2(submissions, numbers)
    assert [row["free_cash_flow"] for row in rows] == [80, 110]
    assert all(row["methodology_version"] == "standalone-fcf-v2" for row in rows)


class _Description:
    def __init__(self, name):
        self.name = name


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, values=None):
        self.connection.calls.append((sql, values))
        if self.connection.responses:
            names, self.rows = self.connection.responses.pop(0)
            self.description = [_Description(name) for name in names]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1


def test_postgres_repository_crud_contract_without_live_database():
    connection = _Connection()
    repository = PostgresEnterpriseRepository(connection)
    organization = Organization("o", "Org")
    entity = Entity("e", "o", "Entity")
    policy = PolicyVersion("p", "o", 1, "Policy", {"x": {"warning": 1}}, "u")
    case = RiskCase("c", "o", "e", RiskDomain.LIQUIDITY, "high", "stable", 0.5, 0.8)
    snapshot = AnalysisSnapshot("s", "o", "e", "i", "out", {}, {}, {}, {})
    model = ModelRecord("m", "o", "rules", "1", "u", "risk", "heuristic")
    for item in (organization, entity, policy, case, snapshot, model):
        assert repository.save(item) is item
    event = AuditEvent("a", "o", "u", "created", "case", "c", {})
    repository.append_event(event)
    risk_snapshot = RiskSnapshot("e", "2024", "f", 70, {"liquidity": 70}, {}, {}, "FLAG", 0.8)
    assert repository.save_risk_snapshot("o", risk_snapshot) is risk_snapshot
    assert connection.commits == 8
    with pytest.raises(TypeError):
        repository.save(object())


def test_postgres_repository_reads_are_tenant_scoped():
    case_names = [
        "id", "organization_id", "entity_id", "domain", "severity", "trajectory",
        "confidence", "evidence_coverage", "status", "owner_id", "reviewer_id",
        "due_date", "rationale", "evidence_ids", "actions", "comments", "created_at",
        "updated_at", "reason_codes", "decision_trace", "snapshot_id", "fusion_version",
        "resolution_evidence", "monitoring_state",
    ]
    case_row = ("c", "o", "e", "liquidity", "high", "stable", 0.5, 0.8, "detected", None, None, None, "r", [], [], [], "now", "now", [], {}, "s", "f1", [], "active")
    entity_names = ["id", "organization_id", "parent_id", "name", "sector"]
    policy_names = ["id", "organization_id", "version", "name", "thresholds", "created_by", "created_at", "status"]
    snapshot_names = ["id", "organization_id", "entity_id", "input_hash", "output_hash", "document_versions", "component_versions", "frozen_input", "frozen_output", "created_at"]
    connection = _Connection([
        (case_names, [case_row]), (case_names, [case_row]),
        (entity_names, [("e", "o", None, "Entity", "industrial")]),
        (policy_names, [("p", "o", 1, "Policy", {}, "u", "now", "active")]),
        ([], [("a", "o", "u", "created", "case", "c", {}, "now")]),
        (snapshot_names, [("s", "o", "e", "i", "out", {}, {}, {}, {}, "now")]),
        ([], [("2024", "f", 70, {}, {}, {}, "FLAG", 0.8, None, "UNCALIBRATED")]),
        ([], []),
    ])
    repository = PostgresEnterpriseRepository(connection)
    assert repository.get_case("o", "c").id == "c"
    assert repository.list_cases("o")[0].organization_id == "o"
    assert repository.get_entity("o", "e").name == "Entity"
    assert repository.get_policy("o", "p").version == 1
    assert repository.list_events("o")[0].id == "a"
    assert repository.get_snapshot("o", "s").output_hash == "out"
    assert repository.list_risk_snapshots("o", "e")[0].period == "2024"
    with pytest.raises(KeyError):
        repository.get_entity("o", "missing")


def test_postgres_credentials_persist_hash_and_revoke_on_rotation():
    raw, credential = issue_api_key("o", "u")
    connection = _Connection([
        ([], []),
        ([], [(credential.id, "o", credential.key_hash, "u", "analyst", True)]),
        ([], [("o", "u", "analyst")]),
        ([], []),
        ([], []),
    ])
    store = PostgresCredentialStore(connection)
    store.register(credential)
    assert store.authenticate(raw).organization_id == "o"
    replacement, new_credential = store.rotate(credential.id)
    assert replacement.startswith(new_credential.prefix)
    assert connection.commits == 2

    denied = PostgresCredentialStore(_Connection([( [], [] )]))
    with pytest.raises(PermissionError):
        denied.authenticate("frk_unknown_secret")
    missing = PostgresCredentialStore(_Connection([( [], [] )]))
    with pytest.raises(KeyError):
        missing.rotate("missing")
