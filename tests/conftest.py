"""Shared pytest configuration.

Provisioning the first administrator through `POST /api/v1/enterprise/organizations`
is opt-in (`FINRISK_ENABLE_ORG_BOOTSTRAP` now defaults to "0"), so the suite opts in
explicitly - integration tests need a tenant, and the value is read once, while
`finrisk.api` is imported.
"""

import os

os.environ.setdefault("FINRISK_ENABLE_ORG_BOOTSTRAP", "1")
# `provider_from_env` is fail-closed, so the suite names its provider explicitly;
# these tests are offline and must never reach a hosted model.
os.environ.setdefault("FINRISK_LLM_PROVIDER", "mock")
