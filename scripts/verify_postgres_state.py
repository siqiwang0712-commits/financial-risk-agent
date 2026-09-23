"""Verify that the deployed API really uses PostgreSQL, and that data survives a restart.

The CI step that ran `verify_docker_health.py` was named "Verify readiness and
PostgreSQL repository selection", but that script contains no reference to a
database at all: it only proved the API answered. A wrong or missing `DATABASE_URL`
silently selects the in-memory repository and every check still passed, so the
persistence guarantee was never actually gated.

This script closes that gap in two phases, with the restart performed by the caller
(CI) so the script stays a pure HTTP client:

    # 1. assert the datastore, provision a tenant, create an entity, remember its id
    python scripts/verify_postgres_state.py --phase before --state-file .runtime/pg-state.json
    # 2. restart the API (the caller does this)
    docker compose ... restart api
    # 3. assert the datastore is unchanged and the entity is still readable
    python scripts/verify_postgres_state.py --phase after --state-file .runtime/pg-state.json

Importing this module must not perform any request.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from finrisk.verification_http import (
    VerificationEndpoints,
    request_json,
    wait_for_readiness,
)

ENDPOINTS = VerificationEndpoints.from_env()
API = ENDPOINTS.api
WEB = ENDPOINTS.web


def wait_for_ready(timeout: float = 120) -> dict:
    try:
        return wait_for_readiness(API, timeout=timeout)
    except TimeoutError as exc:
        raise SystemExit(str(exc)) from exc


def assert_postgres(readiness: dict) -> None:
    datastore = readiness.get("datastore")
    schema = readiness.get("schema")
    if datastore != "postgres" or schema != "complete":
        raise SystemExit(
            f"the API reported datastore={datastore!r}, schema={schema!r}; "
            "PostgreSQL with a complete schema was required. Check DATABASE_URL "
            "and the migrate service."
        )
    print("datastore: postgres, schema: complete (confirmed via /health/ready)")


def phase_before(state_file: Path) -> None:
    assert_postgres(wait_for_ready())
    token = os.environ.get("FINRISK_BOOTSTRAP_TOKEN")
    if not token:
        raise SystemExit("FINRISK_BOOTSTRAP_TOKEN is required to provision the verification tenant")
    organization = request_json(
        f"{API}/api/v1/enterprise/organizations",
        {"name": "Persistence verification", "actor_id": "persistence-admin"},
        {"X-Bootstrap-Token": token},
    )
    headers = {"X-API-Key": organization["api_key"]}
    entity = request_json(
        f"{API}/api/v1/enterprise/entities",
        {"name": "Persistence issuer", "sector": "industrial"},
        headers,
    )
    # Read it back through the *frontend proxy* as well: the browser path must see
    # the same record, otherwise persistence only holds for direct API clients.
    proxied = request_json(f"{WEB}/api/v1/enterprise/overview", None, headers)
    if not isinstance(proxied.get("case_count"), int):
        raise SystemExit(f"frontend proxy did not relay a valid overview: {proxied!r}")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"api_key": organization["api_key"], "entity_id": entity["id"],
                    "organization_id": entity["organization_id"]}),
        encoding="utf-8",
    )
    state_file.chmod(0o600)
    print(f"provisioned entity {entity['id']} (proxy case_count={proxied['case_count']})")


def phase_after(state_file: Path) -> None:
    if not state_file.exists():
        raise SystemExit(f"state file not found: {state_file}")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert_postgres(wait_for_ready())
    headers = {"X-API-Key": state["api_key"]}
    # The credential and the entity were both written before the restart. If either
    # the credential store or the repository were in-memory, this 401s or 404s.
    overview = request_json(f"{API}/api/v1/enterprise/overview", None, headers)
    if not isinstance(overview.get("case_count"), int):
        raise SystemExit(f"unexpected overview payload after the restart: {overview!r}")
    # 404 here means the entity row is gone, i.e. the data was never in PostgreSQL.
    timeline = request_json(
        f"{API}/api/v1/enterprise/entities/{state['entity_id']}/risk-timeline", None, headers
    )
    if not isinstance(timeline, list):
        raise SystemExit(f"entity did not survive the restart: {timeline!r}")
    print("credential and entity survived the restart")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--state-file", type=Path, default=Path(".runtime/pg-state.json"))
    args = parser.parse_args()
    if args.phase == "before":
        phase_before(args.state_file)
    else:
        phase_after(args.state_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
