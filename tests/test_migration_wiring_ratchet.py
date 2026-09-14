"""Ratchet for the declared-but-unwired migration tables (audit report J5).

`migrations/*.sql` declares tables that no runtime SQL statement touches, so the
capability they describe exists only in memory. That is a documented boundary
(`docs/enterprise_platform.md`), but a boundary nobody checks drifts: a new table
could be added and forgotten, or one of these could quietly become load-bearing
without the documentation being updated.

This test pins the set in both directions, so the count can only change on
purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tables declared in `migrations/*.sql` but never named in a SQL statement by the
# PostgreSQL adapters. `model_registry` is deliberately absent: it is written.
UNWIRED_TABLES = frozenset(
    {
        "documents",
        "jobs",
        "alerts",
        "validation_records",
        "decision_bundles",
        "temporal_evidence_nodes",
        "temporal_evidence_edges",
    }
)

# Tables that are declared *and* read/written. Named explicitly so that a table
# moving out of `UNWIRED_TABLES` has to be acknowledged here.
WIRED_TABLES = frozenset(
    {
        "organizations",
        "entities",
        "policy_versions",
        "risk_cases",
        "audit_events",
        "analysis_snapshots",
        "risk_snapshots",
        "model_registry",
        "api_credentials",
    }
)

SQL_ADAPTERS = (
    ROOT / "backend/finrisk/enterprise/postgres.py",
    ROOT / "backend/finrisk/enterprise/security.py",
)


def _declared_tables() -> set[str]:
    declared: set[str] = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        declared |= set(
            re.findall(
                r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_]+)",
                path.read_text(encoding="utf-8"),
            )
        )
    return declared


def _referenced_tables() -> set[str]:
    referenced: set[str] = set()
    for path in SQL_ADAPTERS:
        sql = path.read_text(encoding="utf-8")
        referenced |= {
            name.lower()
            for name in re.findall(
                r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_]+)", sql, re.IGNORECASE
            )
        }
    return referenced


def test_declared_tables_are_exactly_wired_plus_unwired():
    declared = _declared_tables()
    assert declared == WIRED_TABLES | UNWIRED_TABLES
    assert not (WIRED_TABLES & UNWIRED_TABLES)


def test_the_unwired_set_matches_the_runtime_sql():
    declared = _declared_tables()
    referenced = _referenced_tables()
    actually_unwired = {name for name in declared if name not in referenced}
    assert actually_unwired == set(UNWIRED_TABLES), (
        "the set of declared-but-unwired tables changed: "
        f"newly wired {sorted(set(UNWIRED_TABLES) - actually_unwired)}, "
        f"newly unwired {sorted(actually_unwired - set(UNWIRED_TABLES))}. "
        "Update `docs/enterprise_platform.md` and this ratchet together."
    )


def test_the_persistence_documentation_names_every_unwired_table():
    """The disclosure is only useful if it stays complete."""
    documentation = (ROOT / "docs/enterprise_platform.md").read_text(encoding="utf-8")
    missing = [name for name in sorted(UNWIRED_TABLES) if name not in documentation]
    assert missing == [], f"undocumented unwired tables: {missing}"
